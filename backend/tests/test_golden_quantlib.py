"""Golden tests: our bond analytics vs QuantLib (an independent implementation).

QuantLib is a test-only dependency. Conventions mirrored on both sides: unadjusted dates,
backward schedule generation, settlement = valuation date, yield compounded semiannually.
"""

from datetime import date

import pytest

ql = pytest.importorskip("QuantLib")

from app.analytics.bond import (  # noqa: E402
    FixedRateBond,
    accrued_interest,
    cash_flows,
    clean_price,
    yield_from_clean_price,
    yield_risk,
)

CASES = [
    # issue, maturity, coupon, day count, settle, ytm
    (date(2024, 1, 15), date(2029, 1, 15), 0.05, "30/360", date(2026, 3, 3), 0.043),
    (date(2024, 1, 15), date(2029, 1, 15), 0.05, "ACT/ACT", date(2026, 3, 3), 0.061),
    (date(2023, 3, 31), date(2033, 9, 30), 0.0375, "ACT/ACT", date(2026, 8, 31), 0.0412),
    # short first coupon (stub), settle inside the stub
    (date(2026, 2, 10), date(2031, 6, 15), 0.045, "30/360", date(2026, 4, 1), 0.05),
    (date(2026, 2, 10), date(2031, 6, 15), 0.045, "ACT/ACT", date(2026, 4, 1), 0.05),
    # deep premium, long, near-zero and negative yields, near maturity
    (date(2020, 5, 15), date(2050, 5, 15), 0.0625, "ACT/ACT", date(2026, 11, 6), 0.0475),
    (date(2021, 7, 1), date(2027, 1, 1), 0.02, "30/360", date(2026, 11, 6), -0.003),
    (date(2022, 2, 28), date(2027, 2, 28), 0.0125, "ACT/ACT", date(2026, 12, 30), 0.0001),
]


def qd(d: date):
    return ql.Date(d.day, d.month, d.year)


def ql_bond(issue, maturity, coupon, dc_name, settle):
    ql.Settings.instance().evaluationDate = qd(settle)
    sched = ql.Schedule(
        qd(issue),
        qd(maturity),
        ql.Period(ql.Semiannual),
        ql.NullCalendar(),
        ql.Unadjusted,
        ql.Unadjusted,
        ql.DateGeneration.Backward,
        False,
    )
    dc = (
        ql.Thirty360(ql.Thirty360.BondBasis)
        if dc_name == "30/360"
        else ql.ActualActual(ql.ActualActual.ISMA, sched)
    )
    return ql.FixedRateBond(0, 100.0, sched, [coupon], dc), dc


@pytest.mark.parametrize("issue,maturity,coupon,dc_name,settle,ytm", CASES)
def test_matches_quantlib(issue, maturity, coupon, dc_name, settle, ytm):
    ours = FixedRateBond(issue, maturity, coupon, 2, dc_name)
    qb, dc = ql_bond(issue, maturity, coupon, dc_name, settle)
    s = qd(settle)
    args = (dc, ql.Compounded, ql.Semiannual, s)

    q_clean = ql.BondFunctions.cleanPrice(qb, ytm, *args)
    assert clean_price(ours, settle, ytm) == pytest.approx(q_clean, abs=1e-9)
    assert accrued_interest(ours, settle) == pytest.approx(qb.accruedAmount(s), abs=1e-9)

    q_yield = ql.BondFunctions.bondYield(qb, ql.BondPrice(q_clean, ql.BondPrice.Clean), *args)
    assert yield_from_clean_price(ours, settle, q_clean) == pytest.approx(q_yield, abs=1e-8)

    risk = yield_risk(ours, settle, ytm)
    q_mod = ql.BondFunctions.duration(
        qb, ytm, dc, ql.Compounded, ql.Semiannual, ql.Duration.Modified, s
    )
    q_mac = ql.BondFunctions.duration(
        qb, ytm, dc, ql.Compounded, ql.Semiannual, ql.Duration.Macaulay, s
    )
    q_conv = ql.BondFunctions.convexity(qb, ytm, *args)
    assert risk.modified_duration == pytest.approx(q_mod, rel=1e-9)
    assert risk.macaulay_duration == pytest.approx(q_mac, rel=1e-9)
    assert risk.convexity == pytest.approx(q_conv, rel=1e-8)
    q_bpv = ql.BondFunctions.basisPointValue(qb, ytm, *args)  # dirty dP for +1bp
    assert risk.dv01 == pytest.approx(q_bpv, rel=1e-3)


@pytest.mark.parametrize("issue,maturity,coupon,dc_name,settle,ytm", CASES)
def test_cash_flow_schedule_matches_quantlib(issue, maturity, coupon, dc_name, settle, ytm):
    ours = [
        (cf.date, round(cf.amount, 10))
        for cf in cash_flows(FixedRateBond(issue, maturity, coupon, 2, dc_name))
    ]
    qb, _ = ql_bond(issue, maturity, coupon, dc_name, settle)
    theirs = [
        (date(c.date().year(), c.date().month(), c.date().dayOfMonth()), round(c.amount(), 10))
        for c in qb.cashflows()
    ]
    assert ours == theirs
