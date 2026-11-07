import {
  DEFAULT_SHOCK,
  ResearchStore,
  decodeShock,
  encodeShock,
  shockAt,
  shockNodes,
} from './research-store';

describe('shock helpers', () => {
  it('interpolates like the backend: linear between nodes, flat outside', () => {
    const nodes = [
      { tenorYears: 2, bp: -25 },
      { tenorYears: 10, bp: 50 },
    ];
    expect(shockAt(nodes, 1)).toBe(-25);
    expect(shockAt(nodes, 6)).toBeCloseTo(12.5);
    expect(shockAt(nodes, 30)).toBe(50);
  });

  it('round-trips every shock kind through the URL encoding', () => {
    const cases = [
      { ...DEFAULT_SHOCK, parallelBp: 75 },
      { ...DEFAULT_SHOCK, kind: 'twist' as const, shortBp: -25, longBp: 50 },
      {
        ...DEFAULT_SHOCK,
        kind: 'key' as const,
        keyBp: [0, 10, 25, 25, 10, 0],
        spreadMode: 'shock' as const,
        spreadShockBp: 40,
      },
    ];
    for (const s of cases) expect(decodeShock(encodeShock(s))).toEqual(s);
  });

  it('clamps out-of-range and rejects garbage input from URLs', () => {
    expect(decodeShock('p900').parallelBp).toBe(300);
    expect(decodeShock('zzz')).toEqual(DEFAULT_SHOCK);
    expect(decodeShock('pNaN').parallelBp).toBe(0);
  });

  it('builds nodes per kind', () => {
    expect(shockNodes({ ...DEFAULT_SHOCK, parallelBp: 50 })).toEqual([{ tenorYears: 1, bp: 50 }]);
    expect(shockNodes({ ...DEFAULT_SHOCK, kind: 'key' })).toHaveLength(6);
  });
});

describe('ResearchStore', () => {
  it('tracks modifications and resets', () => {
    const store = new ResearchStore();
    expect(store.isShockModified()).toBe(false);
    store.updateShock({ parallelBp: 25 });
    expect(store.isShockModified()).toBe(true);
    store.resetShock();
    expect(store.isShockModified()).toBe(false);
  });
});
