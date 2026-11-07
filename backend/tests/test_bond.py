from datetime import date

import pytest

from app.analytics.bond import (
    BondTermsError,
    FixedRateBond,
    accrued_interest,
    clean_price,
    coupon_dates,
    yield_from_clean_price,
)

BOND = FixedRateBond(date(2024, 1, 15), date(2029, 1, 15), 0.05, 2, "30/360")


def test_coupon_schedule_is_regular_semiannual():
    dates = coupon_dates(BOND)
    assert dates[0] == date(2024, 7, 15)
    assert dates[-1] == date(2029, 1, 15)
    assert len(dates) == 10


def test_par_bond_prices_at_par_on_coupon_date():
    assert clean_price(BOND, date(2025, 1, 15), 0.05) == pytest.approx(100.0, abs=1e-9)


def test_accrued_interest_half_period_30_360():
    # 15 Jan -> 15 Apr = 90/180 of a 2.5 coupon
    assert accrued_interest(BOND, date(2025, 4, 15)) == pytest.approx(1.25, abs=1e-12)


def test_premium_and_discount():
    settle = date(2025, 1, 15)
    assert clean_price(BOND, settle, 0.04) > 100 > clean_price(BOND, settle, 0.06)


def test_yield_round_trip_between_coupons():
    settle = date(2026, 3, 3)
    for y in (-0.005, 0.0, 0.031, 0.08):
        p = clean_price(BOND, settle, y)
        assert yield_from_clean_price(BOND, settle, p) == pytest.approx(y, abs=1e-9)


def test_zero_coupon():
    z = FixedRateBond(date(2025, 1, 1), date(2030, 1, 1), 0.0, 0)
    t = (date(2030, 1, 1) - date(2025, 1, 1)).days / 365.0
    assert clean_price(z, date(2025, 1, 1), 0.04) == pytest.approx(100 / 1.02 ** (2 * t))


def test_rejects_invalid_terms():
    with pytest.raises(BondTermsError):
        FixedRateBond(date(2030, 1, 1), date(2025, 1, 1), 0.05, 2)
    with pytest.raises(BondTermsError):
        clean_price(BOND, date(2029, 1, 15), 0.05)
