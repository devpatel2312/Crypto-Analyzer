import os
os.environ["DB_PATH"] = "/tmp/test_crypto_cache.db"

from fastapi.testclient import TestClient

from app.main import app, _client
from app.crypto_client import CryptoClient


class FakeCryptoClient(CryptoClient):
    def expiries(self, asset):
        return ["20261009", "20261016", "20261023"]

    def option_chain(self, asset, expiry=None):
        expiry = expiry or self.expiries(asset)[0]
        spot = 100000.0 if asset == "BTC" else 4000.0
        step = 1000.0 if asset == "BTC" else 50.0
        rows = []
        for i in range(-10, 11):
            strike = spot + i * step
            leg = lambda side: {"ref_id": f"{asset}-{expiry}-{strike}-{side}", "ltp": 1.0,
                                 "iv": 60.0, "delta": 0.5 if side == "CE" else -0.5,
                                 "gamma": 0.001, "theta": -1.0, "vega": 2.0,
                                 "oi": 100.0, "oi_chg": 0.0, "vol": 10.0,
                                 "bid": 0.9, "ask": 1.1}
            rows.append({"strike": strike, "ce": leg("CE"), "pe": leg("PE")})
        return {"asset": asset, "expiry": expiry, "spot": spot, "atm": spot,
                "ts": 1000, "rows": rows, "expiries": self.expiries(asset),
                "provider": "test"}


import app.main as main
main._client = FakeCryptoClient()
c = TestClient(app)


def test_assets_are_btc_eth_only():
    j = c.get("/api/assets").json()
    assert [a["id"] for a in j["assets"]] == ["BTC", "ETH"]
    assert j["provider"] == "Deribit"


def test_live_chain_and_multi_expiry_greeks():
    for asset in ("BTC", "ETH"):
        exp = c.get("/api/expiries", params={"asset": asset}).json()[0]
        ch = c.get("/api/chain/live", params={"asset": asset, "expiry": exp}).json()
        assert len(ch["rows"]) == 21
        selection = ch["selection"]
        assert selection["atm"] == ch["spot"]
        assert len(selection["ce_otm_strikes"]) == 5
        assert len(selection["pe_otm_strikes"]) == 5
        assert selection["ce_otm_strikes"][0] > selection["atm"]
        assert selection["pe_otm_strikes"][0] < selection["atm"]
        limited = c.get("/api/chain/live", params={
            "asset": asset, "expiry": exp, "otm_count": 2
        }).json()["selection"]
        assert len(limited["ce_otm_strikes"]) == 2
        assert len(limited["pe_otm_strikes"]) == 2
        g = c.get("/api/greeks/live", params={
            "asset": asset, "expiries": ",".join(c.get("/api/expiries", params={"asset": asset}).json()[:2]), "depth": 5
        }).json()
        assert len(g["expiries"]) == 2
        assert g["current"]["sums"]["CE"]["strikes_used"] == 12


def test_bad_asset():
    assert c.get("/api/expiries", params={"asset": "NIFTY"}).status_code == 404
