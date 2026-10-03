from app import greeks


def rows():
    out = []
    for k in range(100, 160, 10):   # strikes 100..150
        out.append({"strike": float(k),
                    "ce": {"delta": 0.5, "theta": -1.0, "vega": 2.0},
                    "pe": {"delta": -0.5, "theta": -1.5, "vega": 2.5}})
    return out


def test_nearest_strike():
    assert greeks.nearest_strike([100, 110, 120], 113) == 110


def test_ce_goes_up_pe_goes_down_from_atm():
    ce, pe = greeks.select_strikes([100, 110, 120, 130, 140], 120, 2)
    assert ce == [120, 130, 140]
    assert pe == [120, 110, 100]


def test_strike_selection_uses_available_expiry_strikes():
    first = greeks.strike_selection(
        [{"strike": strike, "ce": {"ref_id": "call"}, "pe": {"ref_id": "put"}}
         for strike in [100, 150, 200, 250, 300]], 190, 2)
    second = greeks.strike_selection(
        [{"strike": strike, "ce": {"ref_id": "call"}, "pe": {"ref_id": "put"}}
         for strike in [125, 175, 225, 275, 325]], 220, 2)
    assert first["atm"] == 200
    assert first["strike_interval"] == 50
    assert first["ce_strikes"] == [200, 250, 300]
    assert first["pe_strikes"] == [200, 150, 100]
    assert second["atm"] == 225
    assert second["ce_strikes"] == [225, 275, 325]
    assert second["pe_strikes"] == [225, 175, 125]


def test_strike_selection_skips_missing_side_contracts():
    rows = [
        {"strike": 100, "ce": {"ref_id": "100C"}, "pe": {"ref_id": "100P"}},
        {"strike": 150, "ce": {"ref_id": "150C"}, "pe": None},
        {"strike": 200, "ce": None, "pe": {"ref_id": "200P"}},
        {"strike": 250, "ce": {"ref_id": "250C"}, "pe": {"ref_id": "250P"}},
    ]
    selection = greeks.strike_selection(rows, 150, 2)
    assert selection["atm"] == 150
    assert selection["ce_strikes"] == [150, 250]
    assert selection["pe_strikes"] == [100]
    assert selection["pe_otm_strikes"] == [100]


def test_sum_and_edges():
    t = greeks.table(rows(), spot=132, depth=2)
    assert t["atm"] == 130.0
    ce, pe = t["sums"]["CE"], t["sums"]["PE"]
    assert ce["strikes_used"] == 3 and pe["strikes_used"] == 3
    assert ce["delta"] == 1.5 and pe["vega"] == 7.5
    # near the edge of the chain fewer strikes exist - must not crash
    t = greeks.table(rows(), spot=150, depth=3)
    assert t["sums"]["CE"]["strikes_used"] == 1


def test_missing_greeks_skipped():
    r = rows()
    r[3]["ce"]["vega"] = None
    t = greeks.table(r, spot=130, depth=1)
    assert t["sums"]["CE"]["strikes_used"] == 1   # 130 skipped, 140 used


def test_change():
    a = greeks.table(rows(), 120, 1)
    b = greeks.table(rows(), 130, 1)
    c = greeks.change(b, a)
    assert c["spot_change"] == 10 and c["sums"]["CE"]["delta"] == 0


def test_crypto_black_scholes_greeks_are_finite():
    from app.crypto_client import _bs_greeks
    import time
    expiry = int((time.time() + 86400 * 30) * 1000)
    g = _bs_greeks(100000, 100000, expiry, 60, "call")
    assert 0 < g["delta"] < 1
    assert g["vega"] > 0
    assert g["gamma"] > 0


def test_aggregate_multiple_expiries():
    a = greeks.table(rows(), 120, 1)
    b = greeks.table(rows(), 130, 1)
    total = greeks.aggregate_tables([a, b])
    assert total["sums"]["CE"]["delta"] == 2.0
    assert total["sums"]["PE"]["vega"] == 10.0
    assert total["sums"]["CE"]["strikes_used"] == 4
