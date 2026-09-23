import { Box, Chip, Divider, Stack, Typography } from "@mui/material";
import type { FeatureHistory } from "../api/types";
import { isoDate } from "../format";
import { CLASSIFICATION_COLORS, CLASSIFICATION_LABELS } from "../theme";

interface Props {
  history: FeatureHistory;
}

/** One building across every snapshot held.
 *
 * Before/after is always relative to a single interval; this shows the whole
 * trajectory, so a geometry jump can be located in time rather than only
 * seen through whichever comparison happens to be selected.
 */
export function FeatureTimeline({ history }: Props) {
  const entries = history.history;

  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        History across all snapshots
      </Typography>
      <Stack spacing={0.5}>
        {entries.map((entry, index) => {
          const previous = index > 0 ? entries[index - 1] : null;
          // Area is a cheap, honest proxy for "the footprint changed here";
          // the authoritative classification comes from the changeset below.
          const areaDelta = previous ? entry.area_m2 - previous.area_m2 : 0;
          const changedHere = previous !== null && Math.abs(areaDelta) > 0.5;

          const intervalChanges = history.changes.filter(
            (c) => previous && isoDate(c.time_a) === isoDate(previous.requested_time)
              && isoDate(c.time_b) === isoDate(entry.requested_time),
          );

          return (
            <Box key={entry.snapshot_id}>
              {index > 0 && <Divider sx={{ my: 0.5 }} />}
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
                <Typography variant="body2" sx={{ fontWeight: 600, minWidth: 86 }}>
                  {isoDate(entry.requested_time)}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {entry.area_m2.toFixed(0)} m²
                </Typography>
                {changedHere && (
                  <Typography
                    variant="caption"
                    sx={{ color: areaDelta > 0 ? "success.main" : "warning.main" }}
                  >
                    {areaDelta > 0 ? "+" : ""}
                    {areaDelta.toFixed(0)} m²
                  </Typography>
                )}
                {entry.building && (
                  <Chip label={entry.building} size="small" variant="outlined"
                        sx={{ height: 18, fontSize: "0.65rem" }} />
                )}
              </Stack>
              {intervalChanges.map((c) => (
                <Chip
                  key={c.change_feature_id}
                  label={CLASSIFICATION_LABELS[c.classification]}
                  size="small"
                  sx={{
                    height: 18,
                    fontSize: "0.65rem",
                    mt: 0.25,
                    ml: 11,
                    bgcolor: CLASSIFICATION_COLORS[c.classification],
                    color: "#fff",
                  }}
                />
              ))}
            </Box>
          );
        })}
      </Stack>
      {entries.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          Not present in any snapshot.
        </Typography>
      )}
    </Box>
  );
}
