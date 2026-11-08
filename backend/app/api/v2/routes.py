from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.analytics.curve import ENGINE_VERSION
from app.api.errors import ApiError
from app.db.session import get_db
from app.models import CurvePoint, MarketQuote
from app.schemas.v2 import (
    CurveDatesResponse,
    CurveObservationSet,
    CurveObservationsResponse,
    CurvePointV2,
    ScenarioRequest,
)
from app.services import analytics as an
from app.services import explorer as ex
from app.services import market as mk
from app.services.scenario import evaluate

router = APIRouter(prefix="/api/v2")


def _wrap(fn, *args):
    try:
        return fn(*args)
    except an.ServiceError as exc:
        raise ApiError(exc.status, exc.code, exc.message, exc.details) from exc


@router.get("/curves", tags=["v2 curves"])
def curves(db: Session = Depends(get_db)) -> list[dict]:
    return mk.curves_with_range(db)


@router.get("/curves/{curve_id}/dates", response_model=CurveDatesResponse, tags=["v2 curves"])
def curve_dates(curve_id: str, db: Session = Depends(get_db)):
    _wrap(an.get_curve, db, curve_id)
    dates = list(
        db.scalars(
            select(distinct(CurvePoint.as_of))
            .where(CurvePoint.curve_id == curve_id)
            .order_by(CurvePoint.as_of)
        )
    )
    tenors = [
        float(t)
        for t in db.scalars(
            select(distinct(CurvePoint.tenor_months))
            .where(CurvePoint.curve_id == curve_id)
            .order_by(CurvePoint.tenor_months)
        )
    ]
    return CurveDatesResponse(
        curve_id=curve_id,
        first_date=dates[0] if dates else None,
        last_date=dates[-1] if dates else None,
        dates=dates,
        tenors_months=tenors,
    )


@router.get(
    "/curves/{curve_id}/observations", response_model=CurveObservationsResponse, tags=["v2 curves"]
)
def curve_observations(
    curve_id: str,
    dates: list[date] = Query(..., min_length=1, max_length=6),
    tenors: list[float] | None = Query(None, max_length=30, description="tenor months"),
    db: Session = Depends(get_db),
):
    curve = _wrap(an.get_curve, db, curve_id)
    out = []
    for d in dates:
        observed = an.observation_date(db, curve_id, d)
        if observed is None:
            out.append(
                CurveObservationSet(
                    requested_date=d, observed_date=None, status="unavailable", points=[]
                )
            )
            continue
        rows = {
            float(t): float(y)
            for t, y in db.execute(
                select(CurvePoint.tenor_months, CurvePoint.yield_pct).where(
                    CurvePoint.curve_id == curve_id, CurvePoint.as_of == observed
                )
            )
        }
        wanted = tenors or sorted(rows)
        out.append(
            CurveObservationSet(
                requested_date=d,
                observed_date=observed,
                status="observed" if observed == d else "prior_observation",
                points=[CurvePointV2(tenor_months=t, yield_pct=rows.get(t)) for t in wanted],
            )
        )
    return CurveObservationsResponse(
        curve_id=curve_id,
        is_synthetic=curve.is_synthetic,
        units={"yield_pct": "percent, par, bond-equivalent", "tenor_months": "months"},
        observations=out,
        vintage=an.curve_vintage(db),
        generated_at=datetime.now(UTC),
    )


@router.get("/bonds", tags=["v2 explorer"])
def bonds(
    q: str | None = Query(None, max_length=100),
    bond_type: str | None = Query(None, pattern="^(treasury|corporate)$"),
    sector: list[str] = Query([], max_length=20),
    rating: list[str] = Query([], max_length=10),
    maturity: str | None = Query(None, pattern=r"^(0-3y|3-7y|7-10y|10y\+)$"),
    min_yield: float | None = Query(None, ge=-5, le=40),
    max_yield: float | None = Query(None, ge=-5, le=40),
    sort: str = Query("maturity_date", pattern=r"^-?[a-z_]+$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    return _wrap(
        lambda: ex.list_bonds(
            db,
            q=q,
            bond_type=bond_type,
            sectors=sector,
            ratings=rating,
            maturity=maturity,
            min_yield=min_yield,
            max_yield=max_yield,
            sort=sort,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/curves/{curve_id}/series", tags=["v2 curves"])
def curve_series(
    curve_id: str,
    tenors: list[float] = Query(..., min_length=1, max_length=14),
    start: date | None = Query(None, alias="from"),
    end: date | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
) -> dict:
    _wrap(an.get_curve, db, curve_id)
    return ex.curve_series(db, curve_id, tenors, start, end)


@router.get("/securities/{security_id}/price-yield", tags=["v2 securities"])
def price_yield(
    security_id: str,
    range_bp: int = Query(300, ge=25, le=500),
    step_bp: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    return _wrap(ex.price_yield, db, security_id, range_bp, step_bp)


@router.get("/securities/{security_id}/analytics", tags=["v2 securities"])
def security_analytics(
    security_id: str,
    as_of: date | None = Query(None, alias="asOf"),
    curve_id: str = Query("USD-UST-PAR", alias="curveId", max_length=32),
    db: Session = Depends(get_db),
) -> dict:
    result = _wrap(an.security_analytics, db, security_id, as_of, curve_id)
    result["calculated_at"] = datetime.now(UTC)
    return result


@router.get("/securities/{security_id}/history", tags=["v2 securities"])
def security_history(
    security_id: str,
    start: date | None = Query(None, alias="from"),
    end: date | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
) -> dict:
    sec = _wrap(an.security_or_404, db, security_id)
    stmt = select(MarketQuote.as_of, MarketQuote.mid_price, MarketQuote.mid_yield_pct).where(
        MarketQuote.security_id == security_id
    )
    if start:
        stmt = stmt.where(MarketQuote.as_of >= start)
    if end:
        stmt = stmt.where(MarketQuote.as_of <= end)
    rows = db.execute(stmt.order_by(MarketQuote.as_of)).all()
    return {
        "security_id": security_id,
        "is_synthetic": sec.is_synthetic,
        "units": {"mid_price": "clean, per 100 face", "mid_yield_pct": "percent"},
        "points": [
            {"as_of": d, "mid_price": float(p), "mid_yield_pct": float(y)} for d, p, y in rows
        ],
    }


@router.post("/scenarios/evaluate", tags=["v2 scenarios"])
def scenarios_evaluate(
    req: ScenarioRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    return _wrap(evaluate, db, req, getattr(request.state, "request_id", None))


@router.get("/engine", tags=["v2 system"])
def engine() -> dict:
    from app.analytics.curve import METHOD

    return {"engine_version": ENGINE_VERSION, "methodology": METHOD}
