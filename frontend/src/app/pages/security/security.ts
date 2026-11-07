import { Component, effect, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiErrorBody, SecurityDetail } from '../../core/api.models';
import { ApiService } from '../../core/api.service';
import { fmt } from '../../core/format';

@Component({
  selector: 'bm-security',
  imports: [RouterLink],
  template: `
    <p><a routerLink="/screener">← Screener</a></p>
    @if (error(); as e) {
      <div class="panel error" role="alert">{{ e.message }}</div>
    } @else if (sec(); as s) {
      <h1>
        {{ s.name }} <span class="muted">{{ s.id }}</span>
      </h1>
      <p class="muted">
        {{ s.issuer_name }} · {{ s.sector }} · {{ s.rating ?? 'NR' }} · {{ s.currency }}
        @if (s.is_synthetic) {
          <span class="tag">synthetic</span>
        }
      </p>

      <section class="tiles" aria-label="Pricing">
        <div class="tile">
          <div class="tile-label">Clean mid</div>
          <div class="tile-value">{{ fmt(s.mid_price, 3) }}</div>
          <div class="tile-sub">bid {{ fmt(s.bid_price, 3) }} / ask {{ fmt(s.ask_price, 3) }}</div>
        </div>
        <div class="tile">
          <div class="tile-label">YTM (mid)</div>
          <div class="tile-value">{{ fmt(s.mid_yield_pct, 3) }}%</div>
          <div class="tile-sub">as of {{ s.quote_as_of ?? '—' }}</div>
        </div>
        <div class="tile">
          <div class="tile-label">Coupon</div>
          <div class="tile-value">{{ fmt(s.coupon_rate, 3) }}%</div>
          <div class="tile-sub">{{ s.coupon_frequency }}× per year</div>
        </div>
        <div class="tile">
          <div class="tile-label">Maturity</div>
          <div class="tile-value">{{ s.maturity_date }}</div>
          <div class="tile-sub">issued {{ s.issue_date }}</div>
        </div>
      </section>

      <div class="grid-2">
        <section class="panel" aria-labelledby="terms-h">
          <h2 id="terms-h">Terms</h2>
          <dl class="terms">
            <dt>Bond type</dt>
            <dd>{{ s.bond_type }}</dd>
            <dt>Day count</dt>
            <dd>{{ s.day_count }}</dd>
            <dt>Face value</dt>
            <dd>{{ s.face_value }}</dd>
            <dt>ISIN / CUSIP</dt>
            <dd>{{ s.isin ?? '—' }} / {{ s.cusip ?? '—' }}</dd>
            <dt>Callable / putable</dt>
            <dd>{{ s.is_callable ? 'Yes' : 'No' }} / {{ s.is_putable ? 'Yes' : 'No' }}</dd>
            <dt>Source</dt>
            <dd>{{ s.source }}</dd>
          </dl>
        </section>
        <section class="panel">
          <h2>Coming in M1</h2>
          <p class="muted">
            Cash-flow schedule, accrued interest, dirty price, duration, convexity, DV01, price
            history, curve position and peers, all with calculation assumptions shown.
          </p>
        </section>
      </div>
    } @else {
      <p class="muted" aria-live="polite">Loading…</p>
    }
  `,
})
export class SecurityPage {
  private readonly api = inject(ApiService);
  readonly id = input.required<string>();
  protected readonly sec = signal<SecurityDetail | null>(null);
  protected readonly error = signal<ApiErrorBody | null>(null);
  protected readonly fmt = fmt;

  constructor() {
    effect(() => {
      const id = this.id();
      this.sec.set(null);
      this.error.set(null);
      this.api.security(id).subscribe({
        next: (s) => this.sec.set(s),
        error: (e: ApiErrorBody) => this.error.set(e),
      });
    });
  }
}
