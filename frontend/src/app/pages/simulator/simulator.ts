import { Component, computed, inject, signal } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { distinctUntilChanged, of, switchMap } from 'rxjs';

import { PriceYieldPoint } from '../../core/api.models';
import { ApiService } from '../../core/api.service';
import { fmt, signed } from '../../core/format';
import { load } from '../../core/load';
import { Chart, ChartOption } from '../../shared/chart';

const LIMIT = 300;

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

@Component({
  selector: 'bm-simulator',
  imports: [Chart, RouterLink],
  templateUrl: './simulator.html',
})
export class Simulator {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  protected readonly fmt = fmt;
  protected readonly signed = signed;
  protected readonly limit = LIMIT;
  protected readonly presets = [-200, -100, -50, 50, 100, 200];

  private readonly qp = this.route.snapshot.queryParamMap;
  protected readonly bondId = signal(this.qp.get('bond') ?? 'BM-T-0007');
  protected readonly shift = signal(this.clamp(Number(this.qp.get('shift') ?? 100)));
  protected readonly showDuration = signal(true);
  protected readonly showConvexity = signal(false);

  protected readonly bondList = toSignal(
    this.api.bonds({ page_size: 200, sort: 'maturity_date' }).pipe(load()),
    { initialValue: { state: 'loading' } as const },
  );
  protected readonly treasuries = computed(() => {
    const b = this.bondList();
    return b.state === 'ok' ? b.data.items.filter((i) => i.bond_type === 'treasury') : [];
  });
  protected readonly corporates = computed(() => {
    const b = this.bondList();
    return b.state === 'ok' ? b.data.items.filter((i) => i.bond_type === 'corporate') : [];
  });

  protected readonly curve = toSignal(
    toObservable(this.bondId).pipe(
      distinctUntilChanged(),
      switchMap((id) => (id ? this.api.priceYield(id).pipe(load()) : of(null))),
    ),
    { initialValue: null },
  );
  protected readonly data = computed(() => {
    const c = this.curve();
    return c?.state === 'ok' ? c.data : null;
  });
  private readonly byShift = computed(() => {
    const m = new Map<number, PriceYieldPoint>();
    for (const p of this.data()?.points ?? []) m.set(p.shift_bp, p);
    return m;
  });
  protected readonly base = computed(() => this.byShift().get(0) ?? null);
  protected readonly point = computed(() => this.byShift().get(this.shift()) ?? null);

  protected readonly result = computed(() => {
    const b = this.base();
    const p = this.point();
    if (!b || !p) return null;
    return {
      change: p.clean - b.clean,
      pct: (p.clean / b.clean - 1) * 100,
      durError: p.duration_estimate - p.clean,
      convError: p.convexity_estimate - p.clean,
    };
  });

  protected readonly option = computed<ChartOption>(() => {
    const d = this.data();
    const p = this.point();
    if (!d || !p) return {};
    const pts = d.points;
    const xMin = pts[0].ytm_pct;
    const exact = token('--series-1');
    const neg = token('--neg');
    const muted = token('--text-muted');
    const series: unknown[] = [
      {
        type: 'line',
        name: 'Actual price',
        data: pts.map((q) => [q.ytm_pct, q.clean]),
        showSymbol: false,
        lineStyle: { width: 3, color: exact },
        itemStyle: { color: exact },
        z: 3,
      },
    ];
    if (this.showDuration()) {
      series.push({
        type: 'line',
        name: 'Duration estimate (straight line)',
        data: pts.map((q) => [q.ytm_pct, q.duration_estimate]),
        showSymbol: false,
        lineStyle: { width: 1.5, color: muted },
        itemStyle: { color: muted },
      });
      series.push({
        type: 'line',
        name: 'Estimate error',
        data: [
          [p.ytm_pct, p.clean],
          [p.ytm_pct, p.duration_estimate],
        ],
        showSymbol: false,
        lineStyle: { width: 4, color: neg },
        itemStyle: { color: neg },
        z: 4,
      });
    }
    if (this.showConvexity()) {
      series.push({
        type: 'line',
        name: 'Duration + convexity estimate',
        data: pts.map((q) => [q.ytm_pct, q.convexity_estimate]),
        showSymbol: false,
        lineStyle: { width: 1.5, type: 'dashed', color: token('--series-3') },
        itemStyle: { color: token('--series-3') },
      });
    }
    const guide = (y: number, x: number, name: string) => ({
      type: 'line',
      name,
      data: [
        [xMin, y],
        [x, y],
      ],
      showSymbol: false,
      silent: true,
      lineStyle: { width: 1, type: 'dotted', color: muted },
      tooltip: { show: false },
    });
    series.push(
      guide(d.base.clean, d.base.ytm_pct, 'guide-base'),
      guide(p.clean, p.ytm_pct, 'guide-new'),
    );
    series.push({
      type: 'scatter',
      name: 'Today',
      data: [[d.base.ytm_pct, d.base.clean]],
      symbolSize: 12,
      itemStyle: { color: token('--text') },
      label: { show: true, formatter: 'today', position: 'top', color: muted },
      z: 5,
    });
    series.push({
      type: 'scatter',
      name: 'After the change',
      data: [[p.ytm_pct, p.clean]],
      symbolSize: 14,
      itemStyle: { color: exact, borderColor: token('--text'), borderWidth: 2 },
      z: 6,
    });
    return {
      grid: { left: 56, right: 20, top: 44, bottom: 44 },
      legend: {
        top: 0,
        data: [
          'Actual price',
          'Duration estimate (straight line)',
          'Duration + convexity estimate',
          'Estimate error',
        ],
      },
      tooltip: {
        trigger: 'axis',
        formatter: (items: { data: number[]; seriesName: string }[]) => {
          const it = items.find((i) => i.seriesName === 'Actual price');
          return it ? `Yield ${it.data[0].toFixed(2)}%<br/>Price ${it.data[1].toFixed(3)}` : '';
        },
      },
      xAxis: {
        type: 'value',
        name: 'Yield to maturity (%)',
        nameLocation: 'middle',
        nameGap: 28,
        scale: true,
        axisLabel: { formatter: (v: number) => `${v.toFixed(1)}%` },
      },
      yAxis: { type: 'value', name: 'Price (per 100)', scale: true },
      series,
    };
  });

  clamp(v: number): number {
    return Number.isFinite(v) ? Math.max(-LIMIT, Math.min(LIMIT, Math.round(v))) : 0;
  }

  setShift(raw: string | number): void {
    this.shift.set(this.clamp(Number(raw)));
    this.sync();
  }

  setBond(id: string): void {
    this.bondId.set(id);
    this.sync();
  }

  private sync(): void {
    this.router.navigate([], {
      queryParams: { bond: this.bondId(), shift: this.shift() },
      replaceUrl: true,
    });
  }
}
