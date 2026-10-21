/** Initial investigations use a defensible loaded grain; explicit saved choices remain authoritative. */
export function initialResultGrain(
  state: string,
  office: string,
  explicit?: string | null,
): string {
  if (explicit) return explicit;
  return state === "AK" || office !== "PRESIDENT" ? "state" : "county";
}
