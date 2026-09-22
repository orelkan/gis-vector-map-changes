import {
  Alert, Box, Chip, CircularProgress, Divider, Stack, Table, TableBody,
  TableCell, TableRow, Typography,
} from "@mui/material";
import type { ChangeDetail, FeatureHistory } from "../api/types";
import { CLASSIFICATION_COLORS, CLASSIFICATION_LABELS } from "../theme";
import { FeatureTimeline } from "./FeatureTimeline";

interface Props {
  change: ChangeDetail | null;
  history: FeatureHistory | null;
  loading: boolean;
  error: string | null;
}

const isoDate = (iso: string) => iso.slice(0, 10);
const fmt = (v: number | null, digits = 4) => (v === null ? "—" : v.toFixed(digits));

/** Explains a geometry change compositionally, from the two IoU metrics.
 *
 * A low `iou` with a much higher centroid-aligned IoU means the footprint
 * largely kept its shape but moved -- the signature of a re-traced or
 * re-surveyed building rather than a rebuilt one. Stated as evidence, not
 * as a verdict, since the metrics genuinely do not separate the two cleanly.
 */
function geometryNarrative(change: ChangeDetail): string | null {
  const { iou, iou_centroid_aligned: aligned, centroid_shift_m: shift } = change;
  if (iou === null || aligned === null || shift === null) return null;
  const gain = aligned - iou;
  if (gain > 0.3 && shift > 1) {
    return `Shape largely preserved (aligned IoU ${aligned.toFixed(2)} vs ${iou.toFixed(2)}) ` +
      `but moved ${shift.toFixed(1)} m — consistent with a re-trace or re-survey rather ` +
      `than a rebuild.`;
  }
  if (aligned < 0.7) {
    return `Footprint genuinely reshaped: even after aligning centroids the overlap is ` +
      `only ${aligned.toFixed(2)}.`;
  }
  return null;
}

export function FeatureDetailPanel({ change, history, loading, error }: Props) {
  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
        <CircularProgress size={24} />
      </Box>
    );
  }
  if (error) return <Alert severity="error">{error}</Alert>;
  if (!change) {
    return (
      <Typography variant="body2" color="text.secondary">
        Click a highlighted building on the map to inspect what changed.
      </Typography>
    );
  }

  const narrative = geometryNarrative(change);
  const osmIds = Array.from(new Set([...change.osm_ids_a, ...change.osm_ids_b]));

  return (
    <Stack spacing={1.5}>
      <Box>
        <Chip
          label={CLASSIFICATION_LABELS[change.classification]}
          size="small"
          sx={{ bgcolor: CLASSIFICATION_COLORS[change.classification], color: "#fff", fontWeight: 600 }}
        />
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
          {isoDate(change.time_a)} → {isoDate(change.time_b)} · {change.classification_reason}
        </Typography>
      </Box>

      <Box>
        <Typography variant="subtitle2">OSM ID{osmIds.length > 1 ? "s" : ""}</Typography>
        {osmIds.map((id) => (
          <Typography key={id} variant="body2" sx={{ fontFamily: "monospace" }}>
            {id}
          </Typography>
        ))}
      </Box>

      {(change.geom_a || change.geom_b) && (
        <Typography variant="caption" color="text.secondary">
          {change.geom_a && change.geom_b
            ? "Dashed outline = before, solid yellow = after."
            : change.geom_b
              ? "Solid yellow outline = the new footprint (no prior geometry)."
              : "Dashed outline = the removed footprint (no later geometry)."}
        </Typography>
      )}

      {narrative && <Alert severity="info" sx={{ py: 0.5 }}>{narrative}</Alert>}

      {change.iou !== null && (
        <Box>
          <Typography variant="subtitle2" gutterBottom>Geometry metrics</Typography>
          <Table size="small">
            <TableBody>
              <TableRow>
                <TableCell sx={{ pl: 0 }}>IoU</TableCell>
                <TableCell align="right">{fmt(change.iou)}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{ pl: 0 }}>IoU (centroid-aligned)</TableCell>
                <TableCell align="right">{fmt(change.iou_centroid_aligned)}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{ pl: 0 }}>Centroid shift</TableCell>
                <TableCell align="right">{fmt(change.centroid_shift_m, 2)} m</TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{ pl: 0 }}>Area ratio</TableCell>
                <TableCell align="right">{fmt(change.area_ratio, 3)}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{ pl: 0, borderBottom: 0 }}>Hausdorff distance</TableCell>
                <TableCell align="right" sx={{ borderBottom: 0 }}>
                  {fmt(change.hausdorff_m, 2)} m
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Box>
      )}

      {change.attrs_changed.length > 0 && (
        <Box>
          <Typography variant="subtitle2" gutterBottom>Attributes changed</Typography>
          <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: "wrap" }}>
            {change.attrs_changed.map((a) => (
              <Chip key={a} label={a} size="small" variant="outlined" />
            ))}
          </Stack>
        </Box>
      )}

      {change.classification === "ambiguous" && (
        <Alert severity="warning" sx={{ py: 0.5 }}>
          {change.candidates.length} candidate pair
          {change.candidates.length === 1 ? "" : "s"} — kept unresolved rather than
          forcing a match to the highest score.
        </Alert>
      )}

      {(change.involves_repaired_geometry || change.touches_aoi_boundary) && (
        <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: "wrap" }}>
          {change.involves_repaired_geometry && (
            <Chip size="small" color="warning" variant="outlined" label="Repaired geometry" />
          )}
          {change.touches_aoi_boundary && (
            <Chip size="small" color="warning" variant="outlined" label="Touches AOI boundary" />
          )}
        </Stack>
      )}

      {history && (
        <>
          <Divider />
          <FeatureTimeline history={history} />
        </>
      )}
    </Stack>
  );
}
