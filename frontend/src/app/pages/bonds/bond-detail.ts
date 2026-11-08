import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { of, switchMap } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { fmt, shiftDate } from '../../core/format';
import { load } from '../../core/load';
import { Chart, ChartOption } from '../../shared/chart';
import { ExplorerMemory } from './explorer-memory';

type Range = '3M' | '6M' | '1Y' | 'All';

@Component({
  selector: 'bm-bond-detail',
  imports: [Chart, RouterLink],
  templateUrl: './bond-detail.html',
})
export class BondDetail {
  private readonly api = inject(ApiService);
  protected readonly memory = inject(ExplorerMemory);
  protected readonly fmt = fmt;

  readonly id = input.required<string>();
  protected readonly range = signal<Range>('1Y');
  protected readonly metric = signal<'yield' | 'price'>('yield');
  protected readonly ranges: Range[] = ['3M', '6M', '1Y', 'All'];

  private readonly id$ = toObservable(this.id);
  protected readonly analytics = toSignal(
    this.id$.pipe(switchMap((id) => this.api.analytics(id).pipe(load()))),
    { initialValue: { state: 'loading' } as const },
  );
  protected readonly info = toSignal(
    this.id$.pipe(switchMap((id) => this.api.security(id).pipe(load()))),
    { initialValue: { state: 'loading' } as const },
  );
  protected readonly history = toSignal(
    this.id$.pipe(switchMap((id) => this.api.history(id).pipe(load()))),
    { initialValue: { state: 'loading' } as const },
  );
  /** Human title, e.g. "Harborview Communications 5.875% 2037". */
  protected readonly title = computed(() => {
    const i = this.info();
    if (i.state !== 'ok') return null;
    const issuer = i.data.issuer_name.replace(/\s*\(synthetic[^)]*\)/, '');
    return `${issuer} ${i.data.coupon_rate.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')}% ${i.data.maturity_date.slice(0, 4)}`;
  });

  private readonly asOf = computed(() => {
    const a = this.analytics();
    return a.state === 'ok' ? a.data.as_of : null;
  });
  protected readonly curve = toSignal(
    toObservable(this.asOf).pipe(
      switchMap((d) => (d ? this.api.observations('USD-UST-PAR', [d]).pipe(load()) : of(null))),
    ),
    { initialValue: null },
  );

  protected readonly points = computed(() => {
    const h = this.history();
    if (h.state !== 'ok' || !h.data.points.length) return [];
    const pts = h.data.points;
    const r = this.range();
    if (r === 'All') return pts;
    const last = pts[pts.length - 1].as_of;
    const from = shiftDate(last, { months: r === '3M' ? -3 : r === '6M' ? -6 : -12 });
    return pts.filter((p) => p.as_of >= from);
  });

  protected readonly historyOption = computed<ChartOption>(() => {
    const isYield = this.metric() === 'yield';
    return {
      grid: { left: 52, right: 16, top: 16, bottom: 56 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      xAxis: { type: 'time' },
      yAxis: {
        type: 'value',
        scale: true,
        name: isYield ? 'Yield %' : 'Price',
        axisLabel: { formatter: (v: number) => v.toFixed(isYield ? 2 : 1) },
      },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 8 }],
      series: [
        {
          type: 'line',
          name: isYield ? 'Yield to maturity (%)' : 'Clean price',
          showSymbol: false,
          areaStyle: { opacity: 0.08 },
          data: this.points().map((p) => [p.as_of, isYield ? p.mid_yield_pct : p.mid_price]),
        },
      ],
    };
  });

  protected readonly curveOption = computed<ChartOption>(() => {
    const c = this.curve();
    const a = this.analytics();
    const obs = c?.state === 'ok' ? c.data.observations[0] : null;
    const series: unknown[] = [
      {
        type: 'line',
        name: `Treasury curve ${obs?.observed_date ?? ''}`,
        data: (obs?.points ?? []).map((p) => [p.tenor_months / 12, p.yield_pct]),
        symbolSize: 5,
      },
    ];
    if (a.state === 'ok' && a.data.cash_flows.length) {
      series.push({
        type: 'scatter',
        name: 'This bond',
        symbol: 'diamond',
        symbolSize: 14,
        data: [
          [a.data.cash_flows[a.data.cash_flows.length - 1].time_years, a.data.pricing.ytm_pct],
        ],
      });
    }
    return {
      grid: { left: 44, right: 12, top: 48, bottom: 36 },
      legend: { top: 0, left: 0 },
      tooltip: {
        trigger: 'item',
        formatter: (p: { seriesName: string; value: number[] }) =>
          `${p.seriesName}<br/>${p.value[0].toFixed(1)} yrs · ${p.value[1].toFixed(2)}%`,
      },
      xAxis: {
        type: 'value',
        name: 'Years to maturity',
        min: 0,
        max: 30,
        nameLocation: 'middle',
        nameGap: 24,
      },
      yAxis: { type: 'value', scale: true, name: 'Yield %' },
      series,
    };
  });

  entries(obj: Record<string, unknown>): [string, unknown][] {
    return Object.entries(obj);
  }
}
