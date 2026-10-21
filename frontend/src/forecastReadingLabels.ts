const calendarFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});
const easternFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZone: "America/New_York",
  timeZoneName: "short",
});
function calendarDate(value?: string) {
  const date = value?.match(/^\d{4}-\d{2}-\d{2}/)?.[0];
  if (!date) return null;
  // A fieldwork date is a calendar label, not a midnight instant to shift by zone.
  const parsed = new Date(`${date}T12:00:00Z`);
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === date ? parsed : null;
}
export function fieldworkLabel(start?: string, end?: string) {
  const first = calendarDate(start), last = calendarDate(end);
  if (first && last && first.valueOf() !== last.valueOf())
    return `${calendarFormatter.format(first)} – ${calendarFormatter.format(last)}`;
  return first || last ? calendarFormatter.format((first || last)!) : "date unavailable";
}
export function populationLabel(population?: string) {
  const label = population?.trim();
  return ({ LV: "Likely voters", RV: "Registered voters", A: "Adults" } as Record<string, string>)[label?.toUpperCase() || ""] || label || "Population not disclosed";
}
export function easternTimeLabel(value?: string) {
  // Require an explicit offset; never guess the source's timezone for naive text.
  if (!value || !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)) return "time unavailable";
  const parsed = new Date(value);
  return Number.isFinite(parsed.valueOf()) ? easternFormatter.format(parsed) : "time unavailable";
}
