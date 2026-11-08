/**
 * Pure helpers that answer the app's questions from the pre-computed JSON files.
 * They mirror the API's behaviour (filters, sort with missing values last, prior-observation
 * lookup within 7 days, gaps kept as null) so the static site and the API agree.
 */
import {
  BondList,
  BondQuery,
  BondRow,
  CurveDates,
  CurveObservationSet,
  CurveObservations,
  CurveSeries,
  Vintage,
} from './api.models';

export interface BondsFile {
  items: BondRow[];
  facets: BondList['facets'];
  as_of: string | null;
  is_synthetic: boolean;
}

export interface CurveFile {
  curve_id: string;
  is_synthetic: boolean;
  units: string;
  vintage: Vintage;
  dates: string[];
  tenors_months: number[];
  yields: Record<string, (number | null)[]>;
}

const RATING_ORDER: Record<string, number> = { AAA: 0, AA: 1, A: 2, BBB: 3, BB: 4, B: 5 };
const BUCKETS: Record<string, [number, number]> = {
  '0-3y': [0, 3],
  '3-7y': [3, 7],
  '7-10y': [7, 10],
  '10y+': [10, 100],
};
const LOOKBACK_DAYS = 7;

const tenorKey = (t: number) => String(t);

function mean(values: (number | null | undefined)[]): number | null {
  const v = values.filter((x): x is number => typeof x === 'number');
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}

export function queryBonds(file: BondsFile, q: BondQuery): BondList {
  const text = q.q?.trim().toLowerCase();
  let items = file.items.filter((b) => {
    if (
      text &&
      ![b.name, b.issuer_name, b.id, b.sector].some((f) => f?.toLowerCase().includes(text))
    )
      return false;
    if (q.bond_type && b.bond_type !== q.bond_type) return false;
    if (q.sector && b.sector !== q.sector) return false;
    if (q.rating && b.rating !== q.rating) return false;
    if (q.maturity && BUCKETS[q.maturity]) {
      const [lo, hi] = BUCKETS[q.maturity];
      if (b.years === null || b.years < lo || b.years >= hi) return false;
    }
    return true;
  });

  const sort = q.sort ?? 'maturity_date';
  const desc = sort.startsWith('-');
  const key = sort.replace(/^-/, '');
  const value = (b: BondRow): number | string | null => {
    const v = (b as unknown as Record<string, unknown>)[key];
    if (key === 'rating') return typeof v === 'string' ? (RATING_ORDER[v] ?? 99) : null;
    return v === undefined || v === null ? null : (v as number | string);
  };
  const present = items.filter((b) => value(b) !== null);
  const missing = items.filter((b) => value(b) === null).sort((a, b) => a.id.localeCompare(b.id));
  present.sort((a, b) => {
    const va = value(a)!;
    const vb = value(b)!;
    const cmp = va < vb ? -1 : va > vb ? 1 : a.id.localeCompare(b.id);
    return desc ? -cmp : cmp;
  });
  items = [...present, ...missing];

  const page = q.page ?? 1;
  const size = q.page_size ?? 25;
  return {
    items: items.slice((page - 1) * size, page * size),
    total: items.length,
    page,
    page_size: size,
    stats: {
      count: items.length,
      avg_ytm_pct: mean(items.map((b) => b.mid_yield_pct)),
      avg_modified_duration: mean(items.map((b) => b.modified_duration)),
      avg_g_spread_bp: mean(items.map((b) => b.g_spread_bp)),
      avg_coupon_pct: mean(items.map((b) => b.coupon_rate)),
    },
    facets: file.facets,
    as_of: file.as_of,
    is_synthetic: file.is_synthetic,
  };
}

function daysBetween(a: string, b: string): number {
  return (Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000;
}

/** Index of the latest observation on or before `day`, within the lookback window. */
export function priorIndex(dates: string[], day: string): number {
  let lo = 0;
  let hi = dates.length - 1;
  let best = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (dates[mid] <= day) {
      best = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return best >= 0 && daysBetween(dates[best], day) <= LOOKBACK_DAYS ? best : -1;
}

export function curveDates(c: CurveFile): CurveDates {
  return {
    curve_id: c.curve_id,
    first_date: c.dates[0] ?? null,
    last_date: c.dates.at(-1) ?? null,
    dates: c.dates,
    tenors_months: c.tenors_months,
  };
}

export function observations(c: CurveFile, dates: string[], tenors?: number[]): CurveObservations {
  const sets: CurveObservationSet[] = dates.map((d) => {
    const i = priorIndex(c.dates, d);
    if (i < 0) return { requested_date: d, observed_date: null, status: 'unavailable', points: [] };
    const available = c.tenors_months.filter((t) => c.yields[tenorKey(t)][i] !== null);
    const wanted = tenors?.length ? tenors : available;
    return {
      requested_date: d,
      observed_date: c.dates[i],
      status: c.dates[i] === d ? 'observed' : 'prior_observation',
      points: wanted.map((t) => ({
        tenor_months: t,
        yield_pct: c.yields[tenorKey(t)]?.[i] ?? null,
      })),
    };
  });
  return {
    curve_id: c.curve_id,
    is_synthetic: c.is_synthetic,
    units: { yield_pct: c.units, tenor_months: 'months' },
    observations: sets,
    vintage: c.vintage,
    generated_at: new Date().toISOString(),
  };
}

export function series(c: CurveFile, tenors: number[], from?: string, to?: string): CurveSeries {
  const idx = c.dates
    .map((d, i) => [d, i] as const)
    .filter(([d]) => (!from || d >= from) && (!to || d <= to))
    .map(([, i]) => i);
  return {
    curve_id: c.curve_id,
    dates: idx.map((i) => c.dates[i]),
    series: Object.fromEntries(
      tenors.map((t) => [tenorKey(t), idx.map((i) => c.yields[tenorKey(t)]?.[i] ?? null)]),
    ),
    units: 'percent',
  };
}
