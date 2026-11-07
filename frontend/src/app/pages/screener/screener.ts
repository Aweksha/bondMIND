import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { EMPTY, expand, reduce } from 'rxjs';

import { ApiErrorBody, Page, SecurityFilters, SecuritySummary } from '../../core/api.models';
import { ApiService } from '../../core/api.service';
import { fmt } from '../../core/format';

const RATINGS = ['AAA', 'AA', 'A', 'BBB', 'BB'];
const COLUMNS: { key: string; label: string; numeric?: boolean; sortable?: boolean }[] = [
  { key: 'id', label: 'ID', sortable: true },
  { key: 'name', label: 'Name', sortable: true },
  { key: 'sector', label: 'Sector' },
  { key: 'rating', label: 'Rating', sortable: true },
  { key: 'coupon_rate', label: 'Coupon %', numeric: true, sortable: true },
  { key: 'maturity_date', label: 'Maturity', sortable: true },
  { key: 'mid_price', label: 'Price', numeric: true, sortable: true },
  { key: 'mid_yield_pct', label: 'YTM %', numeric: true, sortable: true },
];

function addYears(years: number | null): string | undefined {
  if (years === null || years === undefined || Number.isNaN(years)) return undefined;
  const d = new Date();
  d.setFullYear(d.getFullYear() + years);
  return d.toISOString().slice(0, 10);
}

@Component({
  selector: 'bm-screener',
  imports: [FormsModule, RouterLink],
  templateUrl: './screener.html',
})
export class Screener {
  private readonly api = inject(ApiService);
  protected readonly ratings = RATINGS;
  protected readonly columns = COLUMNS;
  protected readonly fmt = fmt;

  // Filter form state
  q = '';
  bondType = '';
  selectedRatings = new Set<string>();
  minYears: number | null = null;
  maxYears: number | null = null;
  minYield: number | null = null;
  maxYield: number | null = null;

  protected readonly sort = signal('maturity_date');
  protected readonly page = signal(1);
  protected readonly pageSize = 25;
  protected readonly result = signal<Page<SecuritySummary> | null>(null);
  protected readonly error = signal<ApiErrorBody | null>(null);
  protected readonly loading = signal(false);
  protected readonly pages = computed(() =>
    Math.max(1, Math.ceil((this.result()?.total ?? 0) / this.pageSize)),
  );

  constructor() {
    this.load();
  }

  private filters(): SecurityFilters {
    return {
      q: this.q.trim() || undefined,
      bond_type: this.bondType || undefined,
      rating: [...this.selectedRatings],
      maturity_from: addYears(this.minYears),
      maturity_to: addYears(this.maxYears),
      min_yield: this.minYield,
      max_yield: this.maxYield,
      sort: this.sort(),
    };
  }

  load(): void {
    this.loading.set(true);
    this.api
      .securities({ ...this.filters(), page: this.page(), page_size: this.pageSize })
      .subscribe({
        next: (r) => {
          this.result.set(r);
          this.error.set(null);
          this.loading.set(false);
        },
        error: (e: ApiErrorBody) => {
          this.error.set(e);
          this.loading.set(false);
        },
      });
  }

  apply(): void {
    this.page.set(1);
    this.load();
  }

  reset(): void {
    this.q = '';
    this.bondType = '';
    this.selectedRatings.clear();
    this.minYears = this.maxYears = this.minYield = this.maxYield = null;
    this.sort.set('maturity_date');
    this.apply();
  }

  toggleRating(r: string, checked: boolean): void {
    if (checked) this.selectedRatings.add(r);
    else this.selectedRatings.delete(r);
  }

  sortBy(key: string): void {
    this.sort.set(this.sort() === key ? `-${key}` : key);
    this.apply();
  }

  ariaSort(key: string): 'ascending' | 'descending' | 'none' {
    const s = this.sort();
    return s === key ? 'ascending' : s === `-${key}` ? 'descending' : 'none';
  }

  goTo(page: number): void {
    this.page.set(page);
    this.load();
  }

  value(row: SecuritySummary, key: string): string {
    const v = (row as unknown as Record<string, unknown>)[key];
    if (typeof v === 'number')
      return fmt(v, key === 'mid_yield_pct' ? 3 : key === 'coupon_rate' ? 3 : 2);
    return v === null || v === undefined ? '—' : String(v);
  }

  /** Exports every row matching the current filters, not just the visible page. */
  exportCsv(): void {
    const base = { ...this.filters(), page_size: 200 };
    this.api
      .securities({ ...base, page: 1 })
      .pipe(
        expand((p) =>
          p.page * p.page_size < p.total
            ? this.api.securities({ ...base, page: p.page + 1 })
            : EMPTY,
        ),
        reduce((rows, p) => rows.concat(p.items), [] as SecuritySummary[]),
      )
      .subscribe((rows) => {
        const ctx = this.result()?.context;
        const header = [...COLUMNS.map((c) => c.key), 'quote_as_of', 'is_synthetic'];
        const esc = (v: unknown) => `"${String(v ?? '').replaceAll('"', '""')}"`;
        const lines = [
          `# bondMIND export; market date ${ctx?.as_of}; synthetic=${ctx?.is_synthetic}; research only`,
          header.join(','),
          ...rows.map((r) =>
            header.map((h) => esc((r as unknown as Record<string, unknown>)[h])).join(','),
          ),
        ];
        const url = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' }));
        const a = Object.assign(document.createElement('a'), {
          href: url,
          download: `bondmind-screener-${ctx?.as_of ?? 'export'}.csv`,
        });
        a.click();
        URL.revokeObjectURL(url);
      });
  }
}
