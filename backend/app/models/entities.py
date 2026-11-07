"""Core M0 tables. Other §10 entities (predictions, portfolios, ...) come with their milestones.

Conventions: UTC timestamps; rates/yields stored in percent; prices per 100 face;
every market observation links to the ingestion run that loaded it (lineage).
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utcnow

RATE = Numeric(10, 6)
PRICE = Numeric(14, 6)


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    role: Mapped[str] = mapped_column(String(32))  # analyst | risk | admin | demo
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    __table_args__ = (
        CheckConstraint("role IN ('analyst','risk','admin','demo')", name="role_valid"),
    )


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    dataset: Mapped[str] = mapped_column(String(64), index=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))  # running | succeeded | failed
    rows_loaded: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    is_synthetic: Mapped[bool] = mapped_column(Boolean)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Issuer(TimestampMixin, Base):
    __tablename__ = "issuers"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    sector: Mapped[str] = mapped_column(String(64))
    country: Mapped[str] = mapped_column(String(2))
    is_synthetic: Mapped[bool] = mapped_column(Boolean)


class Security(TimestampMixin, Base):
    __tablename__ = "securities"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    issuer_id: Mapped[str] = mapped_column(ForeignKey("issuers.id"), index=True)
    isin: Mapped[str | None] = mapped_column(String(12), unique=True)
    cusip: Mapped[str | None] = mapped_column(String(9), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    bond_type: Mapped[str] = mapped_column(String(32))  # treasury | corporate
    currency: Mapped[str] = mapped_column(String(3))
    coupon_rate: Mapped[Decimal] = mapped_column(RATE)  # percent, e.g. 4.25
    coupon_frequency: Mapped[int] = mapped_column(Integer)  # payments per year; 0 = zero coupon
    day_count: Mapped[str] = mapped_column(String(16))  # 30/360 | ACT/ACT
    issue_date: Mapped[date] = mapped_column(Date)
    maturity_date: Mapped[date] = mapped_column(Date, index=True)
    face_value: Mapped[Decimal] = mapped_column(PRICE, default=Decimal(100))
    is_callable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_putable: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(64))
    is_synthetic: Mapped[bool] = mapped_column(Boolean)

    issuer: Mapped[Issuer] = relationship()
    __table_args__ = (
        CheckConstraint("maturity_date > issue_date", name="maturity_after_issue"),
        CheckConstraint("coupon_frequency IN (0,1,2,4,12)", name="frequency_valid"),
    )


class RatingHistory(Base):
    __tablename__ = "ratings_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    issuer_id: Mapped[str] = mapped_column(ForeignKey("issuers.id"), index=True)
    agency: Mapped[str] = mapped_column(String(32))
    rating: Mapped[str] = mapped_column(String(8))
    effective_date: Mapped[date] = mapped_column(Date)
    ingestion_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"))
    __table_args__ = (UniqueConstraint("issuer_id", "agency", "effective_date"),)


class BenchmarkCurve(TimestampMixin, Base):
    __tablename__ = "benchmark_curves"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3))
    curve_type: Mapped[str] = mapped_column(String(32))  # par | zero | spot
    compounding: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(64))
    is_synthetic: Mapped[bool] = mapped_column(Boolean)


class CurvePoint(Base):
    __tablename__ = "curve_points"
    id: Mapped[int] = mapped_column(primary_key=True)
    curve_id: Mapped[str] = mapped_column(ForeignKey("benchmark_curves.id"))
    as_of: Mapped[date] = mapped_column(Date)
    tenor_months: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    yield_pct: Mapped[Decimal] = mapped_column(RATE)
    ingestion_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"))
    __table_args__ = (UniqueConstraint("curve_id", "as_of", "tenor_months"),)


class MarketQuote(Base):
    __tablename__ = "market_quotes"
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[str] = mapped_column(ForeignKey("securities.id"))
    as_of: Mapped[date] = mapped_column(Date)
    bid_price: Mapped[Decimal] = mapped_column(PRICE)
    ask_price: Mapped[Decimal] = mapped_column(PRICE)
    mid_price: Mapped[Decimal] = mapped_column(PRICE)  # clean, per 100 face
    mid_yield_pct: Mapped[Decimal] = mapped_column(RATE)
    source: Mapped[str] = mapped_column(String(64))
    ingestion_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"))
    __table_args__ = (
        UniqueConstraint("security_id", "as_of", "source"),
        CheckConstraint("bid_price <= ask_price", name="bid_le_ask"),
    )


class DataQualityIssue(Base):
    """Quarantine: rejected records are kept here verbatim, never silently dropped."""

    __tablename__ = "data_quality_issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    ingestion_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"), index=True)
    dataset: Mapped[str] = mapped_column(String(64))
    rule: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))  # error | warning
    message: Mapped[str] = mapped_column(Text)
    raw_record: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
