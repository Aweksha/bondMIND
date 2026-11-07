// Mirrors backend/app/schemas. Yields in percent, prices clean per 100 face, dates ISO-8601.

export interface DataContext {
  is_synthetic: boolean;
  as_of: string | null;
  generated_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  context: DataContext;
}

export interface SecuritySummary {
  id: string;
  name: string;
  issuer_id: string;
  issuer_name: string;
  sector: string;
  bond_type: 'treasury' | 'corporate';
  currency: string;
  rating: string | null;
  coupon_rate: number;
  maturity_date: string;
  mid_price: number | null;
  mid_yield_pct: number | null;
  quote_as_of: string | null;
  is_synthetic: boolean;
}

export interface SecurityDetail extends SecuritySummary {
  isin: string | null;
  cusip: string | null;
  coupon_frequency: number;
  day_count: string;
  issue_date: string;
  face_value: number;
  is_callable: boolean;
  is_putable: boolean;
  source: string;
  bid_price: number | null;
  ask_price: number | null;
  context: DataContext;
}

export interface CurvePoint {
  tenor_months: number;
  yield_pct: number;
}

export interface CurveSnapshot {
  curve_id: string;
  as_of: string;
  points: CurvePoint[];
  interpolation: string;
  context: DataContext;
}

export interface SeriesFreshness {
  dataset: string;
  last_as_of: string | null;
  last_loaded_at: string | null;
  rows_loaded: number;
  rows_rejected: number;
  status: 'fresh' | 'stale' | 'missing';
  is_synthetic: boolean;
}

export interface MarketOverview {
  currency: string;
  curve: CurveSnapshot | null;
  curve_change_bp_1w: Record<string, number>;
  avg_corporate_yield_pct: number | null;
  avg_spread_by_rating_bp: Record<string, number>;
  securities_count: number;
  freshness: SeriesFreshness[];
  context: DataContext;
}

export interface QualityIssue {
  id: number;
  dataset: string;
  rule: string;
  severity: string;
  message: string;
  raw_record: Record<string, string>;
  created_at: string;
}

export interface DataQualityReport {
  freshness: SeriesFreshness[];
  issues_by_rule: Record<string, number>;
  recent_issues: QualityIssue[];
  context: DataContext;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details: unknown;
  request_id: string | null;
}

export interface SecurityFilters {
  q?: string;
  bond_type?: string;
  rating?: string[];
  sector?: string[];
  maturity_from?: string;
  maturity_to?: string;
  min_yield?: number | null;
  max_yield?: number | null;
  sort?: string;
  page?: number;
  page_size?: number;
}
