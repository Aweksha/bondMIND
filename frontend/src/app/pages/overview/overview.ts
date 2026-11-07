import { DatePipe, KeyValuePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';

import { ApiErrorBody, MarketOverview } from '../../core/api.models';
import { ApiService } from '../../core/api.service';
import { fmt, signed, tenorLabel } from '../../core/format';
import { StatusBadge } from '../../core/status-badge';

@Component({
  selector: 'bm-overview',
  imports: [DatePipe, KeyValuePipe, StatusBadge],
  templateUrl: './overview.html',
})
export class Overview {
  private readonly api = inject(ApiService);
  protected readonly data = signal<MarketOverview | null>(null);
  protected readonly error = signal<ApiErrorBody | null>(null);
  protected readonly fmt = fmt;
  protected readonly signed = signed;
  protected readonly tenorLabel = tenorLabel;
  protected readonly byKeyOrder = () => 0;

  constructor() {
    this.api.overview().subscribe({
      next: (d) => this.data.set(d),
      error: (e: ApiErrorBody) => this.error.set(e),
    });
  }

  yieldAt(tenor: number): number | null {
    return this.data()?.curve?.points.find((p) => p.tenor_months === tenor)?.yield_pct ?? null;
  }

  slopeBp(): number | null {
    const y10 = this.yieldAt(120);
    const y2 = this.yieldAt(24);
    return y10 === null || y2 === null ? null : (y10 - y2) * 100;
  }

  change(tenor: number): number | undefined {
    return this.data()?.curve_change_bp_1w[tenor];
  }
}
