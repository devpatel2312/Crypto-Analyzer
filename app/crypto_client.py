"""Crypto market-data adapter.

Deribit supplies the actual BTC/ETH options market data (options, IV, OI, volume,
mark prices). QuickNode is used as the blockchain provider for BTC/ETH network
health/metadata. QuickNode's core RPC APIs do not expose an options market feed.
"""
import math
import time
from datetime import datetime, timezone

import requests

from .config import ASSETS, DERIBIT_URL, QUICKNODE_BTC_URL, QUICKNODE_ETH_URL, CRYPTO_RISK_FREE

_CURRENCY = {"BTC": "BTC", "ETH": "ETH"}


def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _npdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _bs_greeks(spot, strike, expiry_ms, iv_pct, option_type):
    if not spot or not strike or not iv_pct:
        return {"delta": None, "theta": None, "vega": None, "gamma": None}
    sigma = max(float(iv_pct) / 100.0, 1e-6)
    t = max((expiry_ms - int(time.time() * 1000)) / 1000 / 86400 / 365, 1e-6)
    r = CRYPTO_RISK_FREE
    sqrt_t = math.sqrt(t)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    if option_type == "call":
        delta = _ncdf(d1)
        theta = (-spot * _npdf(d1) * sigma / (2 * sqrt_t) - r * strike * math.exp(-r * t) * _ncdf(d2)) / 365
    else:
        delta = _ncdf(d1) - 1
        theta = (-spot * _npdf(d1) * sigma / (2 * sqrt_t) + r * strike * math.exp(-r * t) * _ncdf(-d2)) / 365
    return {
        "delta": delta,
        "theta": theta,
        "vega": spot * _npdf(d1) * sqrt_t / 100,
        "gamma": _npdf(d1) / (spot * sigma * sqrt_t),
    }


class CryptoClient:
    def __init__(self):
        self.session = requests.Session()
        self._instruments = {}
        self._expiry_cache = {}
        self._quicknode_cache = {}

    def _call(self, method, params):
        r = self.session.get(f"{DERIBIT_URL}/public/{method}", params=params, timeout=10)
        r.raise_for_status()
        payload = r.json()
        if payload.get("error"):
            err = payload["error"]
            raise RuntimeError(f"Deribit {err.get('code')}: {err.get('message')}")
        return payload.get("result")

    def _quicknode_status(self, asset):
        # QuickNode is intentionally optional. A missing URL must never prevent
        # the public options feed from working.
        url = QUICKNODE_BTC_URL if asset == "BTC" else QUICKNODE_ETH_URL
        if not url:
            return None
        hit = self._quicknode_cache.get(asset)
        if hit and time.time() - hit[0] < 30:
            return hit[1]
        try:
            if asset == "ETH":
                body = {"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}
                res = self.session.post(url, json=body, timeout=5).json()
                block = int(res["result"], 16)
            else:
                body = {"jsonrpc": "2.0", "id": 1, "method": "getblockcount", "params": []}
                res = self.session.post(url, json=body, timeout=5).json()
                block = int(res["result"])
            value = {"ok": True, "block": block}
        except Exception as exc:
            value = {"ok": False, "error": str(exc)}
        self._quicknode_cache[asset] = (time.time(), value)
        return value

    def _load_instruments(self, asset):
        if asset not in self._instruments:
            result = self._call("get_instruments", {"currency": _CURRENCY[asset], "kind": "option", "expired": "false"})
            self._instruments[asset] = [x for x in result if x.get("is_active", True)]
        return self._instruments[asset]

    def expiries(self, asset):
        hit = self._expiry_cache.get(asset)
        if hit and time.time() - hit[0] < 60:
            return hit[1]
        exps = sorted({int(x["expiration_timestamp"]) for x in self._load_instruments(asset)})
        # UI uses YYYYMMDD; keep only future expiries and deduplicate dates.
        dates = sorted({datetime.fromtimestamp(x / 1000, timezone.utc).strftime("%Y%m%d") for x in exps})
        self._expiry_cache[asset] = (time.time(), dates)
        return dates

    def _expiry_ms(self, expiry):
        return int(datetime.strptime(expiry, "%Y%m%d").replace(hour=8, tzinfo=timezone.utc).timestamp() * 1000)

    def option_chain(self, asset, expiry=None):
        instruments = self._load_instruments(asset)
        if expiry is None:
            expiry = self.expiries(asset)[0]
        target = [x for x in instruments if datetime.fromtimestamp(x["expiration_timestamp"] / 1000, timezone.utc).strftime("%Y%m%d") == str(expiry)]
        if not target:
            raise LookupError(f"No active {asset} option contracts for expiry {expiry}")

        summary = self._call("get_book_summary_by_currency", {"currency": asset, "kind": "option"}) or []
        allowed = {x["instrument_name"]: x for x in target}
        books = {x.get("instrument_name"): x for x in summary if x.get("instrument_name") in allowed}
        spot = next((b.get("underlying_price") for b in books.values() if b.get("underlying_price") is not None), None)
        if spot is None:
            # fallback from an option's underlying_price via ticker
            inst = next(iter(allowed))
            tick = self._call("ticker", {"instrument_name": inst}) or {}
            spot = tick.get("underlying_price")
        if spot is None:
            raise RuntimeError(f"Unable to determine {asset} underlying price")

        rows = {}
        for name, inst in allowed.items():
            b = books.get(name, {})
            strike = float(inst["strike"])
            side = "ce" if inst["option_type"] == "call" else "pe"
            iv = b.get("mark_iv")
            greeks = _bs_greeks(spot, strike, inst["expiration_timestamp"], iv, inst["option_type"])
            # Deribit option prices are quoted in BTC/ETH units. Keep them as
            # exchange-native option prices; spot remains USD.
            leg = {
                "ref_id": name,
                "ltp": b.get("last"),
                "iv": iv,
                "delta": greeks["delta"],
                "gamma": greeks["gamma"],
                "theta": greeks["theta"],
                "vega": greeks["vega"],
                "oi": b.get("open_interest"),
                "oi_chg": None,
                "vol": b.get("volume"),
                "bid": b.get("bid_price"),
                "ask": b.get("ask_price"),
            }
            rows.setdefault(strike, {"strike": strike, "ce": None, "pe": None})[side] = leg

        ordered = sorted(rows.values(), key=lambda x: x["strike"])
        atm = min((r["strike"] for r in ordered), key=lambda k: abs(k - spot)) if ordered else None
        return {
            "asset": asset, "expiry": str(expiry), "spot": spot, "atm": atm,
            "ts": int(time.time() * 1000), "rows": ordered,
            "expiries": self.expiries(asset), "provider": "Deribit + QuickNode",
            "quicknode": self._quicknode_status(asset),
            "price_unit": "coin",
        }

    def resolve_symbol(self, asset, expiry, strike, opt):
        target = "call" if opt == "CE" else "put"
        for x in self._load_instruments(asset):
            if (datetime.fromtimestamp(x["expiration_timestamp"] / 1000, timezone.utc).strftime("%Y%m%d") == str(expiry)
                    and float(x["strike"]) == float(strike) and x["option_type"] == target):
                return x["instrument_name"]
        raise LookupError(f"{asset} {expiry} {strike}{opt} not found")

    def option_history(self, asset, symbols, fields, start, end, interval):
        # Deribit historical option candles are available per instrument, but
        # this adapter deliberately keeps the first integration live-only. The
        # UI hides historical mode for crypto rather than returning misleading data.
        return {}

    def underlying_series(self, asset, start, end, interval):
        return []
