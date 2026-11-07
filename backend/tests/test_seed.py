import json

from sqlalchemy import func, select

from app.models import DataQualityIssue, IngestionRun, MarketQuote
from app.seed.generate import generate
from app.seed.load import load_all


def test_generator_is_deterministic(tmp_path, seed_dir):
    m1 = json.loads((seed_dir / "manifest.json").read_text())
    m2 = generate(tmp_path)
    assert {k: v["sha256"] for k, v in m1["files"].items()} == {
        k: v["sha256"] for k, v in m2["files"].items()
    }


def test_invalid_rows_are_quarantined(session_factory):
    with session_factory() as s:
        rules = dict(
            s.execute(
                select(DataQualityIssue.rule, func.count()).group_by(DataQualityIssue.rule)
            ).all()
        )
    assert rules == {
        "duplicate": 1,
        "impossible_price": 1,
        "crossed_market": 1,
        "unknown_security": 1,
        "impossible_yield": 1,
    }


def test_reload_is_idempotent(session_factory, seed_dir):
    with session_factory() as s:
        before = s.scalar(select(func.count()).select_from(MarketQuote))
        assert load_all(s, seed_dir) == []
        assert s.scalar(select(func.count()).select_from(MarketQuote)) == before
        assert all(r.is_synthetic for r in s.scalars(select(IngestionRun)))
