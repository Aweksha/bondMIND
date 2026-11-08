export function tenorLabel(months: number): string {
  return months < 12 ? `${months}M` : `${months / 12}Y`;
}

export function fmt(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined || !Number.isFinite(value)
    ? '—'
    : value.toFixed(digits);
}

export function signed(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${value > 0 ? '+' : value < 0 ? '−' : ''}${Math.abs(value).toFixed(digits)}`;
}

export function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function shiftDate(iso: string, { years = 0, months = 0 } = {}): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCFullYear(d.getUTCFullYear() + years, d.getUTCMonth() + months);
  return isoDate(d);
}

export function shiftDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return isoDate(d);
}

/** Safe export filename: letters, digits, dash, underscore, dot only. */
export function safeFilename(name: string): string {
  return name.replace(/[^A-Za-z0-9._-]+/g, '-').slice(0, 80);
}

export function download(filename: string, content: string, type: string): void {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = Object.assign(document.createElement('a'), {
    href: url,
    download: safeFilename(filename),
  });
  a.click();
  URL.revokeObjectURL(url);
}

export const SERIES_DASH = ['solid', 'dashed', 'dotted', 'dashed'] as const;
