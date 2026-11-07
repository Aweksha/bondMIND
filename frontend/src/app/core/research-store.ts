import { Injectable, computed, signal } from '@angular/core';

import { ShockNode, SpreadMode } from './api.models';

export type ShockKind = 'parallel' | 'twist' | 'key';

export const KEY_TENORS = [1, 2, 5, 10, 20, 30] as const;

export interface ShockState {
  kind: ShockKind;
  parallelBp: number;
  shortBp: number; // twist node at 2Y
  longBp: number; // twist node at 10Y
  keyBp: number[]; // one per KEY_TENORS entry
  spreadMode: SpreadMode;
  spreadShockBp: number;
}

export const DEFAULT_SHOCK: ShockState = {
  kind: 'parallel',
  parallelBp: 0,
  shortBp: 0,
  longBp: 0,
  keyBp: KEY_TENORS.map(() => 0),
  spreadMode: 'hold_constant',
  spreadShockBp: 0,
};

export const SHOCK_LIMIT_BP = 300;

export function clampBp(v: number, limit = SHOCK_LIMIT_BP): number {
  if (!Number.isFinite(v)) return 0;
  return Math.max(-limit, Math.min(limit, v));
}

export function shockNodes(s: ShockState): ShockNode[] {
  switch (s.kind) {
    case 'parallel':
      return [{ tenorYears: 1, bp: s.parallelBp }];
    case 'twist':
      return [
        { tenorYears: 2, bp: s.shortBp },
        { tenorYears: 10, bp: s.longBp },
      ];
    case 'key':
      return KEY_TENORS.map((t, i) => ({ tenorYears: t, bp: s.keyBp[i] ?? 0 }));
  }
}

/** Same rule as the backend (linear between nodes, flat outside). Used only for preview. */
export function shockAt(nodes: ShockNode[], tenorYears: number): number {
  const pts = [...nodes].sort((a, b) => a.tenorYears - b.tenorYears);
  if (!pts.length) return 0;
  if (tenorYears <= pts[0].tenorYears) return pts[0].bp;
  const last = pts[pts.length - 1];
  if (tenorYears >= last.tenorYears) return last.bp;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1];
    const b = pts[i];
    if (tenorYears <= b.tenorYears) {
      return a.bp + ((tenorYears - a.tenorYears) / (b.tenorYears - a.tenorYears)) * (b.bp - a.bp);
    }
  }
  return last.bp;
}

/** Compact URL encoding so a scenario can be deep-linked: p50 | t-25_50 | k0_10_25_25_10_0 */
export function encodeShock(s: ShockState): string {
  const base =
    s.kind === 'parallel'
      ? `p${s.parallelBp}`
      : s.kind === 'twist'
        ? `t${s.shortBp}_${s.longBp}`
        : `k${s.keyBp.join('_')}`;
  return s.spreadMode === 'shock' ? `${base}~s${s.spreadShockBp}` : base;
}

export function decodeShock(code: string | null | undefined): ShockState {
  if (!code) return DEFAULT_SHOCK;
  const [curve, spread] = code.split('~');
  const nums = (txt: string) => txt.split('_').map((n) => clampBp(Number(n)));
  const s: ShockState = { ...DEFAULT_SHOCK, keyBp: [...DEFAULT_SHOCK.keyBp] };
  const body = curve.slice(1);
  if (curve[0] === 'p') {
    s.parallelBp = clampBp(Number(body));
  } else if (curve[0] === 't') {
    const [a, b] = nums(body);
    Object.assign(s, { kind: 'twist', shortBp: a ?? 0, longBp: b ?? 0 });
  } else if (curve[0] === 'k') {
    const values = nums(body);
    s.kind = 'key';
    s.keyBp = KEY_TENORS.map((_, i) => values[i] ?? 0);
  } else {
    return DEFAULT_SHOCK;
  }
  if (spread?.startsWith('s')) {
    s.spreadMode = 'shock';
    s.spreadShockBp = clampBp(Number(spread.slice(1)), 500);
  }
  return s;
}

/**
 * Shared research context (Requirements 2.0, sec. 8). Ephemeral UI state lives here; the server
 * stays authoritative for data and valuation. Panels read signals and never talk to each other.
 */
@Injectable({ providedIn: 'root' })
export class ResearchStore {
  readonly curveId = signal('USD-UST-PAR');
  readonly selectedSecurityId = signal<string | null>(null);
  /** Terminal search text; kept here so it survives navigating to detail and back. */
  readonly terminalQuery = signal('');
  readonly baseDate = signal<string | null>(null);
  readonly overlayDates = signal<string[]>([]);
  readonly shock = signal<ShockState>(DEFAULT_SHOCK);

  readonly shockNodes = computed(() => shockNodes(this.shock()));
  readonly isShockModified = computed(
    () => encodeShock(this.shock()) !== encodeShock(DEFAULT_SHOCK),
  );

  select(id: string | null): void {
    if (id !== this.selectedSecurityId()) this.selectedSecurityId.set(id);
  }

  updateShock(patch: Partial<ShockState>): void {
    this.shock.update((s) => ({ ...s, ...patch }));
  }

  setKeyBp(index: number, bp: number): void {
    this.shock.update((s) => {
      const keyBp = [...s.keyBp];
      keyBp[index] = clampBp(bp);
      return { ...s, keyBp };
    });
  }

  resetShock(): void {
    this.shock.set(DEFAULT_SHOCK);
  }
}
