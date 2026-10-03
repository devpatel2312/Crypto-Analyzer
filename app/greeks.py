"""Pure functions - no network.  This is the core of the 3-table greeks page.

Definitions
-----------
* ATM strike  : strike nearest to the underlying price.
* CE side     : ATM and the `depth` strikes ABOVE it   (ATM -> OTM calls)
* PE side     : ATM and the `depth` strikes BELOW it   (ATM -> OTM puts)
* Table 1     : sums using the opening underlying price (ATM chosen at open) and opening greeks
* Table 2     : sums using the current/selected underlying price and greeks
* Table 3     : Table 2 - Table 1
"""
from typing import Optional

GREEKS = ("delta", "theta", "vega")


def nearest_strike(strikes, price: float) -> Optional[float]:
    return min(strikes, key=lambda s: abs(s - price)) if strikes else None


def select_strikes(strikes, atm, depth):
    """Return (ce_strikes, pe_strikes) from ATM to OTM, `depth` strikes beyond ATM."""
    ordered = sorted(strikes)
    if atm not in ordered:
        return [], []
    i = ordered.index(atm)
    return ordered[i:i + depth + 1], ordered[max(0, i - depth):i + 1][::-1]


def _available_side_strikes(strikes, atm, side, depth):
    available = sorted(set(strikes))
    if atm is None:
        return []
    selected = [atm] if atm in available else []
    if side == "CE":
        return selected + [strike for strike in available if strike > atm][:depth]
    below_atm = [strike for strike in available if strike < atm]
    return selected + (below_atm[-depth:][::-1] if depth else [])


def strike_selection(rows, spot: float, otm_count: int):
    """Select ATM and available OTM strikes independently from an expiry's chain."""
    strikes = sorted({r["strike"] for r in rows if r.get("ce") or r.get("pe")})
    atm = nearest_strike(strikes, spot)
    ce_available = [r["strike"] for r in rows if r.get("ce")]
    pe_available = [r["strike"] for r in rows if r.get("pe")]
    ce_strikes = _available_side_strikes(ce_available, atm, "CE", otm_count)
    pe_strikes = _available_side_strikes(pe_available, atm, "PE", otm_count)
    intervals = [b - a for a, b in zip(strikes, strikes[1:]) if b > a]
    return {
        "atm": atm,
        "strike_interval": min(intervals) if intervals else None,
        "requested_otm_count": otm_count,
        "ce_strikes": ce_strikes,
        "pe_strikes": pe_strikes,
        "ce_otm_strikes": [strike for strike in ce_strikes if atm is not None and strike > atm],
        "pe_otm_strikes": [strike for strike in pe_strikes if atm is not None and strike < atm],
    }


def sum_greeks(rows, atm, depth, selected_strikes=None):
    """rows: [{'strike': float, 'ce': {...}|None, 'pe': {...}|None}]"""
    by_strike = {r["strike"]: r for r in rows}
    if selected_strikes:
        chosen = [s for s in selected_strikes if s in by_strike]
        ce_s, pe_s = chosen, chosen
    else:
        ce_s = _available_side_strikes(
            [r["strike"] for r in rows if r.get("ce")], atm, "CE", depth)
        pe_s = _available_side_strikes(
            [r["strike"] for r in rows if r.get("pe")], atm, "PE", depth)
    out = {}
    for side, strikes in (("CE", ce_s), ("PE", pe_s)):
        key = side.lower()
        tot = {g: 0.0 for g in GREEKS}
        used = 0
        for s in strikes:
            leg = by_strike[s].get(key)
            if not leg:
                continue
            vals = [leg.get(g) for g in GREEKS]
            if any(v is None for v in vals):
                continue
            for g, v in zip(GREEKS, vals):
                tot[g] += v
            used += 1
        out[side] = {**{g: round(v, 4) for g, v in tot.items()},
                     "strikes_used": used,
                     "from_strike": strikes[0] if strikes else None,
                     "to_strike": strikes[-1] if strikes else None}
    return out


def table(rows, spot, depth, atm=None, selected_strikes=None):
    strikes = [r["strike"] for r in rows]
    atm = atm if atm is not None else nearest_strike(strikes, spot)
    return {"spot": spot, "atm": atm, "depth": depth, "selected_strikes": selected_strikes or [], "sums": sum_greeks(rows, atm, depth, selected_strikes)}



def aggregate_tables(tables):
    """Sum Greek tables from multiple expiries into one portfolio-style view."""
    if not tables:
        return {"spot": None, "atm": None, "depth": 0, "sums": {
            "CE": {g: 0.0 for g in GREEKS}, "PE": {g: 0.0 for g in GREEKS}}}

    out = {"spot": tables[-1].get("spot"), "atm": tables[-1].get("atm"),
           "depth": tables[-1].get("depth", 0), "sums": {}}
    for side in ("CE", "PE"):
        out["sums"][side] = {g: round(sum((t.get("sums", {}).get(side, {}).get(g) or 0.0) for t in tables), 4)
                              for g in GREEKS}
        out["sums"][side]["strikes_used"] = sum(
            t.get("sums", {}).get(side, {}).get("strikes_used", 0) for t in tables)
        ranges = [t.get("sums", {}).get(side, {}) for t in tables
                  if t.get("sums", {}).get(side, {}).get("strikes_used", 0)]
        out["sums"][side]["from_strike"] = min((x.get("from_strike") for x in ranges if x.get("from_strike") is not None), default=None)
        out["sums"][side]["to_strike"] = max((x.get("to_strike") for x in ranges if x.get("to_strike") is not None), default=None)
    return out

def change(current: dict, opening: dict):
    out = {}
    for side in ("CE", "PE"):
        out[side] = {g: round(current["sums"][side][g] - opening["sums"][side][g], 4) for g in GREEKS}
    return {"spot_change": None if current["spot"] is None or opening["spot"] is None
            else round(current["spot"] - opening["spot"], 2), "sums": out}
