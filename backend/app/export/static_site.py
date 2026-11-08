"""Export the site's data as static JSON (for GitHub Pages or any static host).

Run:  python -m app.export.static_site OUT_DIR
Builds a throwaway SQLite database from the committed seed snapshots, then runs the same
validated pricing engine the API uses and writes:

  meta.json                 dates, engine version, data sources
  bonds.json                every bond with yield, duration, spread (+ filter options)
  bonds/{id}.json           terms, analytics, cash flows and price history for one bond
  price-yield/{id}.json     exact price at each yield shift (Price Simulator)
  curve.json                full Treasury par curve history (gaps kept as null)
  data-quality.json         ingestion results and quarantined records
"""

import json
import sys
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.analytics.curve import ENGINE_VERSION, METHOD
from app.core.config import get_settings
from app.db.base import Base
from app.models import CurvePoint, DataQualityIssue, MarketQuote, Security
from app.seed.load import load_all
from app.services import analytics as an
from app.services import explorer as ex
from app.services import market as mk

CURVE_ID = "USD-UST-PAR"


def _default(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, date | datetime):
        return o.isoformat()
    raise TypeError(f"not serialisable: {type(o).__name__}")


def _round(o, digits=6):
    if isinstance(o, float):
        return round(o, digits)
    if isinstance(o, dict):
        return {k: _round(v, digits) for k, v in o.items()}
    if isinstance(o, list):
        return [_round(v, digits) for v in o]
    return o


def write(out: Path, rel: str, payload) -> int:
    path = out / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        _round(json.loads(json.dumps(payload, default=_default))), separators=(",", ":")
    )
    path.write_text(text)
    return len(text)


def export(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine(f"sqlite+pysqlite:///{tmp}/export.db")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)  # noqa: N806
        with Session() as db:
            load_all(db, get_settings().seed_dir)
            sizes = _export(db, out)
        engine.dispose()
    return sizes


def _export(db, out: Path) -> dict:
    sizes: dict[str, int] = {}
    vintage = an.curve_vintage(db)
    as_of = mk.market_date(db)

    bonds = ex.list_bonds(
        db,
        q=None,
        bond_type=None,
        sectors=[],
        ratings=[],
        maturity=None,
        min_yield=None,
        max_yield=None,
        sort="maturity_date",
        page=1,
        page_size=10_000,
    )
    sizes["bonds.json"] = write(
        out,
        "bonds.json",
        {
            "items": bonds["items"],
            "facets": bonds["facets"],
            "as_of": bonds["as_of"],
            "is_synthetic": True,
        },
    )

    detail_stmt, _, _ = mk.security_query()
    n_detail = n_py = 0
    for sec in db.scalars(select(Security).order_by(Security.id)):
        row = db.execute(detail_stmt.where(Security.id == sec.id)).first()
        summary = mk.row_to_summary(row)
        security = {
            **summary,
            **{
                k: getattr(sec, k)
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
        }
        try:
            analytics = an.security_analytics(db, sec.id, None, CURVE_ID)
            analytics["calculated_at"] = datetime.now(UTC)
            analytics_error = None
        except an.ServiceError as exc:
            analytics, analytics_error = None, {"code": exc.code, "message": exc.message}
        history = [
            {"as_of": d, "mid_price": p, "mid_yield_pct": y}
            for d, p, y in db.execute(
                select(MarketQuote.as_of, MarketQuote.mid_price, MarketQuote.mid_yield_pct)
                .where(MarketQuote.security_id == sec.id)
                .order_by(MarketQuote.as_of)
            )
        ]
        n_detail += write(
            out,
            f"bonds/{sec.id}.json",
            {
                "security": security,
                "analytics": analytics,
                "analytics_error": analytics_error,
                "history": {
                    "security_id": sec.id,
                    "is_synthetic": sec.is_synthetic,
                    "points": history,
                },
            },
        )
        try:
            n_py += write(out, f"price-yield/{sec.id}.json", ex.price_yield(db, sec.id, 300, 1))
        except an.ServiceError:
            pass  # unsupported instruments simply have no simulator file
    sizes["bonds/*.json"] = n_detail
    sizes["price-yield/*.json"] = n_py

    by_date: dict[date, dict[float, float]] = {}
    for d, t, y in db.execute(
        select(CurvePoint.as_of, CurvePoint.tenor_months, CurvePoint.yield_pct).where(
            CurvePoint.curve_id == CURVE_ID
        )
    ):
        by_date.setdefault(d, {})[float(t)] = float(y)
    dates = sorted(by_date)
    tenors = sorted({t for v in by_date.values() for t in v})
    sizes["curve.json"] = write(
        out,
        "curve.json",
        {
            "curve_id": CURVE_ID,
            "is_synthetic": False,
            "units": "percent, par, bond-equivalent",
            "vintage": vintage,
            "dates": dates,
            "tenors_months": tenors,
            "yields": {f"{t:g}": [by_date[d].get(t) for d in dates] for t in tenors},
        },
    )

    issues = db.scalars(select(DataQualityIssue).order_by(DataQualityIssue.id.desc())).all()
    sizes["data-quality.json"] = write(
        out,
        "data-quality.json",
        {
            "freshness": mk.freshness(db),
            "issues_by_rule": mk.quality_issue_counts(db),
            "recent_issues": [
                {
                    c: getattr(i, c)
                    for c in (
                        "id",
                        "dataset",
                        "rule",
                        "severity",
                        "message",
                        "raw_record",
                        "created_at",
                    )
                }
                for i in issues
            ],
            "context": {"is_synthetic": True, "as_of": as_of, "generated_at": datetime.now(UTC)},
        },
    )

    sizes["meta.json"] = write(
        out,
        "meta.json",
        {
            "as_of": as_of,
            "generated_at": datetime.now(UTC),
            "engine_version": ENGINE_VERSION,
            "methodology": METHOD,
            "curve_vintage": vintage,
            "note": "Bonds and quotes are synthetic demo data; the Treasury curve is real.",
        },
    )
    return sizes


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m app.export.static_site OUT_DIR")
    result = export(Path(sys.argv[1]))
    for k, v in result.items():
        print(f"{k:<22} {v / 1024:8.1f} KB")
