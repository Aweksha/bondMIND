from datetime import date, datetime

from app.schemas.common import ApiModel, DataContext, Num


class SecuritySummary(ApiModel):
    id: str
    name: str
    issuer_id: str
    issuer_name: str
    sector: str
    bond_type: str
    currency: str
    rating: str | None
    coupon_rate: Num
    maturity_date: date
    mid_price: Num | None
    mid_yield_pct: Num | None
    quote_as_of: date | None
    is_synthetic: bool


class SecurityDetail(SecuritySummary):
    isin: str | None
    cusip: str | None
    coupon_frequency: int
    day_count: str
    issue_date: date
    face_value: Num
    is_callable: bool
    is_putable: bool
    source: str
    bid_price: Num | None
    ask_price: Num | None
    context: DataContext


class CurveInfo(ApiModel):
    id: str
    name: str
    currency: str
    curve_type: str
    compounding: str
    source: str
    is_synthetic: bool
    first_as_of: date | None
    last_as_of: date | None


class CurvePointOut(ApiModel):
    tenor_months: int
    yield_pct: Num


class CurveSnapshot(ApiModel):
    curve_id: str
    as_of: date
    points: list[CurvePointOut]
    interpolation: str = "none (observed tenors only)"
    context: DataContext


class SeriesFreshness(ApiModel):
    dataset: str
    last_as_of: date | None
    last_loaded_at: datetime | None
    rows_loaded: int
    rows_rejected: int
    status: str  # fresh | stale | missing
    is_synthetic: bool


class MarketOverview(ApiModel):
    currency: str
    curve: CurveSnapshot | None
    curve_change_bp_1w: dict[int, float]
    avg_corporate_yield_pct: Num | None
    avg_spread_by_rating_bp: dict[str, float]
    securities_count: int
    freshness: list[SeriesFreshness]
    context: DataContext


class QualityIssueOut(ApiModel):
    id: int
    dataset: str
    rule: str
    severity: str
    message: str
    raw_record: dict
    created_at: datetime


class DataQualityReport(ApiModel):
    freshness: list[SeriesFreshness]
    issues_by_rule: dict[str, int]
    recent_issues: list[QualityIssueOut]
    context: DataContext
