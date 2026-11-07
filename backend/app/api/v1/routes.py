from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.db.session import get_db
from app.models import BenchmarkCurve, DataQualityIssue, Issuer, Security
from app.schemas.common import DataContext, Page
from app.schemas.market import (
    CurveInfo,
    CurveSnapshot,
    DataQualityReport,
    MarketOverview,
    QualityIssueOut,
    SecurityDetail,
    SecuritySummary,
)
from app.services import market as svc

router = APIRouter(prefix="/api/v1")

SORTABLE = {
    "id": Security.id,
    "name": Security.name,
    "maturity_date": Security.maturity_date,
    "coupon_rate": Security.coupon_rate,
}


def ctx(db: Session, as_of: date | None = None) -> DataContext:
    return DataContext(
        is_synthetic=svc.any_synthetic(db),
        as_of=as_of or svc.market_date(db),
        generated_at=svc.now(),
    )


@router.get("/health", tags=["system"])
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(select(1))
    return {"status": "ok", "database": "ok"}


@router.get("/securities", response_model=Page[SecuritySummary], tags=["securities"])
def list_securities(
    db: Session = Depends(get_db),
    q: str | None = Query(None, max_length=100, description="Search name or issuer"),
    bond_type: Literal["treasury", "corporate"] | None = None,
    currency: str | None = Query(None, min_length=3, max_length=3),
    rating: list[str] | None = Query(None),
    sector: list[str] | None = Query(None),
    maturity_from: date | None = None,
    maturity_to: date | None = None,
    min_yield: Decimal | None = None,
    max_yield: Decimal | None = None,
    sort: str = Query("maturity_date", pattern=r"^-?[a-z_]+$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    stmt, quotes, ratings = svc.security_query()
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Security.name).like(like) | func.lower(Issuer.name).like(like))
    if bond_type:
        stmt = stmt.where(Security.bond_type == bond_type)
    if currency:
        stmt = stmt.where(Security.currency == currency.upper())
    if rating:
        stmt = stmt.where(ratings.c.rating.in_(rating))
    if sector:
        stmt = stmt.where(Issuer.sector.in_(sector))
    if maturity_from:
        stmt = stmt.where(Security.maturity_date >= maturity_from)
    if maturity_to:
        stmt = stmt.where(Security.maturity_date <= maturity_to)
    if min_yield is not None:
        stmt = stmt.where(quotes.c.mid_yield_pct >= min_yield)
    if max_yield is not None:
        stmt = stmt.where(quotes.c.mid_yield_pct <= max_yield)

    key, desc = sort.lstrip("-"), sort.startswith("-")
    cols = {
        **SORTABLE,
        "mid_yield_pct": quotes.c.mid_yield_pct,
        "mid_price": quotes.c.mid_price,
        "rating": ratings.c.rating,
    }
    if key not in cols:
        raise ApiError(422, "invalid_sort", f"cannot sort by {key!r}", {"allowed": sorted(cols)})
    col = cols[key]
    stmt = stmt.order_by(col.desc().nulls_last() if desc else col.asc().nulls_last(), Security.id)

    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return Page[SecuritySummary](
        items=[svc.row_to_summary(r) for r in rows],
        total=total or 0,
        page=page,
        page_size=page_size,
        context=ctx(db),
    )


@router.get("/securities/{security_id}", response_model=SecurityDetail, tags=["securities"])
def get_security(security_id: str, db: Session = Depends(get_db)):
    stmt, _, _ = svc.security_query()
    row = db.execute(stmt.where(Security.id == security_id)).first()
    if row is None:
        raise ApiError(404, "not_found", f"security {security_id} not found")
    s: Security = row.Security
    return {
        **svc.row_to_summary(row),
        **{
            k: getattr(s, k)
            for k in (
                "isin",
                "cusip",
                "coupon_frequency",
                "day_count",
                "issue_date",
                "face_value",
                "is_callable",
                "is_putable",
                "source",
            )
        },
        "bid_price": row.bid_price,
        "ask_price": row.ask_price,
        "context": ctx(db, row.quote_as_of),
    }


@router.get("/curves", response_model=list[CurveInfo], tags=["curves"])
def list_curves(db: Session = Depends(get_db)):
    return svc.curves_with_range(db)


@router.get("/curves/{curve_id}/points", response_model=CurveSnapshot, tags=["curves"])
def curve_points(curve_id: str, as_of: date | None = None, db: Session = Depends(get_db)):
    if db.get(BenchmarkCurve, curve_id) is None:
        raise ApiError(404, "not_found", f"curve {curve_id} not found")
    d, pts = svc.curve_snapshot(db, curve_id, as_of)
    if d is None:
        raise ApiError(404, "no_data", f"no points for {curve_id} on or before {as_of}")
    return CurveSnapshot(curve_id=curve_id, as_of=d, points=pts, context=ctx(db, d))


@router.get("/market/overview", response_model=MarketOverview, tags=["market"])
def market_overview(
    currency: str = Query("USD", min_length=3, max_length=3), db: Session = Depends(get_db)
):
    currency = currency.upper()
    curve = db.scalar(
        select(BenchmarkCurve)
        .where(BenchmarkCurve.currency == currency)
        .order_by(BenchmarkCurve.id)
        .limit(1)
    )
    snapshot, change = None, {}
    spreads: dict[str, list[float]] = {}
    corp_yields: list[Decimal] = []
    if curve:
        d, pts = svc.curve_snapshot(db, curve.id)
        if d:
            snapshot = CurveSnapshot(curve_id=curve.id, as_of=d, points=pts, context=ctx(db, d))
            d_prev, prev = svc.curve_snapshot(db, curve.id, d - timedelta(days=7))
            prev_map = {p.tenor_months: p.yield_pct for p in prev}
            change = {
                p.tenor_months: round(float(p.yield_pct - prev_map[p.tenor_months]) * 100, 1)
                for p in pts
                if p.tenor_months in prev_map
            }
            curve_xy = [(p.tenor_months / 12, float(p.yield_pct)) for p in pts]
            stmt, _, _ = svc.security_query()
            for row in db.execute(
                stmt.where(Security.currency == currency, Security.bond_type == "corporate")
            ):
                if row.mid_yield_pct is None or row.quote_as_of != d:
                    continue
                corp_yields.append(row.mid_yield_pct)
                t = (row.Security.maturity_date - d).days / 365.25
                g_spread = (float(row.mid_yield_pct) - svc.linear_interp(curve_xy, t)) * 100
                spreads.setdefault(row.rating or "NR", []).append(g_spread)
    order = ["AAA", "AA", "A", "BBB", "BB", "B", "NR"]
    return MarketOverview(
        currency=currency,
        curve=snapshot,
        curve_change_bp_1w=change,
        avg_corporate_yield_pct=(sum(corp_yields) / len(corp_yields)) if corp_yields else None,
        avg_spread_by_rating_bp={
            k: round(sum(v) / len(v), 1)
            for k, v in sorted(
                spreads.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99
            )
        },
        securities_count=db.scalar(
            select(func.count()).select_from(Security).where(Security.currency == currency)
        )
        or 0,
        freshness=svc.freshness(db),
        context=ctx(db),
    )


@router.get("/data-quality", response_model=DataQualityReport, tags=["data"])
def data_quality(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    issues = db.scalars(
        select(DataQualityIssue).order_by(DataQualityIssue.id.desc()).limit(limit)
    ).all()
    return DataQualityReport(
        freshness=svc.freshness(db),
        issues_by_rule=svc.quality_issue_counts(db),
        recent_issues=[QualityIssueOut.model_validate(i) for i in issues],
        context=ctx(db),
    )
