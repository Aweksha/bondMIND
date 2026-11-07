import { Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { debounceTime, distinctUntilChanged, of, switchMap, tap } from 'rxjs';

import { ScenarioRequest } from '../../core/api.models';
import { ApiService } from '../../core/api.service';
import { SERIES_DASH, download, fmt, shiftDate, signed, tenorLabel } from '../../core/format';
import { load } from '../../core/load';
import {
  KEY_TENORS,
  ResearchStore,
  SHOCK_LIMIT_BP,
  ShockKind,
  clampBp,
  decodeShock,
  encodeShock,
  shockAt,
} from '../../core/research-store';
import { Chart, ChartOption } from '../../shared/chart';

const MAX_OVERLAYS = 3;
const key = (v: unknown) => JSON.stringify(v);

@Component({
  selector: 'bm-curve-lab',
  imports: [Chart],
  templateUrl: './curve-lab.html',
})
export class CurveLab {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  protected readonly store = inject(ResearchStore);
  protected readonly fmt = fmt;
  protected readonly signed = signed;
  protected readonly tenorLabel = tenorLabel;
  protected readonly keyTenors = KEY_TENORS;
  protected readonly limit = SHOCK_LIMIT_BP;
  protected readonly presets = [-100, -50, -25, 25, 50, 100];

  // Deep-link query params: ?security=BM-C-0001&dates=2026-11-06,2025-11-06&shock=p50
  readonly security = input<string | undefined>();
  readonly dates = input<string | undefined>();
  readonly shock = input<string | undefined>();

  protected readonly dateInfo = toSignal(this.api.curveDates(this.store.curveId()).pipe(load()), {
    initialValue: { state: 'loading' } as const,
  });
  protected readonly securities = toSignal(
    this.api.securities({ page_size: 200, sort: 'maturity_date' }).pipe(load()),
    { initialValue: { state: 'loading' } as const },
  );
  protected readonly hiddenTenors = signal<Set<number>>(new Set());
  protected readonly inputWarning = signal<string | null>(null);

  protected readonly minDate = computed(() => {
    const d = this.dateInfo();
    return d.state === 'ok' ? d.data.first_date : null;
  });
  protected readonly maxDate = computed(() => {
    const d = this.dateInfo();
    return d.state === 'ok' ? d.data.last_date : null;
  });

  private initialised = false;

  constructor() {
    // 1) Apply deep-link params once the available date range is known.
    effect(() => {
      const last = this.maxDate();
      if (!last || this.initialised) return;
      this.initialised = true;
      untracked(() => {
        const fromUrl = (this.dates() ?? '')
          .split(',')
          .filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d));
        const base = fromUrl[0] ?? this.store.baseDate() ?? last;
        this.store.baseDate.set(base);
        const overlays = fromUrl.length
          ? fromUrl.slice(1, 1 + MAX_OVERLAYS)
          : this.store.overlayDates().length
            ? this.store.overlayDates()
            : [shiftDate(base, { years: -1 })];
        this.store.overlayDates.set(overlays);
        if (this.shock()) this.store.shock.set(decodeShock(this.shock()));
        const sec = this.security() ?? this.store.selectedSecurityId() ?? 'BM-T-0005';
        this.store.select(sec);
      });
    });
    // 2) Keep the URL in sync so the current view can be shared (no private data in it).
    effect(() => {
      const base = this.store.baseDate();
      if (!base) return;
      const queryParams = {
        security: this.store.selectedSecurityId(),
        dates: [base, ...this.store.overlayDates()].join(','),
        shock: this.store.isShockModified() ? encodeShock(this.store.shock()) : null,
      };
      untracked(() => this.router.navigate([], { queryParams, replaceUrl: true }));
    });
  }

  // --- Historical observations (overlays) ----------------------------------------------
  protected readonly allDates = computed(() => {
    const base = this.store.baseDate();
    return base ? [base, ...this.store.overlayDates()] : [];
  });
  protected readonly observations = toSignal(
    toObservable(this.allDates).pipe(
      debounceTime(150),
      distinctUntilChanged((a, b) => key(a) === key(b)),
      switchMap((ds) =>
        ds.length ? this.api.observations(this.store.curveId(), ds).pipe(load()) : of(null),
      ),
    ),
    { initialValue: null },
  );

  // --- Scenario: optimistic preview + debounced authoritative repricing ----------------
  protected readonly request = computed<ScenarioRequest | null>(() => {
    const base = this.store.baseDate();
    const sec = this.store.selectedSecurityId();
    if (!base || !sec) return null;
    const s = this.store.shock();
    return {
      curveId: this.store.curveId(),
      baseDate: base,
      securityIds: [sec],
      shockNodes: this.store.shockNodes(),
      spreadMode: s.spreadMode,
      spreadShockBp: s.spreadMode === 'shock' ? s.spreadShockBp : 0,
    };
  });
  private readonly evaluatedKey = signal<string | null>(null);
  protected readonly scenario = toSignal(
    toObservable(this.request).pipe(
      debounceTime(300),
      distinctUntilChanged((a, b) => key(a) === key(b)),
      switchMap((req) =>
        req
          ? this.api.evaluate(req).pipe(
              tap({
                next: () => this.evaluatedKey.set(key(req)),
                error: () => this.evaluatedKey.set(key(req)),
              }),
              load(),
            )
          : of(null),
      ),
    ),
    { initialValue: null },
  );
  protected readonly updating = computed(() => key(this.request()) !== this.evaluatedKey());
  protected readonly result = computed(() => {
    const s = this.scenario();
    return s?.state === 'ok' ? s.data.results[0] : null;
  });

  // --- Table rows shared by both charts, the CSV export and the accessible table -------
  protected readonly baseObs = computed(() => {
    const o = this.observations();
    return o?.state === 'ok' ? o.data.observations : [];
  });
  protected readonly tenors = computed(() => {
    const set = new Set<number>();
    for (const o of this.baseObs()) for (const p of o.points) set.add(p.tenor_months);
    return [...set].sort((a, b) => a - b);
  });
  protected readonly visibleTenors = computed(() =>
    this.tenors().filter((t) => !this.hiddenTenors().has(t)),
  );
  protected readonly rows = computed(() => {
    const obs = this.baseObs();
    const nodes = this.store.shockNodes();
    const server = this.scenario();
    const serverPts =
      server?.state === 'ok' && !this.updating()
        ? new Map(server.data.curve.points.map((p) => [p.tenor_months, p]))
        : null;
    return this.visibleTenors().map((t) => {
      const values = obs.map((o) => o.points.find((p) => p.tenor_months === t)?.yield_pct ?? null);
      const base = values[0] ?? null;
      const sp = serverPts?.get(t);
      const shockBp = sp ? sp.shock_bp : shockAt(nodes, t / 12);
      return {
        tenor: t,
        values,
        shockBp,
        shocked: sp ? sp.shocked_par_pct : base === null ? null : base + shockBp / 100,
        zeroBase: sp?.base_zero_pct ?? null,
        histDiffBp:
          base !== null && values[1] !== null && values[1] !== undefined
            ? (base - values[1]) * 100
            : null,
      };
    });
  });
  protected readonly isPreview = computed(() => this.updating() || this.scenario()?.state !== 'ok');

  protected readonly curveOption = computed<ChartOption>(() => {
    const obs = this.baseObs();
    const rows = this.rows();
    const labels = rows.map((r) => tenorLabel(r.tenor));
    const series: unknown[] = obs.map((o, i) => ({
      type: 'line',
      name: o.observed_date
        ? `${o.observed_date}${o.status === 'prior_observation' ? ' (prior obs.)' : ''}`
        : `${o.requested_date} (unavailable)`,
      data: rows.map((r) => r.values[i]),
      connectNulls: false,
      symbol: ['circle', 'rect', 'triangle', 'diamond'][i % 4],
      symbolSize: 6,
      lineStyle: { type: SERIES_DASH[i % SERIES_DASH.length], width: i === 0 ? 2.5 : 1.5 },
    }));
    if (this.store.isShockModified()) {
      series.push({
        type: 'line',
        name: this.isPreview() ? 'Base + shock (preview)' : 'Base + shock',
        data: rows.map((r) => r.shocked),
        connectNulls: false,
        symbol: 'emptyCircle',
        symbolSize: 6,
        lineStyle: { type: [6, 3], width: 2.5 },
        color: getComputedStyle(document.documentElement).getPropertyValue('--warn').trim(),
      });
    }
    return {
      grid: { left: 48, right: 16, top: 40, bottom: 32 },
      legend: { top: 0 },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (v: number | null) => (v == null ? 'n/a' : `${v.toFixed(3)}%`),
      },
      xAxis: { type: 'category', data: labels, name: 'Tenor', nameLocation: 'middle', nameGap: 24 },
      yAxis: { type: 'value', scale: true, name: 'Par yield %' },
      series,
    };
  });

  protected readonly changeOption = computed<ChartOption>(() => {
    const rows = this.rows();
    const obs = this.baseObs();
    const series: unknown[] = [
      {
        type: 'bar',
        name: this.isPreview() ? 'Scenario shock (preview)' : 'Scenario shock',
        data: rows.map((r) => Number(r.shockBp.toFixed(2))),
        barMaxWidth: 18,
      },
    ];
    if (obs.length > 1 && obs[1].observed_date) {
      series.push({
        type: 'line',
        name: `Change since ${obs[1].observed_date}`,
        data: rows.map((r) => (r.histDiffBp === null ? null : Number(r.histDiffBp.toFixed(1)))),
        connectNulls: false,
        lineStyle: { type: 'dashed' },
        symbol: 'rect',
      });
    }
    return {
      grid: { left: 48, right: 16, top: 40, bottom: 32 },
      legend: { top: 0 },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (v: number | null) => (v == null ? 'n/a' : `${v} bp`),
      },
      xAxis: { type: 'category', data: rows.map((r) => tenorLabel(r.tenor)) },
      yAxis: { type: 'value', name: 'bp' },
      series,
    };
  });

  // --- Controls ------------------------------------------------------------------------
  setBase(value: string): void {
    if (value) this.store.baseDate.set(value);
  }

  setOverlay(i: number, value: string): void {
    if (!value) return;
    this.store.overlayDates.update((ds) => ds.map((d, j) => (j === i ? value : d)));
  }

  addOverlay(offset: { years?: number; months?: number }): void {
    const base = this.store.baseDate();
    if (!base || this.store.overlayDates().length >= MAX_OVERLAYS) return;
    this.store.overlayDates.update((ds) => [...ds, shiftDate(base, offset)]);
  }

  removeOverlay(i: number): void {
    this.store.overlayDates.update((ds) => ds.filter((_, j) => j !== i));
  }

  toggleTenor(t: number): void {
    this.hiddenTenors.update((set) => {
      const next = new Set(set);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  }

  setKind(kind: ShockKind): void {
    this.store.updateShock({ kind });
  }

  bp(raw: string | number, field: 'parallelBp' | 'shortBp' | 'longBp' | 'spreadShockBp'): void {
    const v = Number(raw);
    const limit = field === 'spreadShockBp' ? 500 : SHOCK_LIMIT_BP;
    if (!Number.isFinite(v)) return;
    this.inputWarning.set(
      Math.abs(v) > limit ? `Shocks are limited to ±${limit} bp; value clamped.` : null,
    );
    this.store.updateShock({ [field]: clampBp(v, limit) });
  }

  keyBp(i: number, raw: string): void {
    const v = Number(raw);
    if (!Number.isFinite(v)) return;
    this.inputWarning.set(
      Math.abs(v) > SHOCK_LIMIT_BP
        ? `Shocks are limited to ±${SHOCK_LIMIT_BP} bp; value clamped.`
        : null,
    );
    this.store.setKeyBp(i, v);
  }

  reset(): void {
    this.inputWarning.set(null);
    this.store.resetShock();
  }

  entries(obj: Record<string, unknown> | undefined): [string, unknown][] {
    return obj ? Object.entries(obj) : [];
  }

  // --- Exports -------------------------------------------------------------------------
  exportCsv(): void {
    const obs = this.baseObs();
    const s = this.scenario();
    const meta = [
      `# bondMIND Curve Lab export; curve ${this.store.curveId()}; units: yields %, shocks bp`,
      `# source: ${s?.state === 'ok' ? s.data.vintage.source : 'U.S. Treasury'}; scenario ${encodeShock(this.store.shock())}`,
      `# ${this.isPreview() ? 'shocked curve is a client preview' : 'shocked curve from server ' + (s?.state === 'ok' ? s.data.engine_version : '')}`,
    ];
    const header = [
      'tenor',
      ...obs.map((o) => `yield_${o.observed_date ?? o.requested_date}`),
      'shock_bp',
      'shocked_yield',
    ];
    const lines = this.rows().map((r) =>
      [
        tenorLabel(r.tenor),
        ...r.values.map((v) => v ?? ''),
        r.shockBp.toFixed(4),
        r.shocked?.toFixed(6) ?? '',
      ].join(','),
    );
    download(
      `bondmind-curve-lab-${this.store.baseDate()}.csv`,
      [...meta, header.join(','), ...lines].join('\n'),
      'text/csv',
    );
  }

  exportJson(): void {
    const s = this.scenario();
    if (s?.state !== 'ok') return;
    download(
      `bondmind-scenario-${this.store.baseDate()}.json`,
      JSON.stringify(s.data, null, 2),
      'application/json',
    );
  }

  protected readonly securityOptions = computed(() => {
    const s = this.securities();
    return s.state === 'ok' ? s.data.items : [];
  });

  protected readonly selectedIsListed = computed(() =>
    this.securityOptions().some((s) => s.id === this.store.selectedSecurityId()),
  );
}
