import { FormControl, InputLabel, MenuItem, Select, Typography } from "@mui/material";
import type { Changeset } from "../api/types";

interface Props {
  changesets: Changeset[];
  selectedId: number | null;
  onChange: (id: number) => void;
}

const isoDate = (iso: string) => iso.slice(0, 10);

/** Selects which computed interval to view.
 *
 * Intervals are the changesets Airflow has already computed, not arbitrary
 * date ranges -- that keeps algorithm_version provenance intact and matches
 * the pipeline's versioned-result model.
 */
export function ChangesetPicker({ changesets, selectedId, onChange }: Props) {
  return (
    <FormControl fullWidth size="small">
      <InputLabel id="changeset-label">Interval</InputLabel>
      <Select
        labelId="changeset-label"
        label="Interval"
        value={selectedId === null ? "" : String(selectedId)}
        onChange={(event) => onChange(Number(event.target.value))}
      >
        {changesets.map((cs) => (
          <MenuItem key={cs.id} value={String(cs.id)}>
            <Typography component="span" sx={{ fontWeight: 600, mr: 1 }}>
              {cs.span_label}
            </Typography>
            <Typography component="span" variant="body2" color="text.secondary">
              {isoDate(cs.time_a)} → {isoDate(cs.time_b)} · {cs.changed_count.toLocaleString()} changes
            </Typography>
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
