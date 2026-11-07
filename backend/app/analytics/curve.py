"""Par-curve bootstrapping, curve-based bond pricing, Z-spread and scenario shocks.

Methodology (ENGINE_VERSION; every API response echoes these labels):

* Input: observed par yields (bond-equivalent, semiannual) at sourced tenors. Par yields are
  never used directly as discount rates.
* Short end: tenors up to 6M are single-payment instruments, so their par yield equals the
  semiannually compounded zero rate.
* Bootstrap: par yields are linearly interpolated (in tenor) onto a semiannual grid
  0.5y, 1.0y, ... up to the longest observed tenor. Each grid point is treated as a par bond
  with idealised 0.5y coupon periods; discount factors are solved node by node.
* Interpolation between nodes: linear in log discount factor (piecewise-flat forwards).
* Extrapolation: none. Cash flows beyond the longest observed tenor are rejected.
* Curve time: ACT/365F year fraction from the settlement date.
* Spread: Z-spread, a constant added to the semiannually compounded zero rate, calibrated so
  the curve price equals the quoted dirty price on the base date.
* Shocks: applied to observed par yields; between shock nodes the bp shock is linearly
  interpolated in tenor, flat beyond the first/last node. The curve is then re-bootstrapped.
"""

import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date

from app.analytics.bond import FixedRateBond, accrued_interest, future_flows

ENGINE_VERSION = "curve-engine/2.0.0"
METHOD = {
    "curve_input": "observed par yields, bond-equivalent semiannual",
    "bootstrap": "semiannual par grid, linear-in-tenor par interpolation",
    "short_end": "tenors <= 6M treated as semiannual zero rates",
    "interpolation": "log-linear discount factors (piecewise-flat forwards)",
    "extrapolation": "none; flows beyond the longest observed tenor are rejected",
    "time_basis": "ACT/365F from settlement",
    "spread": "Z-spread added to the semiannual zero rate",
    "shock_interpolation": "linear in tenor between nodes, flat outside",
}
BUMP = 1e-4  # 1bp for effective duration / convexity / DV01


class CurveError(ValueError):
    """Unsupported curve, tenor or instrument combination (actionable message)."""


@dataclass(frozen=True)
class ParCurve:
    tenors: tuple[float, ...]  # years, ascending, unique
    par_yields: tuple[float, ...]  # decimals

    @staticmethod
    def from_points(points: list[tuple[float, float]]) -> "ParCurve":
        if len(points) < 2:
            raise CurveError("a curve needs at least two observed tenors")
        pts = sorted(points)
        tenors = tuple(t for t, _ in pts)
        if len(set(tenors)) != len(tenors) or tenors[0] <= 0:
            raise CurveError("tenors must be positive and unique")
        if tenors[-1] < 0.5:
            raise CurveError("curve must extend to at least 6M to bootstrap")
        return ParCurve(tenors, tuple(y for _, y in pts))

    def par_at(self, t: float) -> float:
        ts, ys = self.tenors, self.par_yields
        if t <= ts[0]:
            return ys[0]
        i = bisect_left(ts, t)
        if i < len(ts) and ts[i] == t:
            return ys[i]
        w = (t - ts[i - 1]) / (ts[i] - ts[i - 1])
        return ys[i - 1] + w * (ys[i] - ys[i - 1])

    def shocked(self, nodes: list[tuple[float, float]]) -> "ParCurve":
        return ParCurve(
            self.tenors,
            tuple(
                y + shock_at(nodes, t) for t, y in zip(self.tenors, self.par_yields, strict=True)
            ),
        )


def shock_at(nodes: list[tuple[float, float]], t: float) -> float:
    """Shock (decimal) at tenor t from (tenor_years, bp) nodes."""
    if not nodes:
        return 0.0
    pts = sorted(nodes)
    if t <= pts[0][0]:
        return pts[0][1] * 1e-4
    if t >= pts[-1][0]:
        return pts[-1][1] * 1e-4
    for (t0, b0), (t1, b1) in zip(pts, pts[1:], strict=False):
        if t <= t1:
            return (b0 + (t - t0) / (t1 - t0) * (b1 - b0)) * 1e-4
    raise AssertionError("unreachable")


@dataclass(frozen=True)
class ZeroCurve:
    times: tuple[float, ...]  # includes 0.0
    log_dfs: tuple[float, ...]

    @property
    def max_time(self) -> float:
        return self.times[-1]

    def df(self, t: float) -> float:
        if t < 0:
            raise CurveError("negative curve time")
        if t > self.max_time + 1e-9:
            raise CurveError(
                f"cash flow at {t:.2f}y is beyond the longest observed tenor "
                f"({self.max_time:.2f}y); extrapolation is disabled"
            )
        ts = self.times
        i = bisect_left(ts, t)
        if i < len(ts) and ts[i] == t:
            return math.exp(self.log_dfs[i])
        i = min(i, len(ts) - 1)
        w = (t - ts[i - 1]) / (ts[i] - ts[i - 1])
        return math.exp(self.log_dfs[i - 1] + w * (self.log_dfs[i] - self.log_dfs[i - 1]))

    def zero_rate(self, t: float) -> float:
        """Semiannually compounded zero rate."""
        if t <= 0:
            t = 1e-6
        return 2 * (self.df(t) ** (-1 / (2 * t)) - 1)


def bootstrap(par: ParCurve) -> ZeroCurve:
    nodes: dict[float, float] = {0.0: 1.0}
    for t, y in zip(par.tenors, par.par_yields, strict=True):
        if t < 0.5:
            nodes[t] = (1 + y / 2) ** (-2 * t)
    n_max = int(math.floor(par.tenors[-1] * 2 + 1e-9))
    annuity = 0.0
    for n in range(1, n_max + 1):
        t = n / 2
        c = par.par_at(t)
        df = (1 - c / 2 * annuity) / (1 + c / 2)
        if df <= 0:
            raise CurveError(f"bootstrap failed at {t}y: non-positive discount factor")
        nodes[t] = df
        annuity += df
    last = par.tenors[-1]
    if last not in nodes:  # odd final tenor: price a par bond to the exact final tenor
        raise CurveError("longest tenor must be a multiple of 6M")
    times = tuple(sorted(nodes))
    return ZeroCurve(times, tuple(math.log(nodes[t]) for t in times))


def year_frac(settle: date, d: date) -> float:
    return (d - settle).days / 365.0


def curve_dirty_price(bond: FixedRateBond, settle: date, zc: ZeroCurve, z: float = 0.0) -> float:
    total = 0.0
    for cf in future_flows(bond, settle):
        t = year_frac(settle, cf.date)
        r = zc.zero_rate(t) + z
        total += cf.amount * (1 + r / 2) ** (-2 * t)
    return total


def solve_z_spread(
    bond: FixedRateBond, settle: date, zc: ZeroCurve, dirty: float, tol: float = 1e-10
) -> float:
    lo, hi = -0.2, 0.5
    f_lo = curve_dirty_price(bond, settle, zc, lo) - dirty
    f_hi = curve_dirty_price(bond, settle, zc, hi) - dirty
    if f_lo * f_hi > 0:
        raise CurveError(f"cannot calibrate Z-spread to price {dirty:.4f}")
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = curve_dirty_price(bond, settle, zc, mid) - dirty
        if abs(f_mid) < tol or hi - lo < tol:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    raise CurveError("Z-spread solver did not converge")


@dataclass(frozen=True)
class Valuation:
    clean: float
    dirty: float
    accrued: float
    effective_duration: float
    effective_convexity: float
    dv01: float  # signed dP (dirty, per 100 face) for a +1bp parallel par-curve move


def value(bond: FixedRateBond, settle: date, par: ParCurve, z: float) -> Valuation:
    """Curve valuation plus effective risk from +/-1bp parallel shifts of the par curve."""
    zc = bootstrap(par)
    p0 = curve_dirty_price(bond, settle, zc, z)
    p_up = curve_dirty_price(bond, settle, bootstrap(par.shocked([(1.0, 1.0)])), z)
    p_dn = curve_dirty_price(bond, settle, bootstrap(par.shocked([(1.0, -1.0)])), z)
    ai = accrued_interest(bond, settle)
    return Valuation(
        clean=p0 - ai,
        dirty=p0,
        accrued=ai,
        effective_duration=(p_dn - p_up) / (2 * p0 * BUMP),
        effective_convexity=(p_dn + p_up - 2 * p0) / (p0 * BUMP**2),
        dv01=(p_up - p_dn) / 2,
    )
