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

// ---- v2 (Requirements 2.0) ---------------------------------------------------------

export interface CurveDates {
  curve_id: string;
  first_date: string | null;
  last_date: string | null;
  dates: string[];
  tenors_months: number[];
}

export interface CurveObservationSet {
  requested_date: string;
  observed_date: string | null;
  status: 'observed' | 'prior_observation' | 'unavailable';
  points: { tenor_months: number; yield_pct: number | null }[];
}

export interface CurveObservations {
  curve_id: string;
  is_synthetic: boolean;
  units: Record<string, string>;
  observations: CurveObservationSet[];
  vintage: Vintage;
  generated_at: string;
}

export interface Vintage {
  ingestion_run_id: number | null;
  file_sha256: string | null;
  source: string | null;
  retrieved_at: string | null;
  license: string | null;
}

export interface CashFlowRow {
  date: string;
  amount: number;
  kind: 'coupon' | 'principal';
  time_years: number;
  discount_factor: number;
  present_value: number;
}

export interface SecurityAnalytics {
  security_id: string;
  as_of: string;
  is_synthetic: boolean;
  quote: { as_of: string; source: string; bid: number; ask: number; mid_clean: number };
  pricing: { clean: number; dirty: number; accrued: number; ytm_pct: number };
  yield_risk: {
    macaulay_duration: number;
    modified_duration: number;
    convexity: number;
    dv01: number;
  };
  curve_risk: {
    z_spread_bp: number;
    g_spread_bp: number;
    effective_duration: number;
    effective_convexity: number;
    dv01: number;
    model_dirty: number;
  };
  cash_flows: CashFlowRow[];
  assumptions: Record<string, string | number>;
  warnings: string[];
  engine_version: string;
  calculated_at: string;
}

export interface HistoryPoint {
  as_of: string;
  mid_price: number;
  mid_yield_pct: number;
}

export interface SecurityHistory {
  security_id: string;
  is_synthetic: boolean;
  points: HistoryPoint[];
}

export interface ShockNode {
  tenorYears: number;
  bp: number;
}

export type SpreadMode = 'hold_constant' | 'shock';

export interface ScenarioRequest {
  curveId: string;
  baseDate: string;
  securityIds: string[];
  shockNodes: ShockNode[];
  spreadMode: SpreadMode;
  spreadShockBp: number;
}

export interface ValuationMetrics {
  clean: number;
  dirty: number;
  accrued: number;
  effective_duration: number;
  effective_convexity: number;
  dv01: number;
}

export interface ScenarioSecurityResult {
  security_id: string;
  status: 'ok' | 'error';
  error?: { code: string; message: string };
  is_synthetic?: boolean;
  quote_as_of?: string;
  z_spread_bp?: number;
  shocked_z_spread_bp?: number;
  base?: ValuationMetrics;
  shocked?: ValuationMetrics;
  change?: { clean: number; dirty: number; pct: number };
  approximation?: { method: string; estimated_change: number; error_vs_full: number } | null;
  assumptions?: Record<string, string | number>;
  warnings?: string[];
}

export interface ScenarioCurvePoint {
  tenor_months: number;
  base_par_pct: number;
  shock_bp: number;
  shocked_par_pct: number;
  base_zero_pct: number;
  shocked_zero_pct: number;
}

export interface ScenarioResponse {
  input: Record<string, unknown>;
  units: Record<string, string>;
  curve: {
    curve_id: string;
    requested_date: string;
    observed_date: string;
    points: ScenarioCurvePoint[];
    is_parallel: boolean;
  };
  results: ScenarioSecurityResult[];
  warnings: string[];
  methodology: Record<string, string>;
  vintage: Vintage;
  engine_version: string;
  calculated_at: string;
  request_id: string | null;
  disclaimer: string;
}
