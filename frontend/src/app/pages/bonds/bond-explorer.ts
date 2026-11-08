import { Component, computed, effect, inject, signal } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Params, Router, RouterLink } from '@angular/router';
import { debounceTime, distinctUntilChanged, map, switchMap } from 'rxjs';

import { BondList, BondQuery, BondRow } from '../../core/api.models';
import { ApiService } from '../../core/api.service';
import { download, fmt } from '../../core/format';
import { Load, load } from '../../core/load';
import { ExplorerMemory } from './explorer-memory';

const PAGE_SIZE = 20;
const FILTERS = ['bond_type', 'sector', 'rating', 'maturity'] as const;
type FilterKey = (typeof FILTERS)[number];

interface Column {
  key: string;
  label: string;
  num?: boolean;
  title?: string;
}

const COLUMNS: Column[] = [
  { key: 'id', label: 'Bond' },
  { key: 'issuer_name', label: 'Issuer' },
  { key: 'rating', label: 'Rating' },
  { key: 'coupon_rate', label: 'Coupon %', num: true },
  { key: 'maturity_date', label: 'Maturity' },
  { key: 'years', label: 'Years', num: true, title: 'Years to maturity' },
  { key: 'mid_price', label: 'Price', num: true, title: 'Clean mid price per 100 face' },
  { key: 'mid_yield_pct', label: 'Yield %', num: true, title: 'Yield to maturity' },
  { key: 'modified_duration', label: 'Duration', num: true, title: 'Modified duration (years)' },
  { key: 'g_spread_bp', label: 'Spread bp', num: true, title: 'G-spread over the Treasury curve' },
];

@Component({
  selector: 'bm-bond-explorer',
  imports: [RouterLink],
  templateUrl: './bond-explorer.html',
})
export class BondExplorer {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly memory = inject(ExplorerMemory);
  protected readonly fmt = fmt;
  protected readonly columns = COLUMNS;
  protected readonly filterKeys = FILTERS;
  protected readonly labels: Record<FilterKey, string> = {
    bond_type: 'Type',
    sector: 'Sector',
    rating: 'Rating',
    maturity: 'Maturity',
  };

  /** The URL is the single source of truth for filters, sort and page. */
  protected readonly params = toSignal(this.route.queryParams, { initialValue: {} as Params });
  protected readonly query = computed<BondQuery>(() => {
    const p = this.params();
    return {
      q: p['q'] || undefined,
      bond_type: p['bond_type'] || undefined,
      sector: p['sector'] || undefined,
      rating: p['rating'] || undefined,
      maturity: p['maturity'] || undefined,
      sort: p['sort'] || 'maturity_date',
      page: Number(p['page']) || 1,
      page_size: PAGE_SIZE,
    };
  });

  protected readonly data = toSignal(
    toObservable(this.query).pipe(
      distinctUntilChanged((a, b) => JSON.stringify(a) === JSON.stringify(b)),
      switchMap((q) => this.api.bonds(q).pipe(load())),
    ),
    { initialValue: { state: 'loading' } as Load<BondList> },
  );
  /** Keep the last good result on screen while a new page loads (no flashing). */
  private readonly lastGood = signal<BondList | null>(null);
  protected readonly view = computed(() => {
    const d = this.data();
    return d.state === 'ok' ? d.data : this.lastGood();
  });
  protected readonly loading = computed(() => this.data().state === 'loading');
  protected readonly pages = computed(() =>
    Math.max(1, Math.ceil((this.view()?.total ?? 0) / PAGE_SIZE)),
  );
  protected readonly activeChips = computed(() =>
    FILTERS.filter((k) => this.params()[k]).map((k) => ({ key: k, value: this.params()[k] })),
  );

  protected readonly searchText = signal('');

  constructor() {
    effect(() => {
      const d = this.data();
      if (d.state === 'ok') this.lastGood.set(d.data);
    });
    effect(() => this.memory.lastQuery.set(this.params()));
    this.searchText.set(this.route.snapshot.queryParams['q'] ?? '');
    toObservable(this.searchText)
      .pipe(
        debounceTime(250),
        map((v) => v.trim()),
        distinctUntilChanged(),
      )
      .subscribe((q) => {
        if ((this.params()['q'] ?? '') !== q) this.update({ q: q || null, page: null });
      });
  }

  update(patch: Params): void {
    this.router.navigate([], { queryParams: patch, queryParamsHandling: 'merge' });
  }

  setFilter(key: FilterKey, value: string): void {
    this.update({ [key]: value || null, page: null });
  }

  clearAll(): void {
    this.searchText.set('');
    this.router.navigate([], { queryParams: {} });
  }

  sortBy(key: string): void {
    const current = this.query().sort;
    const numericFirstDesc = ['mid_yield_pct', 'g_spread_bp', 'modified_duration'].includes(key);
    const next =
      current === key
        ? `-${key}`
        : current === `-${key}`
          ? key
          : numericFirstDesc
            ? `-${key}`
            : key;
    this.update({ sort: next, page: null });
  }

  ariaSort(key: string): 'ascending' | 'descending' | 'none' {
    const s = this.query().sort;
    return s === key ? 'ascending' : s === `-${key}` ? 'descending' : 'none';
  }

  goTo(page: number): void {
    this.update({ page: page > 1 ? page : null });
  }

  open(row: BondRow): void {
    this.router.navigate(['/bonds', row.id]);
  }

  cell(row: BondRow, key: string): string {
    const v = (row as unknown as Record<string, unknown>)[key];
    if (typeof v === 'number') {
      const digits = key === 'g_spread_bp' ? 0 : key === 'years' ? 1 : key === 'mid_price' ? 2 : 2;
      return fmt(v, key === 'coupon_rate' ? 3 : digits);
    }
    return v === null || v === undefined ? '—' : String(v);
  }

  label(key: FilterKey, value: string): string {
    return key === 'bond_type' ? value[0].toUpperCase() + value.slice(1) : value;
  }

  exportCsv(): void {
    const all = { ...this.query(), page: 1, page_size: 200 };
    this.api.bonds(all).subscribe((r) => {
      const header = COLUMNS.map((c) => c.key);
      const esc = (v: unknown) => `"${String(v ?? '').replaceAll('"', '""')}"`;
      const lines = [
        `# bondMIND bond export; quotes as of ${r.as_of}; SYNTHETIC demo bonds; research only`,
        header.join(','),
        ...r.items.map((it) =>
          header.map((h) => esc((it as unknown as Record<string, unknown>)[h])).join(','),
        ),
      ];
      download(`bondmind-bonds-${r.as_of}.csv`, lines.join('\n'), 'text/csv');
    });
  }
}
