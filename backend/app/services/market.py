"""Read-side queries for market data. Kept separate from routes so they are unit-testable."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.models import (
    BenchmarkCurve,
    CurvePoint,
    DataQualityIssue,
    IngestionRun,
    Issuer,
    MarketQuote,
    RatingHistory,
    Security,
)

STALE_AFTER_DAYS = 4  # calendar days behind the market date before a series is "stale"


def now() -> datetime:
    return datetime.now(UTC)


def latest_quotes_subq():
    last = (
        select(MarketQuote.security_id, func.max(MarketQuote.as_of).label("as_of"))
        .group_by(MarketQuote.security_id)
        .subquery()
    )
    return (
        select(MarketQuote)
        .join(
            last,
            and_(MarketQuote.security_id == last.c.security_id, MarketQuote.as_of == last.c.as_of),
        )
        .subquery()
    )


def latest_ratings_subq():
    last = (
        select(RatingHistory.issuer_id, func.max(RatingHistory.effective_date).label("eff"))
        .group_by(RatingHistory.issuer_id)
        .subquery()
    )
    return (
        select(RatingHistory.issuer_id, RatingHistory.rating)
        .join(
            last,
            and_(
                RatingHistory.issuer_id == last.c.issuer_id,
                RatingHistory.effective_date == last.c.eff,
            ),
        )
        .subquery()
    )


def security_query() -> tuple[Select, object, object]:
    q, r = latest_quotes_subq(), latest_ratings_subq()
    stmt = (
        select(
            Security,
            Issuer.name.label("issuer_name"),
            Issuer.sector,
            r.c.rating,
            q.c.mid_price,
            q.c.mid_yield_pct,
            q.c.bid_price,
            q.c.ask_price,
            q.c.as_of.label("quote_as_of"),
        )
        .join(Issuer, Security.issuer_id == Issuer.id)
        .outerjoin(r, r.c.issuer_id == Security.issuer_id)
        .outerjoin(q, q.c.security_id == Security.id)
    )
    return stmt, q, r


def row_to_summary(row) -> dict:
    s: Security = row.Security
    return {
        "id": s.id,
        "name": s.name,
        "issuer_id": s.issuer_id,
        "issuer_name": row.issuer_name,
        "sector": row.sector,
        "bond_type": s.bond_type,
        "currency": s.currency,
        "rating": row.rating,
        "coupon_rate": s.coupon_rate,
        "maturity_date": s.maturity_date,
        "mid_price": row.mid_price,
        "mid_yield_pct": row.mid_yield_pct,
        "quote_as_of": row.quote_as_of,
        "is_synthetic": s.is_synthetic,
    }


def market_date(db: Session) -> date | None:
    return db.scalar(select(func.max(CurvePoint.as_of)))


def curve_snapshot(db: Session, curve_id: str, as_of: date | None = None):
    """Points on the latest date <= as_of (or overall latest)."""
    stmt = select(func.max(CurvePoint.as_of)).where(CurvePoint.curve_id == curve_id)
    if as_of:
        stmt = stmt.where(CurvePoint.as_of <= as_of)
    d = db.scalar(stmt)
    if d is None:
        return None, []
    pts = db.scalars(
        select(CurvePoint)
        .where(CurvePoint.curve_id == curve_id, CurvePoint.as_of == d)
        .order_by(CurvePoint.tenor_months)
    ).all()
    return d, pts


def linear_interp(points: list[tuple[float, float]], x: float) -> float:
    """Linear in tenor; flat extrapolation beyond observed tenors (labelled in API docs)."""
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        if x <= x1:
            return y0 + (x - x0) / (x1 - x0) * (y1 - y0)
    return points[-1][1]


def freshness(db: Session) -> list[dict]:
    ref = market_date(db)
    latest_by_dataset = {
        "curve_points": db.scalar(select(func.max(CurvePoint.as_of))),
        "quotes": db.scalar(select(func.max(MarketQuote.as_of))),
        "ratings": db.scalar(select(func.max(RatingHistory.effective_date))),
    }
    out = []
    for dataset in ("issuers", "securities", "ratings", "curves", "curve_points", "quotes"):
        run = db.scalar(
            select(IngestionRun)
            .where(IngestionRun.dataset == dataset, IngestionRun.status == "succeeded")
            .order_by(IngestionRun.started_at.desc())
            .limit(1)
        )
        last = latest_by_dataset.get(dataset)
        if run is None:
            status = "missing"
        elif dataset in ("curve_points", "quotes") and (
            last is None or ref is None or (ref - last) > timedelta(days=STALE_AFTER_DAYS)
        ):
            status = "stale"
        else:
            status = "fresh"
        out.append(
            {
                "dataset": dataset,
                "last_as_of": last,
                "last_loaded_at": run.finished_at if run else None,
                "rows_loaded": run.rows_loaded if run else 0,
                "rows_rejected": run.rows_rejected if run else 0,
                "status": status,
                "is_synthetic": run.is_synthetic if run else False,
            }
        )
    return out


def any_synthetic(db: Session) -> bool:
    return bool(
        db.scalar(
            select(func.count())
            .select_from(IngestionRun)
            .where(IngestionRun.is_synthetic.is_(True))
        )
    )


def quality_issue_counts(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(DataQualityIssue.rule, func.count()).group_by(DataQualityIssue.rule)
    ).all()
    return {rule: n for rule, n in rows}


def curves_with_range(db: Session) -> list[dict]:
    rng = (
        select(
            CurvePoint.curve_id,
            func.min(CurvePoint.as_of).label("first"),
            func.max(CurvePoint.as_of).label("last"),
        )
        .group_by(CurvePoint.curve_id)
        .subquery()
    )
    rows = db.execute(
        select(BenchmarkCurve, rng.c.first, rng.c.last)
        .outerjoin(rng, rng.c.curve_id == BenchmarkCurve.id)
        .order_by(BenchmarkCurve.id)
    ).all()
    return [
        {
            **{
                c: getattr(b, c)
                for c in (
                    "id",
                    "name",
                    "currency",
                    "curve_type",
                    "compounding",
                    "source",
                    "is_synthetic",
                )
            },
            "first_as_of": first,
            "last_as_of": last,
        }
        for b, first, last in rows
    ]
