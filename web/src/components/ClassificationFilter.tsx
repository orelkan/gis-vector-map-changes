import { Box, Checkbox, Chip, FormControlLabel, Stack, Typography } from "@mui/material";
import { CLASSIFICATIONS, type Changeset, type Classification } from "../api/types";
import { CLASSIFICATION_COLORS, CLASSIFICATION_LABELS } from "../theme";

interface Props {
  changeset: Changeset | null;
  visible: Classification[];
  onToggle: (classification: Classification) => void;
}

const COUNT_KEYS: Record<Classification, keyof Changeset> = {
  added: "added_count",
  removed: "removed_count",
  modified_geometry: "modified_geometry_count",
  modified_attributes: "modified_attributes_count",
  modified_geometry_and_attributes: "modified_geometry_and_attributes_count",
  ambiguous: "ambiguous_count",
};

/** Legend and visibility filter in one control -- the colour swatch that
 *  explains the map is the same thing you click to filter it. */
export function ClassificationFilter({ changeset, visible, onToggle }: Props) {
  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        Change types
      </Typography>
      <Stack spacing={0}>
        {CLASSIFICATIONS.map((classification) => {
          const count = changeset
            ? (changeset[COUNT_KEYS[classification]] as number)
            : null;
          return (
            <FormControlLabel
              key={classification}
              control={
                <Checkbox
                  size="small"
                  checked={visible.includes(classification)}
                  onChange={() => onToggle(classification)}
                  slotProps={{
                    input: { "aria-label": CLASSIFICATION_LABELS[classification] },
                  }}
                  sx={{
                    color: CLASSIFICATION_COLORS[classification],
                    "&.Mui-checked": { color: CLASSIFICATION_COLORS[classification] },
                  }}
                />
              }
              label={
                <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                  <Typography variant="body2">
                    {CLASSIFICATION_LABELS[classification]}
                  </Typography>
                  {count !== null && (
                    <Chip
                      label={count.toLocaleString()}
                      size="small"
                      variant="outlined"
                      sx={{ height: 20, fontSize: "0.7rem" }}
                    />
                  )}
                </Stack>
              }
            />
          );
        })}
      </Stack>
      {changeset && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
          {changeset.unchanged_count.toLocaleString()} buildings unchanged in this interval
          (derived, not drawn).
        </Typography>
      )}
    </Box>
  );
}
