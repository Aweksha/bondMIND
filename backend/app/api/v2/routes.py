from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.analytics.curve import ENGINE_VERSION
from app.api.errors import ApiError
from app.db.session import get_db
from app.models import CurvePoint
from app.schemas.v2 import (
    CurveDatesResponse,
    CurveObservationSet,
    CurveObservationsResponse,
    CurvePointV2,
    ScenarioRequest,
)
from app.services import analytics as an
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


@router.post("/scenarios/evaluate", tags=["v2 scenarios"])
def scenarios_evaluate(
    req: ScenarioRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    return _wrap(evaluate, db, req, getattr(request.state, "request_id", None))


@router.get("/engine", tags=["v2 system"])
def engine() -> dict:
    from app.analytics.curve import METHOD

    return {"engine_version": ENGINE_VERSION, "methodology": METHOD}
