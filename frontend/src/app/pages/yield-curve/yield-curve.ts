import { Component, computed, inject, signal } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { distinctUntilChanged, of, switchMap } from 'rxjs';

import { CurveObservationSet } from '../../core/api.models';
import { ApiService } from '../../core/api.service';
import { download, fmt, shiftDate, shiftDays, signed, tenorLabel } from '../../core/format';
import { load } from '../../core/load';
import { Chart, ChartOption } from '../../shared/chart';

const CURVE = 'USD-UST-PAR';
type Preset = '1D' | '1W' | '1M' | '3M' | '6M' | '1Y' | '3Y';
const PRESETS: Preset[] = ['1D', '1W', '1M', '3M', '6M', '1Y', '3Y'];
const TILE_TENORS = [3, 24, 60, 120, 360];
const SPREADS = [
  { id: '2s10s', label: '2s10s', long: 120, short: 24, help: '10Y − 2Y' },
  { id: '3m10y', label: '3M10Y', long: 120, short: 3, help: '10Y − 3M' },
  { id: '5s30s', label: '5s30s', long: 360, short: 60, help: '30Y − 5Y' },
];

@Component({
  selector: 'bm-yield-curve',
  imports: [Chart],
  templateUrl: './yield-curve.html',
})
export class YieldCurve {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  protected readonly fmt = fmt;
  protected readonly signed = signed;
  protected readonly tenorLabel = tenorLabel;
  protected readonly presets = PRESETS;
  protected readonly spreadDefs = SPREADS;

  protected readonly dateInfo = toSignal(this.api.curveDates(CURVE).pipe(load()), {
    initialValue: { state: 'loading' } as const,
  });
  private readonly allDates = computed(() => {
    const d = this.dateInfo();
    return d.state === 'ok' ? d.data.dates : [];
  });
  protected readonly minDate = computed(() => this.allDates()[0] ?? null);
  protected readonly maxDate = computed(() => this.allDates().at(-1) ?? null);

  // URL state: ?date=2026-11-06&compare=1M  (or compare=2025-01-02)
  private readonly qp = this.route.snapshot.queryParamMap;
  protected readonly chosenDate = signal<string | null>(this.qp.get('date'));
  protected readonly compare = signal<string>(this.qp.get('compare') ?? '1M');

  protected readonly currentDate = computed(() => this.chosenDate() ?? this.maxDate());
  protected readonly isPreset = computed(() => (PRESETS as string[]).includes(this.compare()));
  protected readonly compareDate = computed(() => {
    const cur = this.currentDate();
    const c = this.compare();
    if (!cur) return null;
    if (!this.isPreset()) return c;
    if (c === '1D') {
      const ds = this.allDates();
      const i = ds.findIndex((d) => d >= cur);
      const idx = i === -1 ? ds.length - 1 : ds[i] === cur ? i : i - 1;
      return ds[Math.max(0, idx - 1)] ?? null;
    }
    const n = Number(c.slice(0, -1));
    if (c.endsWith('W')) return shiftDays(cur, -7 * n);
    return c.endsWith('M') ? shiftDate(cur, { months: -n }) : shiftDate(cur, { years: -n });
  });

  private readonly pair = computed(() => {
    const a = this.currentDate();
    const b = this.compareDate();
    return a && b ? [a, b] : null;
  });
  protected readonly obs = toSignal(
    toObservable(this.pair).pipe(
      distinctUntilChanged((x, y) => JSON.stringify(x) === JSON.stringify(y)),
      switchMap((p) => (p ? this.api.observations(CURVE, p).pipe(load()) : of(null))),
    ),
    { initialValue: null },
  );
  protected readonly series = toSignal(
    toObservable(this.currentDate).pipe(
      distinctUntilChanged(),
      switchMap((d) =>
        d
          ? this.api
              .curveSeries(CURVE, [3, 24, 60, 120, 360], shiftDate(d, { years: -1 }), d)
              .pipe(load())
          : of(null),
      ),
    ),
    { initialValue: null },
  );

  protected readonly current = computed<CurveObservationSet | null>(() => {
    const o = this.obs();
    return o?.state === 'ok' ? o.data.observations[0] : null;
  });
  protected readonly prior = computed<CurveObservationSet | null>(() => {
    const o = this.obs();
    return o?.state === 'ok' ? o.data.observations[1] : null;
  });

  private value(set: CurveObservationSet | null, tenor: number): number | null {
    return set?.points.find((p) => p.tenor_months === tenor)?.yield_pct ?? null;
  }

  protected readonly rows = computed(() => {
    const cur = this.current();
    const pri = this.prior();
    const tenors = new Set<number>();
    for (const s of [cur, pri]) for (const p of s?.points ?? []) tenors.add(p.tenor_months);
    return [...tenors]
      .sort((a, b) => a - b)
      .map((t) => {
        const a = this.value(cur, t);
        const b = this.value(pri, t);
        return {
          tenor: t,
          current: a,
          prior: b,
          change: a !== null && b !== null ? (a - b) * 100 : null,
        };
      });
  });

  protected readonly tiles = computed(() =>
    TILE_TENORS.map(
      (t) =>
        this.rows().find((r) => r.tenor === t) ?? {
          tenor: t,
          current: null,
          prior: null,
          change: null,
        },
    ),
  );

  protected readonly spreads = computed(() => {
    const s = this.series();
    const data = s?.state === 'ok' ? s.data : null;
    return SPREADS.map((def) => {
      const cur = this.value(this.current(), def.long);
      const curS = this.value(this.current(), def.short);
      const pri = this.value(this.prior(), def.long);
      const priS = this.value(this.prior(), def.short);
      const now = cur !== null && curS !== null ? (cur - curS) * 100 : null;
      const then = pri !== null && priS !== null ? (pri - priS) * 100 : null;
      const hist: [string, number][] = [];
      if (data) {
        const L = data.series[String(def.long)];
        const S = data.series[String(def.short)];
        data.dates.forEach((d, i) => {
          if (L[i] != null && S[i] != null) hist.push([d, (L[i]! - S[i]!) * 100]);
        });
      }
      const values = hist.map((h) => h[1]);
      return {
        ...def,
        now,
        change: now !== null && then !== null ? now - then : null,
        min: values.length ? Math.min(...values) : null,
        max: values.length ? Math.max(...values) : null,
        yearAgo: hist[0]?.[1] ?? null,
        option: {
          grid: { left: 0, right: 0, top: 4, bottom: 0 },
          xAxis: { type: 'time', show: false },
          yAxis: { type: 'value', show: false, scale: true },
          tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${v.toFixed(0)} bp` },
          series: [
            {
              type: 'line',
              data: hist,
              showSymbol: false,
              areaStyle: { opacity: 0.12 },
              lineStyle: { width: 1.5 },
            },
          ],
        } as ChartOption,
      };
    });
  });

  protected readonly chartOption = computed<ChartOption>(() => {
    const rows = this.rows();
    const cur = this.current();
    const pri = this.prior();
    const label = (s: CurveObservationSet | null) =>
      s?.observed_date ? s.observed_date : s ? `${s.requested_date} (no data)` : '';
    return {
      grid: { left: 52, right: 20, top: 40, bottom: 40 },
      legend: { top: 0 },
      tooltip: {
        trigger: 'axis',
        formatter: (items: { dataIndex: number }[]) => {
          const r = rows[items[0]?.dataIndex ?? 0];
          if (!r) return '';
          const f = (v: number | null) => (v === null ? 'n/a' : `${v.toFixed(2)}%`);
          return `<b>${tenorLabel(r.tenor)}</b><br/>${label(cur)}: ${f(r.current)}<br/>${label(pri)}: ${f(r.prior)}<br/>Change: ${
            r.change === null ? 'n/a' : `${signed(r.change, 1)} bp`
          }`;
        },
      },
      xAxis: {
        type: 'category',
        data: rows.map((r) => tenorLabel(r.tenor)),
        name: 'Maturity',
        nameLocation: 'middle',
        nameGap: 26,
      },
      yAxis: {
        type: 'value',
        scale: true,
        name: 'Yield %',
        axisLabel: { formatter: (v: number) => `${v.toFixed(1)}%` },
      },
      series: [
        {
          type: 'line',
          name: label(cur),
          data: rows.map((r) => r.current),
          smooth: 0.25,
          symbolSize: 8,
          lineStyle: { width: 3 },
          areaStyle: { opacity: 0.1 },
          connectNulls: false,
        },
        {
          type: 'line',
          name: label(pri),
          data: rows.map((r) => r.prior),
          smooth: 0.25,
          symbol: 'rect',
          symbolSize: 6,
          lineStyle: { type: 'dashed', width: 2 },
          connectNulls: false,
        },
      ],
    };
  });

  setDate(value: string): void {
    if (!value) return;
    this.chosenDate.set(value);
    this.sync();
  }

  setCompare(value: string): void {
    if (!value) return;
    this.compare.set(value);
    this.sync();
  }

  private sync(): void {
    this.router.navigate([], {
      queryParams: { date: this.chosenDate(), compare: this.compare() },
      replaceUrl: true,
    });
  }

  exportCsv(): void {
    const cur = this.current();
    const pri = this.prior();
    const lines = [
      '# bondMIND Treasury par yield curve comparison; source: U.S. Department of the Treasury; units: percent, change in bp',
      `tenor,${cur?.observed_date ?? 'current'},${pri?.observed_date ?? 'prior'},change_bp`,
      ...this.rows().map(
        (r) =>
          `${tenorLabel(r.tenor)},${r.current ?? ''},${r.prior ?? ''},${r.change?.toFixed(1) ?? ''}`,
      ),
    ];
    download(`bondmind-yield-curve-${cur?.observed_date}.csv`, lines.join('\n'), 'text/csv');
  }
}
