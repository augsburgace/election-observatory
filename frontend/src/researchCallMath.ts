/** Signed R−D estimates retain direction; absent evidence never becomes an even race. */
export function marginCallLabel(value: number | null | undefined, digits = 1) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "Unavailable";
  if (value === 0) return "Even";
  return `${value > 0 ? "R" : "D"} +${Math.abs(value).toFixed(digits)}`;
}
