"""Scenario evaluation: shock the par curve, re-bootstrap, reprice each security."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.analytics.bond import accrued_interest
from app.analytics.curve import ENGINE_VERSION, METHOD, CurveError, bootstrap, solve_z_spread
from app.analytics.curve import value as curve_value
from app.models import AuditEvent
from app.schemas.v2 import ScenarioRequest
from app.services.analytics import (
    ServiceError,
    assumptions,
    curve_on,
    curve_vintage,
    quote_on,
    security_or_404,
    to_bond,
)

LARGE_SHOCK_BP = 100


def evaluate(db: Session, req: ScenarioRequest, request_id: str | None) -> dict:
    base = curve_on(db, req.curve_id, req.base_date)
    nodes = [(n.tenor_years, n.bp) for n in req.shock_nodes]
    shocked = base.par.shocked(nodes)
    zc_base, zc_shock = bootstrap(base.par), bootstrap(shocked)
    bps = {n.bp for n in req.shock_nodes}
    is_parallel = len(bps) == 1
    max_abs = max(abs(n.bp) for n in req.shock_nodes)

    warnings: list[str] = []
    if base.resolved_from_prior:
        warnings.append(f"base curve resolved to prior observation {base.observed}")
    if max_abs > LARGE_SHOCK_BP:
        warnings.append(
            f"shock exceeds {LARGE_SHOCK_BP}bp: duration/convexity approximations "
            "degrade; use the full repricing figures"
        )
    if req.spread_mode == "hold_constant":
        warnings.append("rate-only scenario: each bond's Z-spread is held constant")

    curve_rows = []
    for (t_months, y), y_shock in zip(base.points, shocked.par_yields, strict=True):
        t = t_months / 12
        curve_rows.append(
            {
                "tenor_months": t_months,
                "base_par_pct": y,
                "shock_bp": round((y_shock * 100 - y) * 100, 6),
                "shocked_par_pct": y_shock * 100,
                "base_zero_pct": zc_base.zero_rate(t) * 100,
                "shocked_zero_pct": zc_shock.zero_rate(t) * 100,
            }
        )

    results = []
    for sid in req.security_ids:
        try:
            results.append(_reprice(db, sid, base, shocked, req, is_parallel))
        except ServiceError as exc:
            results.append(
                {
                    "security_id": sid,
                    "status": "error",
                    "error": {"code": exc.code, "message": exc.message},
                }
            )

    response = {
        "input": req.model_dump(mode="json"),
        "units": {
            "yields": "percent",
            "shocks": "bp",
            "spreads": "bp",
            "prices": "per 100 face",
            "durations": "years",
            "dv01": "signed dirty price change per 100 face for +1bp",
        },
        "curve": {
            "curve_id": base.curve_id,
            "requested_date": base.requested,
            "observed_date": base.observed,
            "points": curve_rows,
            "is_parallel": is_parallel,
        },
        "results": results,
        "warnings": warnings,
        "methodology": METHOD,
        "vintage": curve_vintage(db),
        "engine_version": ENGINE_VERSION,
        "calculated_at": datetime.now(UTC),
        "request_id": request_id,
        "disclaimer": "Hypothetical research simulation. Not investment advice.",
    }
    db.add(
        AuditEvent(
            actor="anonymous",
            action="scenario.evaluate",
            entity="scenario",
            entity_id=request_id,
            details={
                "input": response["input"],
                "engine_version": ENGINE_VERSION,
                "vintage_sha256": response["vintage"]["file_sha256"],
                "status": [r["status"] for r in results],
            },
        )
    )
    db.commit()
    return response


def _reprice(db, sid, base, shocked, req: ScenarioRequest, is_parallel: bool) -> dict:
    sec = security_or_404(db, sid)
    bond = to_bond(sec)
    quote = quote_on(db, sid, base.observed)
    settle = quote.as_of
    sec_warnings = []
    if settle != base.observed:
        sec_warnings.append(f"latest quote {settle} predates curve date {base.observed}")
    clean = float(quote.mid_price)
    dirty = clean + accrued_interest(bond, settle)
    try:
        z = solve_z_spread(bond, settle, bootstrap(base.par), dirty)
        v0 = curve_value(bond, settle, base.par, z)
        z1 = z + (req.spread_shock_bp * 1e-4 if req.spread_mode == "shock" else 0.0)
        v1 = curve_value(bond, settle, shocked, z1)
    except CurveError as exc:
        raise ServiceError(422, "unsupported_tenor", str(exc)) from exc

    approx = None
    if is_parallel and req.spread_mode == "hold_constant":
        dy = req.shock_nodes[0].bp * 1e-4
        est = v0.dirty * (-v0.effective_duration * dy + 0.5 * v0.effective_convexity * dy**2)
        approx = {
            "method": "dP ~ P(-D_eff dy + 0.5 C_eff dy^2)",
            "estimated_change": est,
            "error_vs_full": est - (v1.dirty - v0.dirty),
        }
    return {
        "security_id": sid,
        "status": "ok",
        "is_synthetic": sec.is_synthetic,
        "quote_as_of": quote.as_of,
        "z_spread_bp": z * 1e4,
        "shocked_z_spread_bp": z1 * 1e4,
        "base": _metrics(v0),
        "shocked": _metrics(v1),
        "change": {
            "clean": v1.clean - v0.clean,
            "dirty": v1.dirty - v0.dirty,
            "pct": (v1.dirty / v0.dirty - 1) * 100,
        },
        "approximation": approx,
        "assumptions": assumptions(bond, settle, base),
        "warnings": sec_warnings,
    }


def _metrics(v) -> dict:
    return {
        "clean": v.clean,
        "dirty": v.dirty,
        "accrued": v.accrued,
        "effective_duration": v.effective_duration,
        "effective_convexity": v.effective_convexity,
        "dv01": v.dv01,
    }
