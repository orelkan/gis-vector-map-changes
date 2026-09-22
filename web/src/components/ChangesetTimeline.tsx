import { alpha, Box, ButtonBase, Tooltip, Typography, useTheme } from "@mui/material";
import type { Changeset } from "../api/types";

interface Props {
  changesets: Changeset[];
  selectedId: number | null;
  onChange: (id: number) => void;
}

const isoDate = (iso: string) => iso.slice(0, 10);
const shortLabel = (iso: string) => iso.slice(0, 7); // "2026-06", or "2026" would drop the month needed to tell 2026-06 from 2026-07 apart.

const ROW_HEIGHT = 26;
const ROW_GAP = 6;
const TRACK_PADDING = 10;

/** Every interval is one of the changesets Airflow has already computed --
 *  not an arbitrary date range -- so this is a timeline in *presentation*
 *  only: ticks mark the handful of snapshot dates that exist, and each
 *  computed changeset draws as a bracket between its two dates. There is no
 *  affordance to drag an endpoint to an uncomputed date, which would imply
 *  on-demand interval computation (deliberately out of scope --
 *  docs/architecture.md §8). Rows are ordered longest-span-first so nested
 *  intervals (the 5-year span containing the five 1-year steps, which
 *  contain the trailing 1-month step) read top-to-bottom as zoom levels. */
export function ChangesetTimeline({ changesets, selectedId, onChange }: Props) {
  const theme = useTheme();
  if (changesets.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        No computed intervals yet.
      </Typography>
    );
  }

  const dates = Array.from(
    new Set(changesets.flatMap((cs) => [isoDate(cs.time_a), isoDate(cs.time_b)])),
  ).sort();
  const xPercent = (iso: string) =>
    dates.length > 1 ? (dates.indexOf(iso) / (dates.length - 1)) * 100 : 50;

  const spanMs = (cs: Changeset) => new Date(cs.time_b).getTime() - new Date(cs.time_a).getTime();
  const rows = Array.from(new Set(changesets.map((cs) => cs.span_label)))
    .map((label) => ({
      label,
      items: changesets.filter((cs) => cs.span_label === label),
    }))
    .sort((a, b) => spanMs(b.items[0]) - spanMs(a.items[0]));

  const trackHeight = rows.length * ROW_HEIGHT + (rows.length - 1) * ROW_GAP;

  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        Interval
      </Typography>
      <Box sx={{ position: "relative", height: trackHeight, mx: `${TRACK_PADDING}px`, mt: 2 }}>
        {dates.map((d) => (
          <Box
            key={d}
            sx={{
              position: "absolute",
              top: 0,
              bottom: 0,
              left: `${xPercent(d)}%`,
              width: "1px",
              bgcolor: "divider",
            }}
          />
        ))}
        {rows.map((row, rowIndex) =>
          row.items.map((cs) => {
            const left = xPercent(isoDate(cs.time_a));
            const right = xPercent(isoDate(cs.time_b));
            const selected = cs.id === selectedId;
            return (
              <Tooltip
                key={cs.id}
                title={`${cs.span_label}: ${isoDate(cs.time_a)} → ${isoDate(cs.time_b)} · ${cs.changed_count.toLocaleString()} changes`}
              >
                <ButtonBase
                  onClick={() => onChange(cs.id)}
                  aria-pressed={selected}
                  sx={{
                    position: "absolute",
                    top: rowIndex * (ROW_HEIGHT + ROW_GAP),
                    left: `${left}%`,
                    width: `${Math.max(right - left, 2)}%`,
                    height: ROW_HEIGHT,
                    borderRadius: 999,
                    justifyContent: "center",
                    px: 0.5,
                    minWidth: 0,
                    bgcolor: selected
                      ? "primary.main"
                      : alpha(theme.palette.primary.main, 0.18),
                    color: selected ? "primary.contrastText" : "text.primary",
                    boxShadow: selected ? 2 : 0,
                    transition: "background-color 120ms, box-shadow 120ms",
                    "&:hover": {
                      bgcolor: selected ? "primary.dark" : alpha(theme.palette.primary.main, 0.32),
                    },
                  }}
                >
                  <Typography
                    variant="caption"
                    noWrap
                    sx={{
                      fontWeight: selected ? 700 : 500,
                      fontSize: "0.68rem",
                      pointerEvents: "none",
                    }}
                  >
                    {cs.span_label}
                  </Typography>
                </ButtonBase>
              </Tooltip>
            );
          }),
        )}
      </Box>
      <Box sx={{ position: "relative", height: 16, mx: `${TRACK_PADDING}px` }}>
        {dates.map((d) => (
          <Typography
            key={d}
            variant="caption"
            color="text.secondary"
            sx={{
              position: "absolute",
              left: `${xPercent(d)}%`,
              transform: "translateX(-50%)",
              whiteSpace: "nowrap",
              fontSize: "0.65rem",
            }}
          >
            {shortLabel(d)}
          </Typography>
        ))}
      </Box>
    </Box>
  );
}
