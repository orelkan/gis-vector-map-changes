/** Shared display formatting.
 *
 * These were defined independently in three components; keeping one copy
 * means a change to how dates or metrics read applies everywhere at once.
 */

/** "2026-07-01T00:00:00Z" -> "2026-07-01". */
export const isoDate = (iso: string): string => iso.slice(0, 10);

/** Axis label for a snapshot date: "2026-06". Deliberately keeps the month
 *  -- "2026" alone could not tell 2026-06 and 2026-07 apart. */
export const shortLabel = (iso: string): string => iso.slice(0, 7);

/** A metric, or an em dash when it is absent (ambiguous groups leave the
 *  promoted metrics null rather than picking one candidate's). */
export const fmt = (v: number | null, digits = 4): string =>
  v === null ? "—" : v.toFixed(digits);
