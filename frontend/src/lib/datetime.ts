// Backend timestamps come from SQLite as naive UTC (no timezone suffix), e.g.
// "2026-06-22T02:56:00". The browser's `new Date()` would treat those as LOCAL
// time, shifting displayed times and inflating elapsed durations by the local
// UTC offset. Treat backend timestamps as UTC.
export function parseBackendDate(value: string): Date {
  if (value && !/[zZ]$|[+-]\d{2}:?\d{2}$/.test(value)) {
    return new Date(`${value}Z`);
  }
  return new Date(value);
}
