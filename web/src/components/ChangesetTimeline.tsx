import { useMemo, useState } from "react";
import { alpha, Box, ButtonBase, Typography, useTheme } from "@mui/material";
import type { Changeset } from "../api/types";

interface Props {
  changesets: Changeset[];
  selectedId: number | null;
  onChange: (id: number) => void;
}

const isoDate = (iso: string) => iso.slice(0, 10);
const shortLabel = (iso: string) => iso.slice(0, 7); // "2026-06", or "2026" would drop the month needed to tell 2026-06 from 2026-07 apart.

const ROW_HEIGHT = 28;
const ROW_GAP = 10;
const TRACK_PADDING = 10;

/** Every interval is one of the changesets Airflow has already computed --
 *  not an arbitrary date range -- so this is a timeline in *presentation*
 *  only: ticks mark the handful of snapshot dates that exist, and each
 *  computed changeset draws as a bracket between its two dates. There is no
 *  affordance to drag an endpoint to an uncomputed date, which would imply
 *  on-demand interval computation (deliberately out of scope --
 *  docs/architecture.md §8). Rows are ordered longest-span-first so nested
 *  intervals (the 5-year span containing the five 1-year steps, which
 *  contain the trailing 1-month step) read top-to-bottom as zoom levels.
 *
 *  Deliberately no hover Tooltip: a tooltip anchored to a full-width "5
 *  years" bracket pops directly over the row beneath it (MUI's default
 *  "bottom" placement), blanketing the very brackets a user is trying to
 *  click next. Interval details are shown in a persistent caption below the
 *  track instead, driven by hover *or* selection -- informative without
 *  ever sitting on top of anything clickable. */
export function ChangesetTimeline({ changesets, selectedId, onChange }: Props) {
  const theme = useTheme();
  const [hoveredId, setHoveredId] = useState<number | null>(null);

  const dates = useMemo(
    () =>
      Array.from(new Set(changesets.flatMap((cs) => [isoDate(cs.time_a), isoDate(cs.time_b)]))).sort(),
    [changesets],
  );
  const xPercent = (iso: string) =>
    dates.length > 1 ? (dates.indexOf(iso) / (dates.length - 1)) * 100 : 50;

  const spanMs = (cs: Changeset) => new Date(cs.time_b).getTime() - new Date(cs.time_a).getTime();
  const rows = useMemo(
    () =>
      Array.from(new Set(changesets.map((cs) => cs.span_label)))
        .map((label) => ({ label, items: changesets.filter((cs) => cs.span_label === label) }))
        .sort((a, b) => spanMs(b.items[0]) - spanMs(a.items[0])),
    [changesets],
  );

  if (changesets.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        No computed intervals yet.
      </Typography>
    );
  }

  const trackHeight = rows.length * ROW_HEIGHT + (rows.length - 1) * ROW_GAP;
  const described = changesets.find((cs) => cs.id === (hoveredId ?? selectedId)) ?? null;

  return (
    <Box>
      <Typography
        variant="overline"
        color="text.secondary"
        sx={{ letterSpacing: 1, fontWeight: 700 }}
      >
        Interval
      </Typography>
      <Box sx={{ position: "relative", height: trackHeight, mx: `${TRACK_PADDING}px`, mt: 1.5 }}>
        {/* Faint alternating lanes, so each row reads as its own track rather
            than a handful of pills floating in shared space. */}
        {rows.map((row, rowIndex) => (
          <Box
            key={row.label}
            sx={{
              position: "absolute",
              top: rowIndex * (ROW_HEIGHT + ROW_GAP) - ROW_GAP / 2,
              left: 0,
              right: 0,
              height: ROW_HEIGHT + ROW_GAP,
              borderRadius: 2,
              bgcolor: rowIndex % 2 === 0 ? alpha(theme.palette.text.primary, 0.03) : "transparent",
            }}
          />
        ))}
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
            const hovered = cs.id === hoveredId;
            return (
              <ButtonBase
                key={cs.id}
                onClick={() => onChange(cs.id)}
                onMouseEnter={() => setHoveredId(cs.id)}
                onMouseLeave={() => setHoveredId((id) => (id === cs.id ? null : id))}
                onFocus={() => setHoveredId(cs.id)}
                onBlur={() => setHoveredId((id) => (id === cs.id ? null : id))}
                aria-pressed={selected}
                aria-label={`${cs.span_label}: ${isoDate(cs.time_a)} to ${isoDate(cs.time_b)}, ${cs.changed_count.toLocaleString()} changes`}
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
                  backgroundImage: selected
                    ? `linear-gradient(135deg, ${theme.palette.primary.main}, ${theme.palette.primary.dark})`
                    : "none",
                  bgcolor: selected ? undefined : alpha(theme.palette.primary.main, hovered ? 0.32 : 0.16),
                  color: selected ? "primary.contrastText" : "text.primary",
                  boxShadow: selected ? `0 2px 8px ${alpha(theme.palette.primary.main, 0.5)}` : 0,
                  transform: hovered && !selected ? "scale(1.03)" : "scale(1)",
                  transition: "background-color 120ms, transform 120ms, box-shadow 120ms",
                }}
              >
                <Typography
                  variant="caption"
                  noWrap
                  sx={{
                    fontWeight: selected ? 700 : 500,
                    fontSize: "0.68rem",
                    letterSpacing: selected ? 0.2 : 0,
                    pointerEvents: "none",
                  }}
                >
                  {cs.span_label}
                </Typography>
              </ButtonBase>
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
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", mt: 0.5, minHeight: "1.2em" }}
      >
        {described
          ? `${described.span_label}: ${isoDate(described.time_a)} → ${isoDate(described.time_b)} · ${described.changed_count.toLocaleString()} changes`
          : " "}
      </Typography>
    </Box>
  );
}
