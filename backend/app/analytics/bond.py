"""Fixed-rate bullet bond: cash flows and yield-based measures (street convention).

Scope: fixed-rate, bullet, non-defaulted bonds; no ex-coupon rules; unadjusted coupon dates
(no holiday calendar); settlement date supplied by the caller. Yields are decimals
(0.045 = 4.5%) compounded at the coupon frequency. A short first coupon is pro-rated using
the ICMA reference period. Zero-coupon bonds (frequency 0) use semiannual compounding with
ACT/365 year fractions. Validated against QuantLib in tests/test_golden_quantlib.py.
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
    day_count: str = "30/360"  # "30/360" (bond basis) | "ACT/ACT" (ICMA)
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


@dataclass(frozen=True)
class CashFlow:
    date: date
    amount: float
    accrual_start: date
    is_principal: bool = False


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


def days_30_360(d1: date, d2: date) -> int:
    day1, day2 = min(d1.day, 30), d2.day
    if day1 == 30 and day2 == 31:
        day2 = 30
    return 360 * (d2.year - d1.year) + 30 * (d2.month - d1.month) + (day2 - day1)


def period_fraction(bond: FixedRateBond, start: date, end: date, period_end: date) -> float:
    """Fraction of the regular (reference) coupon period ending at period_end, start->end."""
    period_start = add_months(period_end, -12 // bond.frequency)
    if bond.day_count == "30/360":
        return days_30_360(start, end) / days_30_360(period_start, period_end)
    return (end - start).days / (period_end - period_start).days


def cash_flows(bond: FixedRateBond) -> list[CashFlow]:
    """All contractual cash flows. The first coupon is pro-rated if the period is short."""
    if bond.frequency == 0:
        return [CashFlow(bond.maturity_date, bond.face, bond.issue_date, True)]
    regular = bond.face * bond.coupon_rate / bond.frequency
    flows, prev = [], bond.issue_date
    dates = coupon_dates(bond)
    for i, d in enumerate(dates):
        amount = regular * period_fraction(bond, prev, d, d) if i == 0 else regular
        flows.append(CashFlow(d, amount, prev))
        prev = d
    flows.append(CashFlow(bond.maturity_date, bond.face, bond.maturity_date, True))
    return flows


def future_flows(bond: FixedRateBond, settle: date) -> list[CashFlow]:
    if settle < bond.issue_date:
        raise BondTermsError("settlement before issue date")
    flows = [cf for cf in cash_flows(bond) if cf.date > settle]
    if not flows:
        raise BondTermsError("settlement is on or after maturity")
    return flows


def accrued_interest(bond: FixedRateBond, settle: date) -> float:
    if bond.frequency == 0:
        return 0.0
    nxt = next(cf for cf in future_flows(bond, settle) if not cf.is_principal)
    coupon = bond.face * bond.coupon_rate / bond.frequency
    return coupon * period_fraction(bond, nxt.accrual_start, settle, nxt.date)


def _periods(bond: FixedRateBond, settle: date) -> list[tuple[float, float]]:
    """(time in coupon periods, amount) for each future flow under street convention."""
    flows = future_flows(bond, settle)
    if bond.frequency == 0:
        t = (bond.maturity_date - settle).days / 365.0
        return [(2 * t, bond.face)]
    first_coupon = next(cf for cf in flows if not cf.is_principal)
    w = period_fraction(bond, settle, first_coupon.date, first_coupon.date)
    coupon_dates_ahead = sorted({cf.date for cf in flows})
    index = {d: k for k, d in enumerate(coupon_dates_ahead)}
    return [(w + index[cf.date], cf.amount) for cf in flows]


def _compounding(bond: FixedRateBond) -> int:
    return bond.frequency or 2


def dirty_price(bond: FixedRateBond, settle: date, ytm: float) -> float:
    base = 1 + ytm / _compounding(bond)
    if base <= 0:
        raise BondTermsError("yield below -100% per period")
    return sum(cf / base**tau for tau, cf in _periods(bond, settle))


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


@dataclass(frozen=True)
class YieldRisk:
    """Analytic yield-based measures. Durations in years; DV01 per 100 face, signed."""

    macaulay_duration: float
    modified_duration: float
    convexity: float
    dv01: float  # dP_dirty for +1bp in yield (negative for a long position)


def yield_risk(bond: FixedRateBond, settle: date, ytm: float) -> YieldRisk:
    f = _compounding(bond)
    base = 1 + ytm / f
    periods = _periods(bond, settle)
    price = sum(cf / base**tau for tau, cf in periods)
    mac = sum((tau / f) * cf / base**tau for tau, cf in periods) / price
    conv = sum(cf * (tau / f) * (tau / f + 1 / f) / base ** (tau + 2) for tau, cf in periods)
    mod = mac / base
    return YieldRisk(mac, mod, conv / price, -mod * price * 1e-4)
