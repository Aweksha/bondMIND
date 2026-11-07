"""Valuation services used by the v2 API. All numeric work is delegated to app.analytics."""

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.bond import (
    BondTermsError,
    FixedRateBond,
    accrued_interest,
    future_flows,
    yield_from_clean_price,
    yield_risk,
)
from app.analytics.curve import (
    ENGINE_VERSION,
    CurveError,
    ParCurve,
    bootstrap,
    solve_z_spread,
    value,
    year_frac,
)
from app.core.config import get_settings
from app.models import BenchmarkCurve, CurvePoint, IngestionRun, MarketQuote, Security

MAX_LOOKBACK_DAYS = 7  # weekends/holidays resolve to the prior observation, and say so


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


@dataclass(frozen=True)
class CurveOnDate:
    curve_id: str
    requested: date
    observed: date
    par: ParCurve
    points: list[tuple[float, float]]  # (tenor_months, yield_pct) as sourced

    @property
    def resolved_from_prior(self) -> bool:
        return self.observed != self.requested


def get_curve(db: Session, curve_id: str) -> BenchmarkCurve:
    curve = db.get(BenchmarkCurve, curve_id)
    if curve is None:
        raise ServiceError(
            404,
            "unknown_curve",
            f"curve {curve_id!r} not found",
            {"available": list(db.scalars(select(BenchmarkCurve.id)))},
        )
    return curve


def observation_date(db: Session, curve_id: str, requested: date) -> date | None:
    return db.scalar(
        select(func.max(CurvePoint.as_of)).where(
            CurvePoint.curve_id == curve_id,
            CurvePoint.as_of <= requested,
            CurvePoint.as_of >= requested - timedelta(days=MAX_LOOKBACK_DAYS),
        )
    )


def curve_on(db: Session, curve_id: str, requested: date) -> CurveOnDate:
    get_curve(db, curve_id)
    observed = observation_date(db, curve_id, requested)
    if observed is None:
        raise ServiceError(
            422,
            "no_curve_observation",
            f"no {curve_id} observation on or within {MAX_LOOKBACK_DAYS} days "
            f"before {requested}",
            {"hint": "choose a date with published data"},
        )
    rows = db.execute(
        select(CurvePoint.tenor_months, CurvePoint.yield_pct)
        .where(CurvePoint.curve_id == curve_id, CurvePoint.as_of == observed)
        .order_by(CurvePoint.tenor_months)
    ).all()
    points = [(float(t), float(y)) for t, y in rows]
    try:
        par = ParCurve.from_points([(t / 12, y / 100) for t, y in points])
    except CurveError as exc:
        raise ServiceError(422, "unsupported_curve", str(exc)) from exc
    return CurveOnDate(curve_id, requested, observed, par, points)


def curve_vintage(db: Session) -> dict:
    run = db.scalar(
        select(IngestionRun)
        .where(IngestionRun.dataset == "curve_points", IngestionRun.status == "succeeded")
        .order_by(IngestionRun.started_at.desc())
        .limit(1)
    )
    meta_path: Path = get_settings().seed_dir / "ust_par_curve.meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return {
        "ingestion_run_id": run.id if run else None,
        "file_sha256": run.file_sha256 if run else None,
        "source": meta.get("source"),
        "retrieved_at": meta.get("retrieved_at"),
        "license": meta.get("license"),
    }


def to_bond(sec: Security) -> FixedRateBond:
    reasons = []
    if sec.is_callable or sec.is_putable:
        reasons.append("embedded options (callable/putable) need an option model")
    if sec.bond_type not in ("treasury", "corporate"):
        reasons.append(f"bond type {sec.bond_type!r} is not a plain fixed-rate bullet")
    if reasons:
        raise ServiceError(
            422,
            "unsupported_instrument",
            f"{sec.id} is excluded from repricing: {'; '.join(reasons)}",
        )
    try:
        return FixedRateBond(
            sec.issue_date,
            sec.maturity_date,
            float(sec.coupon_rate) / 100,
            sec.coupon_frequency,
            sec.day_count,
            float(sec.face_value),
        )
    except BondTermsError as exc:
        raise ServiceError(422, "invalid_terms", f"{sec.id}: {exc}") from exc


def quote_on(db: Session, security_id: str, requested: date) -> MarketQuote:
    q = db.scalar(
        select(MarketQuote)
        .where(
            MarketQuote.security_id == security_id,
            MarketQuote.as_of <= requested,
            MarketQuote.as_of >= requested - timedelta(days=MAX_LOOKBACK_DAYS),
        )
        .order_by(MarketQuote.as_of.desc())
        .limit(1)
    )
    if q is None:
        raise ServiceError(
            422,
            "no_quote",
            f"no quote for {security_id} on or within {MAX_LOOKBACK_DAYS} days "
            f"before {requested}",
        )
    return q


def security_or_404(db: Session, security_id: str) -> Security:
    sec = db.get(Security, security_id)
    if sec is None:
        raise ServiceError(404, "not_found", f"security {security_id} not found")
    return sec


def latest_quote_date(db: Session, security_id: str) -> date | None:
    return db.scalar(
        select(func.max(MarketQuote.as_of)).where(MarketQuote.security_id == security_id)
    )


def security_analytics(db: Session, security_id: str, as_of: date | None, curve_id: str) -> dict:
    sec = security_or_404(db, security_id)
    bond = to_bond(sec)
    requested = as_of or latest_quote_date(db, security_id)
    if requested is None:
        raise ServiceError(422, "no_quote", f"{security_id} has no quotes")
    quote = quote_on(db, security_id, requested)
    settle = quote.as_of  # T+0: settlement = valuation date (disclosed)
    curve = curve_on(db, curve_id, settle)
    warnings: list[str] = []
    if curve.resolved_from_prior:
        warnings.append(f"curve resolved to prior observation {curve.observed}")
    if quote.as_of != requested:
        warnings.append(f"quote resolved to prior observation {quote.as_of}")

    clean = float(quote.mid_price)
    ai = accrued_interest(bond, settle)
    dirty = clean + ai
    ytm = yield_from_clean_price(bond, settle, clean)
    yr = yield_risk(bond, settle, ytm)
    zc = bootstrap(curve.par)
    try:
        z = solve_z_spread(bond, settle, zc, dirty)
        val = value(bond, settle, curve.par, z)
    except CurveError as exc:
        raise ServiceError(422, "unsupported_tenor", str(exc)) from exc
    t_mat = year_frac(settle, bond.maturity_date)
    g_spread_bp = (ytm - curve.par.par_at(t_mat)) * 1e4

    flows = []
    for cf in future_flows(bond, settle):
        t = year_frac(settle, cf.date)
        df = (1 + (zc.zero_rate(t) + z) / 2) ** (-2 * t)
        flows.append(
            {
                "date": cf.date,
                "amount": cf.amount,
                "kind": "principal" if cf.is_principal else "coupon",
                "time_years": t,
                "discount_factor": df,
                "present_value": cf.amount * df,
            }
        )
    return {
        "security_id": sec.id,
        "as_of": settle,
        "is_synthetic": sec.is_synthetic,
        "quote": {
            "as_of": quote.as_of,
            "source": quote.source,
            "bid": float(quote.bid_price),
            "ask": float(quote.ask_price),
            "mid_clean": float(quote.mid_price),
        },
        "pricing": {"clean": clean, "dirty": dirty, "accrued": ai, "ytm_pct": ytm * 100},
        "yield_risk": {
            "macaulay_duration": yr.macaulay_duration,
            "modified_duration": yr.modified_duration,
            "convexity": yr.convexity,
            "dv01": yr.dv01,
        },
        "curve_risk": {
            "z_spread_bp": z * 1e4,
            "g_spread_bp": g_spread_bp,
            "effective_duration": val.effective_duration,
            "effective_convexity": val.effective_convexity,
            "dv01": val.dv01,
            "model_dirty": val.dirty,
        },
        "cash_flows": flows,
        "assumptions": assumptions(bond, settle, curve),
        "warnings": warnings,
        "engine_version": ENGINE_VERSION,
    }


def assumptions(bond: FixedRateBond, settle: date, curve: CurveOnDate) -> dict:
    from app.analytics.curve import METHOD

    return {
        "settlement_date": settle,
        "settlement_convention": "T+0 (settlement = valuation date)",
        "day_count": bond.day_count
        + (" (ICMA)" if bond.day_count == "ACT/ACT" else " (bond basis)"),
        "coupon_frequency": bond.frequency,
        "yield_compounding": "per coupon frequency (street convention)",
        "discount_curve": f"{curve.curve_id} bootstrapped zero curve, observed {curve.observed}",
        "dv01_definition": "signed change in dirty price per 100 face for +1bp; "
        "negative means the price falls",
        "risk_bump": "+/-1bp parallel shift of the par curve, Z-spread held constant",
        **{f"method_{k}": v for k, v in METHOD.items()},
    }
