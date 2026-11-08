import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ApiErrorBody, BondRow } from './api.models';
import { ApiService } from './api.service';
import { BondsFile, CurveFile, observations, priorIndex, queryBonds } from './static-data';

const row = (id: string, extra: Partial<BondRow>): BondRow =>
  ({
    id,
    name: id,
    issuer_name: 'X',
    sector: 'Energy',
    bond_type: 'corporate',
    rating: 'A',
    coupon_rate: 5,
    maturity_date: '2030-01-01',
    mid_price: 100,
    mid_yield_pct: 5,
    years: 4,
    modified_duration: 3.5,
    g_spread_bp: 100,
    ...extra,
  }) as BondRow;

const FILE: BondsFile = {
  items: [
    row('B1', { rating: 'BBB', g_spread_bp: 150, years: 5 }),
    row('B2', { rating: 'A', g_spread_bp: 90, years: 2 }),
    row('B3', { rating: 'BBB', g_spread_bp: null, years: 6 }),
    row('T1', { bond_type: 'treasury', rating: null, g_spread_bp: 1, years: 9 }),
  ],
  facets: { sectors: [], ratings: [], maturity_buckets: [], bond_types: [] },
  as_of: '2026-11-06',
  is_synthetic: true,
};

describe('queryBonds (mirrors the API)', () => {
  it('filters, sorts with missing values last, and computes stats', () => {
    const r = queryBonds(FILE, { rating: 'BBB', sort: '-g_spread_bp' });
    expect(r.items.map((b) => b.id)).toEqual(['B1', 'B3']);
    expect(r.stats.count).toBe(2);
    expect(r.stats.avg_g_spread_bp).toBe(150); // null spread excluded from the average
  });

  it('applies maturity buckets and paginates', () => {
    const r = queryBonds(FILE, { maturity: '3-7y', page: 1, page_size: 1, sort: 'id' });
    expect(r.total).toBe(2);
    expect(r.items.map((b) => b.id)).toEqual(['B1']);
  });
});

describe('curve lookups', () => {
  const curve: CurveFile = {
    curve_id: 'C',
    is_synthetic: false,
    units: '%',
    dates: ['2024-01-02', '2024-01-05'],
    tenors_months: [1.5, 120],
    yields: { '1.5': [null, 4.1], '120': [4.0, 4.2] },
    vintage: {
      ingestion_run_id: 1,
      file_sha256: null,
      source: 's',
      retrieved_at: null,
      license: null,
    },
  };

  it('resolves weekends to the prior observation within 7 days', () => {
    expect(priorIndex(curve.dates, '2024-01-07')).toBe(1);
    expect(priorIndex(curve.dates, '2023-12-01')).toBe(-1);
    const o = observations(curve, ['2024-01-07', '2024-01-02', '2020-01-01']).observations;
    expect(o.map((s) => s.status)).toEqual(['prior_observation', 'observed', 'unavailable']);
  });

  it('keeps unpublished tenors as gaps, never zero', () => {
    const o = observations(curve, ['2024-01-02'], [1.5, 120]).observations[0];
    expect(o.points).toEqual([
      { tenor_months: 1.5, yield_pct: null },
      { tenor_months: 120, yield_pct: 4.0 },
    ]);
  });
});

describe('ApiService', () => {
  let api: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  it('reads relative data paths (works under any base href) and caches them', () => {
    api.bonds({}).subscribe();
    api.bonds({ rating: 'A' }).subscribe();
    http.expectOne('data/bonds.json').flush(FILE);
    http.verify();
  });

  it('maps a missing bond to a not_found error and rejects unsafe ids', () => {
    let err: ApiErrorBody | undefined;
    api.analytics('NOPE').subscribe({ error: (e) => (err = e) });
    http.expectOne('data/bonds/NOPE.json').flush(null, { status: 404, statusText: 'Not Found' });
    expect(err?.code).toBe('not_found');

    let err2: ApiErrorBody | undefined;
    api.priceYield('../secret').subscribe({ error: (e) => (err2 = e) });
    expect(err2?.code).toBe('not_found');
    http.verify();
  });
});
