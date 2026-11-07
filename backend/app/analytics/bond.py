"""Fixed-rate bullet bond pricing (street convention).

Scope (M0): fixed-rate, bullet, non-defaulted bonds; no ex-coupon rules; settlement date
is supplied by the caller (no holiday calendar yet). Yields are decimals (0.045 = 4.5%)
compounded at the coupon frequency. Zero-coupon bonds (frequency 0) use semiannual
compounding with ACT/365 year fractions. M1 extends this and validates against QuantLib.
"""

import calendar
from dataclasses import dataclass
from datetime import date


class BondTermsError(ValueError):
    """Raised when terms are incomplete or inconsistent for the requested calculation."""


@dataclass(frozen=True)
class FixedRateBond:
    issue_date: date
    maturity_date: date
    coupon_rate: float  # decimal, 0.05 = 5%
    frequency: int  # 0, 1, 2, 4, 12
    day_count: str = "30/360"  # "30/360" | "ACT/ACT"
    face: float = 100.0

    def __post_init__(self) -> None:
        if self.maturity_date <= self.issue_date:
            raise BondTermsError("maturity_date must be after issue_date")
        if self.frequency not in (0, 1, 2, 4, 12):
            raise BondTermsError(f"unsupported frequency {self.frequency}")
        if self.day_count not in ("30/360", "ACT/ACT"):
            raise BondTermsError(f"unsupported day count {self.day_count}")
        if self.frequency == 0 and self.coupon_rate != 0:
            raise BondTermsError("frequency 0 requires a zero coupon")


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def coupon_dates(bond: FixedRateBond) -> list[date]:
    """Coupon dates generated backward from maturity; a short first period if irregular."""
    if bond.frequency == 0:
        return [bond.maturity_date]
    step = 12 // bond.frequency
    dates, k = [], 0
    while True:
        d = add_months(bond.maturity_date, -step * k)
        if d <= bond.issue_date:
            break
        dates.append(d)
        k += 1
    return sorted(dates)


def _days_30_360(d1: date, d2: date) -> int:
    day1, day2 = min(d1.day, 30), d2.day
    if day1 == 30 and day2 == 31:
        day2 = 30
    return 360 * (d2.year - d1.year) + 30 * (d2.month - d1.month) + (day2 - day1)


def _period_fraction(bond: FixedRateBond, start: date, end: date, period_end: date) -> float:
    """Fraction of the regular coupon period [prev, period_end] elapsed between start and end."""
    period_start = add_months(period_end, -12 // bond.frequency)
    if bond.day_count == "30/360":
        return _days_30_360(start, end) / _days_30_360(period_start, period_end)
    return (end - start).days / (period_end - period_start).days


def _prev_next(bond: FixedRateBond, settle: date) -> tuple[date, date, list[date]]:
    dates = coupon_dates(bond)
    future = [d for d in dates if d > settle]
    if not future:
        raise BondTermsError("settlement is on or after maturity")
    nxt = future[0]
    past = [d for d in dates if d <= settle]
    prev = past[-1] if past else bond.issue_date
    return prev, nxt, future


def accrued_interest(bond: FixedRateBond, settle: date) -> float:
    if bond.frequency == 0:
        return 0.0
    prev, nxt, _ = _prev_next(bond, settle)
    coupon = bond.face * bond.coupon_rate / bond.frequency
    return coupon * _period_fraction(bond, prev, settle, nxt)


def dirty_price(bond: FixedRateBond, settle: date, ytm: float) -> float:
    if settle < bond.issue_date:
        raise BondTermsError("settlement before issue date")
    if bond.frequency == 0:
        if settle >= bond.maturity_date:
            raise BondTermsError("settlement is on or after maturity")
        t = (bond.maturity_date - settle).days / 365.0
        return bond.face / (1 + ytm / 2) ** (2 * t)
    f = bond.frequency
    _, nxt, future = _prev_next(bond, settle)
    w = _period_fraction(bond, settle, nxt, nxt)  # fraction of period until next coupon
    coupon = bond.face * bond.coupon_rate / f
    base = 1 + ytm / f
    if base <= 0:
        raise BondTermsError("yield below -100% per period")
    pv = 0.0
    for k, _d in enumerate(future):
        cf = coupon + (bond.face if k == len(future) - 1 else 0.0)
        pv += cf / base ** (w + k)
    return pv


def clean_price(bond: FixedRateBond, settle: date, ytm: float) -> float:
    return dirty_price(bond, settle, ytm) - accrued_interest(bond, settle)


def yield_from_clean_price(
    bond: FixedRateBond, settle: date, price: float, tol: float = 1e-12, max_iter: int = 200
) -> float:
    """Solve clean price -> YTM by bisection on a bracket (price is monotone in yield)."""
    lo, hi = -0.5, 2.0
    f_lo = clean_price(bond, settle, lo) - price
    f_hi = clean_price(bond, settle, hi) - price
    if f_lo * f_hi > 0:
        raise BondTermsError(f"price {price} outside solvable range")
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = clean_price(bond, settle, mid) - price
        if abs(f_mid) < tol or (hi - lo) / 2 < tol:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    raise BondTermsError("YTM solver did not converge")
