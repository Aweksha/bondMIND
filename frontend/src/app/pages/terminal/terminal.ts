import {
  Component,
  ElementRef,
  HostListener,
  computed,
  effect,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { debounceTime, distinctUntilChanged, map, of, switchMap } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { fmt, shiftDate, signed, tenorLabel } from '../../core/format';
import { Load, load } from '../../core/load';
import { ResearchStore } from '../../core/research-store';
import { Chart, ChartOption } from '../../shared/chart';

type Range = '3M' | '6M' | '1Y' | 'All';

@Component({
  selector: 'bm-terminal',
  imports: [Chart, RouterLink],
  templateUrl: './terminal.html',
})
export class Terminal {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  protected readonly store = inject(ResearchStore);
  protected readonly fmt = fmt;
  protected readonly signed = signed;
  protected readonly tenorLabel = tenorLabel;

  /** Route param from /terminal/security/:id */
  readonly id = input<string | undefined>();
  private readonly searchBox = viewChild<ElementRef<HTMLInputElement>>('searchBox');

  protected readonly range = signal<Range>('1Y');
  protected readonly metric = signal<'price' | 'yield'>('yield');
  protected readonly ranges: Range[] = ['3M', '6M', '1Y', 'All'];

  // --- Search panel (debounced, latest request wins) ----------------------------------
  protected readonly results = toSignal(
    toObservable(this.store.terminalQuery).pipe(
      debounceTime(250),
      map((q) => q.trim()),
      distinctUntilChanged(),
      switchMap((q) =>
        this.api
          .securities({ q: q || undefined, page_size: 100, sort: 'maturity_date' })
          .pipe(load()),
      ),
    ),
    { initialValue: { state: 'loading' } as Load<never> },
  );

  // --- Dependent panels: switchMap cancels stale requests on a new selection -----------
  private readonly selected$ = toObservable(this.store.selectedSecurityId);
  protected readonly analytics = toSignal(
    this.selected$.pipe(switchMap((id) => (id ? this.api.analytics(id).pipe(load()) : of(null)))),
    { initialValue: null },
  );
  protected readonly history = toSignal(
    this.selected$.pipe(switchMap((id) => (id ? this.api.history(id).pipe(load()) : of(null)))),
    { initialValue: null },
  );
  private readonly asOf = computed(() => {
    const a = this.analytics();
    return a?.state === 'ok' ? a.data.as_of : null;
  });
  protected readonly curve = toSignal(
    toObservable(this.asOf).pipe(
      switchMap((d) =>
        d ? this.api.observations(this.store.curveId(), [d]).pipe(load()) : of(null),
      ),
    ),
    { initialValue: null },
  );

  constructor() {
    effect(() => this.store.select(this.id() ?? null));
  }

  @HostListener('document:keydown', ['$event'])
  onKey(e: KeyboardEvent): void {
    const typing = (e.target as HTMLElement)?.closest('input, textarea, select');
    if (e.key === '/' && !typing) {
      e.preventDefault();
      this.searchBox()?.nativeElement.focus();
    }
  }

  entries(obj: Record<string, unknown>): [string, unknown][] {
    return Object.entries(obj);
  }

  open(id: string): void {
    this.router.navigate(['/terminal/security', id]);
  }

  // --- Chart options -----------------------------------------------------------------
  protected readonly historyPoints = computed(() => {
    const h = this.history();
    if (h?.state !== 'ok' || !h.data.points.length) return [];
    const pts = h.data.points;
    const r = this.range();
    if (r === 'All') return pts;
    const last = pts[pts.length - 1].as_of;
    const from = shiftDate(last, { months: r === '3M' ? -3 : r === '6M' ? -6 : -12 });
    return pts.filter((p) => p.as_of >= from);
  });

  protected readonly historyOption = computed<ChartOption>(() => {
    const pts = this.historyPoints();
    const isYield = this.metric() === 'yield';
    return {
      grid: { left: 52, right: 16, top: 16, bottom: 56 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      xAxis: { type: 'time' },
      yAxis: {
        type: 'value',
        scale: true,
        name: isYield ? 'YTM %' : 'Clean price',
        axisLabel: { formatter: (v: number) => v.toFixed(isYield ? 2 : 1) },
      },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 8 }],
      series: [
        {
          type: 'line',
          name: isYield ? 'Mid YTM (%)' : 'Mid clean price',
          showSymbol: false,
          data: pts.map((p) => [p.as_of, isYield ? p.mid_yield_pct : p.mid_price]),
        },
      ],
    };
  });

  protected readonly curveOption = computed<ChartOption>(() => {
    const c = this.curve();
    const a = this.analytics();
    const obs = c?.state === 'ok' ? c.data.observations[0] : null;
    const pts = obs?.points ?? [];
    const series: unknown[] = [
      {
        type: 'line',
        name: `UST par ${obs?.observed_date ?? ''}`,
        data: pts.map((p) => [p.tenor_months / 12, p.yield_pct]),
        symbolSize: 5,
      },
    ];
    if (a?.state === 'ok' && a.data.cash_flows.length) {
      const years = a.data.cash_flows[a.data.cash_flows.length - 1].time_years;
      series.push({
        type: 'scatter',
        name: `${a.data.security_id} YTM`,
        symbol: 'diamond',
        symbolSize: 12,
        data: [[years, a.data.pricing.ytm_pct]],
      });
    }
    return {
      grid: { left: 44, right: 12, top: 48, bottom: 36 },
      legend: { top: 0, left: 0 },
      tooltip: { trigger: 'item' },
      xAxis: { type: 'value', name: 'Years', min: 0, max: 30, nameLocation: 'middle', nameGap: 24 },
      yAxis: { type: 'value', scale: true, name: 'Yield %', nameGap: 8 },
      series,
    };
  });
}
