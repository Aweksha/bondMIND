import math
from datetime import date

import pytest

from app.analytics.bond import FixedRateBond, accrued_interest, clean_price, yield_risk
from app.analytics.curve import (
    CurveError,
    ParCurve,
    bootstrap,
    curve_dirty_price,
    shock_at,
    solve_z_spread,
    value,
)

TENORS = [1 / 12, 3 / 12, 6 / 12, 1, 2, 3, 5, 7, 10, 20, 30]
UPWARD = ParCurve.from_points(
    list(
        zip(
            TENORS,
            [
                0.0430,
                0.0425,
                0.0415,
                0.0400,
                0.0385,
                0.0380,
                0.0385,
                0.0395,
                0.0410,
                0.0445,
                0.0450,
            ],
            strict=True,
        )
    )
)
BOND = FixedRateBond(date(2024, 5, 15), date(2034, 5, 15), 0.0425, 2, "ACT/ACT")
SETTLE = date(2026, 11, 6)


def test_flat_par_curve_gives_flat_zero_curve():
    zc = bootstrap(ParCurve.from_points([(t, 0.05) for t in TENORS]))
    for t in (0.1, 0.5, 1.3, 7.25, 29.9):
        assert zc.zero_rate(t) == pytest.approx(0.05, abs=1e-12)


def test_grid_par_bonds_reprice_to_par():
    zc = bootstrap(UPWARD)
    for n in (1, 4, 14, 20, 60):
        c = UPWARD.par_at(n / 2)
        pv = sum(c / 2 * zc.df(k / 2) for k in range(1, n + 1)) + zc.df(n / 2)
        assert pv == pytest.approx(1.0, abs=1e-12)


def test_discount_factors_decrease_and_par_not_used_as_zero():
    zc = bootstrap(UPWARD)
    dfs = [zc.df(t) for t in (0.25, 1, 5, 10, 20, 30)]
    assert dfs == sorted(dfs, reverse=True)
    # in an upward-sloping long end, zero rates sit above par yields
    assert zc.zero_rate(20) > UPWARD.par_at(20)


def test_no_extrapolation_beyond_last_tenor():
    zc = bootstrap(ParCurve.from_points([(0.5, 0.04), (5, 0.04)]))
    with pytest.raises(CurveError, match="extrapolation is disabled"):
        zc.df(6)


def test_z_spread_round_trip():
    zc = bootstrap(UPWARD)
    market_dirty = clean_price(BOND, SETTLE, 0.0455) + accrued_interest(BOND, SETTLE)
    z = solve_z_spread(BOND, SETTLE, zc, market_dirty)
    assert curve_dirty_price(BOND, SETTLE, zc, z) == pytest.approx(market_dirty, abs=1e-8)
    assert 0.002 < z < 0.008


def test_shock_interpolation():
    nodes = [(2, -25), (10, 50)]
    assert shock_at(nodes, 1) == pytest.approx(-0.0025)
    assert shock_at(nodes, 6) == pytest.approx(0.00125)
    assert shock_at(nodes, 30) == pytest.approx(0.005)
    assert shock_at([(1, 50)], 17) == pytest.approx(0.005)


def test_valuation_risk_is_consistent():
    v0 = value(BOND, SETTLE, UPWARD, 0.003)
    v_up = value(BOND, SETTLE, UPWARD.shocked([(1, 50)]), 0.003)
    assert v_up.dirty < v0.dirty
    assert v0.dv01 < 0
    # duration + convexity approximation is close to full repricing for +50bp
    approx = v0.dirty * (-v0.effective_duration * 0.005 + 0.5 * v0.effective_convexity * 0.005**2)
    assert v_up.dirty - v0.dirty == pytest.approx(approx, rel=2e-3)
    # effective duration near analytic modified duration at the bond's own yield
    ytm_mod = yield_risk(BOND, SETTLE, 0.0455).modified_duration
    assert v0.effective_duration == pytest.approx(ytm_mod, rel=0.03)
    assert v0.clean == pytest.approx(v0.dirty - v0.accrued)
    assert math.isfinite(v0.effective_convexity) and v0.effective_convexity > 0
