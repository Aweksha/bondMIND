export function tenorLabel(months: number): string {
  return months < 12 ? `${months}M` : `${months / 12}Y`;
}

export function fmt(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined ? '—' : value.toFixed(digits);
}

export function signed(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return '—';
  return `${value > 0 ? '+' : value < 0 ? '−' : ''}${Math.abs(value).toFixed(digits)}`;
}
