"""Validate and load seed CSV snapshots into the database (idempotent).

Run:  python -m app.seed.load [--reset]
Each dataset gets an ingestion_runs row. Invalid records go to data_quality_issues with the
rule that rejected them; valid records are inserted. A file whose sha256 already loaded
successfully is skipped, so re-running is safe.
"""

import argparse
import csv
import hashlib
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import (
    AuditEvent,
    BenchmarkCurve,
    CurvePoint,
    DataQualityIssue,
    IngestionRun,
    Issuer,
    MarketQuote,
    RatingHistory,
    Security,
)

SOURCE = "seed-csv"


class RejectError(Exception):
    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule, self.message = rule, message


def _dec(row: dict, key: str) -> Decimal:
    try:
        return Decimal(row[key])
    except (InvalidOperation, KeyError, TypeError) as exc:
        raise RejectError("invalid_number", f"{key}={row.get(key)!r} is not numeric") from exc


def _date(row: dict, key: str) -> date:
    try:
        return date.fromisoformat(row[key])
    except (ValueError, KeyError, TypeError) as exc:
        raise RejectError("invalid_date", f"{key}={row.get(key)!r} is not ISO-8601") from exc


def _bool(v: str) -> bool:
    return v.strip().lower() in ("true", "1", "yes")


def _require(row: dict, keys: list[str]) -> None:
    missing = [k for k in keys if not (row.get(k) or "").strip()]
    if missing:
        raise RejectError("missing_terms", f"missing required fields: {', '.join(missing)}")


class Ctx:
    def __init__(self, session: Session):
        self.issuers = set(session.scalars(select(Issuer.id)))
        self.securities = {s.id: s for s in session.scalars(select(Security))}
        self.curves = set(session.scalars(select(BenchmarkCurve.id)))
        self.seen: set[tuple] = set()

    def dedupe(self, key: tuple) -> None:
        if key in self.seen:
            raise RejectError("duplicate", f"duplicate record key {key}")
        self.seen.add(key)


def v_issuer(r: dict, c: Ctx) -> dict:
    _require(r, ["id", "name", "sector", "country"])
    c.dedupe(("issuer", r["id"]))
    c.issuers.add(r["id"])
    return {
        "id": r["id"],
        "name": r["name"],
        "sector": r["sector"],
        "country": r["country"],
        "is_synthetic": True,
    }


def v_security(r: dict, c: Ctx) -> dict:
    _require(
        r,
        [
            "id",
            "issuer_id",
            "bond_type",
            "currency",
            "coupon_rate",
            "coupon_frequency",
            "day_count",
            "issue_date",
            "maturity_date",
        ],
    )
    c.dedupe(("security", r["id"]))
    if r["issuer_id"] not in c.issuers:
        raise RejectError("unknown_issuer", f"issuer {r['issuer_id']} not found")
    issue, mat = _date(r, "issue_date"), _date(r, "maturity_date")
    if mat <= issue:
        raise RejectError("inconsistent_terms", "maturity_date must be after issue_date")
    freq = int(r["coupon_frequency"])
    if freq not in (0, 1, 2, 4, 12):
        raise RejectError("inconsistent_terms", f"unsupported frequency {freq}")
    cpn = _dec(r, "coupon_rate")
    if not Decimal(0) <= cpn <= Decimal(25):
        raise RejectError("impossible_coupon", f"coupon {cpn}% outside [0, 25]")
    row = {
        "id": r["id"],
        "issuer_id": r["issuer_id"],
        "name": r["name"],
        "bond_type": r["bond_type"],
        "currency": r["currency"],
        "coupon_rate": cpn,
        "coupon_frequency": freq,
        "day_count": r["day_count"],
        "issue_date": issue,
        "maturity_date": mat,
        "is_callable": _bool(r["is_callable"]),
        "is_putable": _bool(r["is_putable"]),
        "source": SOURCE,
        "is_synthetic": True,
    }
    c.securities[r["id"]] = Security(**row)
    return row


def v_rating(r: dict, c: Ctx) -> dict:
    _require(r, ["issuer_id", "agency", "rating", "effective_date"])
    c.dedupe(("rating", r["issuer_id"], r["agency"], r["effective_date"]))
    if r["issuer_id"] not in c.issuers:
        raise RejectError("unknown_issuer", f"issuer {r['issuer_id']} not found")
    return {
        "issuer_id": r["issuer_id"],
        "agency": r["agency"],
        "rating": r["rating"],
        "effective_date": _date(r, "effective_date"),
    }


def v_curve(r: dict, c: Ctx) -> dict:
    _require(r, ["id", "name", "currency", "curve_type", "compounding"])
    c.dedupe(("curve", r["id"]))
    c.curves.add(r["id"])
    return {
        **{k: r[k] for k in ("id", "name", "currency", "curve_type", "compounding")},
        "source": SOURCE,
        "is_synthetic": True,
    }


def v_curve_point(r: dict, c: Ctx) -> dict:
    _require(r, ["curve_id", "as_of", "tenor_months", "yield_pct"])
    if r["curve_id"] not in c.curves:
        raise RejectError("unknown_curve", f"curve {r['curve_id']} not found")
    y = _dec(r, "yield_pct")
    if not Decimal(-5) <= y <= Decimal(25):
        raise RejectError("impossible_yield", f"yield {y}% outside [-5, 25] (unit mismatch?)")
    tenor = int(r["tenor_months"])
    if tenor <= 0:
        raise RejectError("invalid_tenor", f"tenor {tenor} must be positive")
    c.dedupe(("cp", r["curve_id"], r["as_of"], tenor))
    return {
        "curve_id": r["curve_id"],
        "as_of": _date(r, "as_of"),
        "tenor_months": tenor,
        "yield_pct": y,
    }


def v_quote(r: dict, c: Ctx) -> dict:
    _require(
        r,
        ["security_id", "as_of", "bid_price", "ask_price", "mid_price", "mid_yield_pct", "source"],
    )
    sec = c.securities.get(r["security_id"])
    if sec is None:
        raise RejectError("unknown_security", f"security {r['security_id']} not found")
    as_of = _date(r, "as_of")
    if not sec.issue_date <= as_of < sec.maturity_date:
        raise RejectError("outside_life", f"quote {as_of} outside security life")
    bid, ask, mid = _dec(r, "bid_price"), _dec(r, "ask_price"), _dec(r, "mid_price")
    if not all(Decimal(0) < p < Decimal(300) for p in (bid, ask, mid)):
        raise RejectError("impossible_price", f"price outside (0, 300): bid={bid} ask={ask}")
    if bid > ask:
        raise RejectError("crossed_market", f"bid {bid} > ask {ask}")
    y = _dec(r, "mid_yield_pct")
    if not Decimal(-5) <= y <= Decimal(40):
        raise RejectError("impossible_yield", f"yield {y}% outside [-5, 40]")
    c.dedupe(("q", r["security_id"], r["as_of"], r["source"]))
    return {
        "security_id": r["security_id"],
        "as_of": as_of,
        "bid_price": bid,
        "ask_price": ask,
        "mid_price": mid,
        "mid_yield_pct": y,
        "source": r["source"],
    }


# Order matters: referenced datasets load first.
DATASETS: list[tuple[str, type, Callable[[dict, Ctx], dict], bool]] = [
    ("issuers", Issuer, v_issuer, False),
    ("securities", Security, v_security, False),
    ("ratings", RatingHistory, v_rating, True),
    ("curves", BenchmarkCurve, v_curve, False),
    ("curve_points", CurvePoint, v_curve_point, True),
    ("quotes", MarketQuote, v_quote, True),
]


def reset(session: Session) -> None:
    for model in (
        DataQualityIssue,
        MarketQuote,
        CurvePoint,
        RatingHistory,
        Security,
        BenchmarkCurve,
        Issuer,
        IngestionRun,
    ):
        session.execute(delete(model))
    session.commit()


def load_dataset(
    session: Session,
    ctx: Ctx,
    seed_dir: Path,
    name: str,
    model: type,
    validate: Callable[[dict, Ctx], dict],
    has_run_fk: bool,
) -> IngestionRun | None:
    path = seed_dir / f"{name}.csv"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    done = session.scalar(
        select(IngestionRun).where(
            IngestionRun.dataset == name,
            IngestionRun.file_sha256 == digest,
            IngestionRun.status == "succeeded",
        )
    )
    if done:
        return None
    run = IngestionRun(
        source=SOURCE, dataset=name, file_sha256=digest, status="running", is_synthetic=True
    )
    session.add(run)
    session.flush()
    good, bad = [], []
    with path.open(newline="") as fh:
        for raw in csv.DictReader(fh):
            try:
                row = validate(raw, ctx)
                if has_run_fk:
                    row["ingestion_run_id"] = run.id
                good.append(row)
            except RejectError as rej:
                bad.append(
                    {
                        "ingestion_run_id": run.id,
                        "dataset": name,
                        "rule": rej.rule,
                        "severity": "error",
                        "message": rej.message,
                        "raw_record": raw,
                    }
                )
    for i in range(0, len(good), 5000):
        session.execute(insert(model), good[i : i + 5000])
    if bad:
        session.execute(insert(DataQualityIssue), bad)
    run.rows_loaded, run.rows_rejected = len(good), len(bad)
    run.status, run.finished_at = "succeeded", datetime.now(UTC)
    session.add(
        AuditEvent(
            actor="system:seed",
            action="ingest",
            entity="ingestion_run",
            entity_id=str(run.id),
            details={"dataset": name, "loaded": len(good), "rejected": len(bad), "sha256": digest},
        )
    )
    session.commit()
    return run


def load_all(session: Session, seed_dir: Path) -> list[IngestionRun]:
    ctx = Ctx(session)
    runs = []
    for name, model, validate, has_fk in DATASETS:
        run = load_dataset(session, ctx, seed_dir, name, model, validate, has_fk)
        if run:
            runs.append(run)
    return runs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete seeded data first")
    args = parser.parse_args()
    with SessionLocal() as session:
        if args.reset:
            reset(session)
        runs = load_all(session, get_settings().seed_dir)
    if not runs:
        print("Nothing to load: seed files already ingested.")
    for r in runs:
        print(f"{r.dataset:<14} loaded={r.rows_loaded:<7} rejected={r.rows_rejected}")


if __name__ == "__main__":
    main()
