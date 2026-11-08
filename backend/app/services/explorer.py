"""Read models for the three public features: Bond Explorer, Yield Curve, Price Simulator."""

from datetime import date
from decimal import Decimal
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.bond import (
    BondTermsError,
    accrued_interest,
    clean_price,
    yield_from_clean_price,
    yield_risk,
)
from app.analytics.curve import year_frac
from app.models import CurvePoint, Issuer, Security
from app.services import market as mk
from app.services.analytics import (
    ServiceError,
    curve_on,
    latest_quote_date,
    quote_on,
    security_or_404,
    to_bond,
)

MATURITY_BUCKETS = {"0-3y": (0, 3), "3-7y": (3, 7), "7-10y": (7, 10), "10y+": (10, 100)}
SORT_KEYS = {
    "id",
    "issuer_name",
    "rating",
    "coupon_rate",
    "maturity_date",
    "years",
    "mid_price",
    "mid_yield_pct",
    "modified_duration",
    "g_spread_bp",
}
RATING_ORDER = {"AAA": 0, "AA": 1, "A": 2, "BBB": 3, "BB": 4, "B": 5}


def list_bonds(
    db: Session,
    *,
    q: str | None,
    bond_type: str | None,
    sectors: list[str],
    ratings: list[str],
    maturity: str | None,
    min_yield: float | None,
    max_yield: float | None,
    sort: str,
    page: int,
    page_size: int,
) -> dict:
    stmt, quotes, rat = mk.security_query()
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(Security.name).like(like)
            | func.lower(Issuer.name).like(like)
            | func.lower(Security.id).like(like)
            | func.lower(Issuer.sector).like(like)
        )
    if bond_type:
        stmt = stmt.where(Security.bond_type == bond_type)
    if sectors:
        stmt = stmt.where(Issuer.sector.in_(sectors))
    if ratings:
        stmt = stmt.where(rat.c.rating.in_(ratings))
    if min_yield is not None:
        stmt = stmt.where(quotes.c.mid_yield_pct >= min_yield)
    if max_yield is not None:
        stmt = stmt.where(quotes.c.mid_yield_pct <= max_yield)
    rows = db.execute(stmt).all()

    curves: dict[date, object] = {}
    items = []
    for row in rows:
        item = {
            k: float(v) if isinstance(v, Decimal) else v for k, v in mk.row_to_summary(row).items()
        }
        item["years"] = None
        item["modified_duration"] = None
        item["g_spread_bp"] = None
        d = row.quote_as_of
        if d is not None and row.mid_price is not None:
            sec: Security = row.Security
            item["years"] = round(year_frac(d, sec.maturity_date), 4)
            try:
                bond = to_bond(sec)
                ytm = float(row.mid_yield_pct) / 100
                item["modified_duration"] = yield_risk(bond, d, ytm).modified_duration
                if d not in curves:
                    try:
                        curves[d] = curve_on(db, "USD-UST-PAR", d).par
                    except ServiceError:
                        curves[d] = None
                if curves[d] is not None:
                    item["g_spread_bp"] = (ytm - curves[d].par_at(item["years"])) * 1e4
            except (ServiceError, BondTermsError):
                pass  # unsupported instruments keep None: shown as unavailable, never guessed
        if maturity in MATURITY_BUCKETS:
            lo, hi = MATURITY_BUCKETS[maturity]
            if item["years"] is None or not lo <= item["years"] < hi:
                continue
        items.append(item)

    key, desc = sort.lstrip("-"), sort.startswith("-")
    if key not in SORT_KEYS:
        raise ServiceError(
            422, "invalid_sort", f"cannot sort by {key!r}", {"allowed": sorted(SORT_KEYS)}
        )

    def sort_value(it):
        v = it.get(key)
        if key == "rating":
            v = RATING_ORDER.get(v, 99) if v else None
        return v

    present = [it for it in items if sort_value(it) is not None]
    missing = [it for it in items if sort_value(it) is None]
    present.sort(key=lambda it: (sort_value(it), it["id"]), reverse=desc)
    ordered = present + sorted(missing, key=lambda it: it["id"])

    def avg(field):
        vals = [float(it[field]) for it in items if it.get(field) is not None]
        return mean(vals) if vals else None

    sectors_all = sorted(db.scalars(select(Issuer.sector).distinct()))
    start = (page - 1) * page_size
    return {
        "items": ordered[start : start + page_size],
        "total": len(items),
        "page": page,
        "page_size": page_size,
        "stats": {
            "count": len(items),
            "avg_ytm_pct": avg("mid_yield_pct"),
            "avg_modified_duration": avg("modified_duration"),
            "avg_g_spread_bp": avg("g_spread_bp"),
            "avg_coupon_pct": avg("coupon_rate"),
        },
        "facets": {
            "sectors": sectors_all,
            "ratings": list(RATING_ORDER)[:5],
            "maturity_buckets": list(MATURITY_BUCKETS),
            "bond_types": ["treasury", "corporate"],
        },
        "as_of": mk.market_date(db),
        "is_synthetic": True,
    }


def curve_series(
    db: Session, curve_id: str, tenors: list[float], start: date | None, end: date | None
) -> dict:
    stmt = select(CurvePoint.as_of, CurvePoint.tenor_months, CurvePoint.yield_pct).where(
        CurvePoint.curve_id == curve_id, CurvePoint.tenor_months.in_(tenors)
    )
    if start:
        stmt = stmt.where(CurvePoint.as_of >= start)
    if end:
        stmt = stmt.where(CurvePoint.as_of <= end)
    by_date: dict[date, dict[float, float]] = {}
    for d, t, y in db.execute(stmt.order_by(CurvePoint.as_of)):
        by_date.setdefault(d, {})[float(t)] = float(y)
    dates = sorted(by_date)
    return {
        "curve_id": curve_id,
        "dates": dates,
        "series": {f"{t:g}": [by_date[d].get(t) for d in dates] for t in tenors},
        "units": "percent",
    }


def price_yield(db: Session, security_id: str, range_bp: int, step_bp: int) -> dict:
    """Exact price-yield relationship around the bond's market yield, plus the duration and
    duration+convexity approximations at every point (for the Price Simulator)."""
    sec = security_or_404(db, security_id)
    bond = to_bond(sec)
    d = latest_quote_date(db, security_id)
    if d is None:
        raise ServiceError(422, "no_quote", f"{security_id} has no quotes")
    quote = quote_on(db, security_id, d)
    settle = quote.as_of
    clean0 = float(quote.mid_price)
    ytm0 = yield_from_clean_price(bond, settle, clean0)
    ai = accrued_interest(bond, settle)
    dirty0 = clean0 + ai
    risk = yield_risk(bond, settle, ytm0)
    points = []
    for shift in range(-range_bp, range_bp + 1, step_bp):
        dy = shift * 1e-4
        y = ytm0 + dy
        if y <= -0.05:
            continue
        exact = clean_price(bond, settle, y)
        dur_est = clean0 - risk.modified_duration * dirty0 * dy
        conv_est = dur_est + 0.5 * risk.convexity * dirty0 * dy * dy
        points.append(
            {
                "shift_bp": shift,
                "ytm_pct": y * 100,
                "clean": exact,
                "duration_estimate": dur_est,
                "convexity_estimate": conv_est,
            }
        )
    return {
        "security_id": sec.id,
        "name": sec.name,
        "is_synthetic": sec.is_synthetic,
        "as_of": settle,
        "coupon_pct": float(sec.coupon_rate),
        "maturity_date": sec.maturity_date,
        "base": {
            "ytm_pct": ytm0 * 100,
            "clean": clean0,
            "dirty": dirty0,
            "accrued": ai,
            "modified_duration": risk.modified_duration,
            "macaulay_duration": risk.macaulay_duration,
            "convexity": risk.convexity,
            "dv01": risk.dv01,
        },
        "points": points,
        "method": {
            "pricing": "exact: discount every remaining cash flow at the new yield "
            "(street convention, compounded at the coupon frequency)",
            "duration_estimate": "P0 - D_mod x P0_dirty x dy (straight tangent line)",
            "convexity_estimate": "adds + 1/2 x C x P0_dirty x dy^2 (curvature correction)",
            "settlement": f"T+0 on the quote date {settle}",
        },
    }
