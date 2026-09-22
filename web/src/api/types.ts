/** Types mirroring the FastAPI responses (see api/main.py). */

/** The classifications a stored change record can carry.
 *
 * `unchanged` is deliberately absent: it is derived from absence rather than
 * stored (see sql/003_create_feature_tables.sql), so it can never appear in
 * a tile or a change record.
 */
export const CLASSIFICATIONS = [
  "added",
  "removed",
  "modified_geometry",
  "modified_attributes",
  "modified_geometry_and_attributes",
  "ambiguous",
] as const;

export type Classification = (typeof CLASSIFICATIONS)[number];

export interface Changeset {
  id: number;
  algorithm_version: string;
  snapshot_a_id: number;
  snapshot_b_id: number;
  time_a: string;
  time_b: string;
  span_label: string;
  changed_count: number;
  unchanged_count: number;
  modified_geometry_count: number;
  modified_attributes_count: number;
  modified_geometry_and_attributes_count: number;
  added_count: number;
  removed_count: number;
  ambiguous_count: number;
}

export interface Snapshot {
  id: number;
  requested_time: string;
  source_query_version: string;
  feature_count: number;
  invalid_geometry_count: number;
  repaired_geometry_count: number;
  published_feature_count: number;
}

export interface GeoJsonGeometry {
  type: "Polygon" | "MultiPolygon";
  coordinates: number[][][] | number[][][][];
}

export interface CandidateMetrics {
  osm_id_a: string;
  osm_id_b: string;
  iou: number;
  iou_centroid_aligned: number;
  centroid_shift_m: number;
  area_ratio: number;
  hausdorff_m: number;
  attrs_changed: string[];
}

export interface ChangeDetail {
  id: number;
  changeset_id: number;
  classification: Classification;
  match_method: string | null;
  match_score: number | null;
  classification_reason: string;
  osm_ids_a: string[];
  osm_ids_b: string[];
  involves_repaired_geometry: boolean;
  touches_aoi_boundary: boolean;
  iou: number | null;
  iou_centroid_aligned: number | null;
  centroid_shift_m: number | null;
  area_ratio: number | null;
  hausdorff_m: number | null;
  attrs_changed: string[];
  candidates: CandidateMetrics[];
  /** Before-geometry: null for `added`. */
  geom_a: GeoJsonGeometry | null;
  /** After-geometry: null for `removed`. */
  geom_b: GeoJsonGeometry | null;
  time_a: string;
  time_b: string;
}

export interface HistoryEntry {
  snapshot_id: number;
  requested_time: string;
  building: string | null;
  category: string | null;
  name: string | null;
  raw_tags: Record<string, string>;
  original_valid: boolean;
  repair_method: string | null;
  geometry: GeoJsonGeometry;
  area_m2: number;
}

export interface ChangeParticipation {
  change_feature_id: number;
  changeset_id: number;
  classification: Classification;
  time_a: string;
  time_b: string;
}

/** One building's full trajectory across every snapshot held.
 *
 * This is what makes "many different timestamps" answerable: before/after is
 * always relative to one interval, but this shows the whole sequence.
 */
export interface FeatureHistory {
  osm_id: string;
  history: HistoryEntry[];
  changes: ChangeParticipation[];
}
