import type { ChangeDetail, Changeset, FeatureHistory, HistoryEntry } from "../../api/types";

/** Mirrors the real yearly changeset (2025-07-01 -> 2026-07-01) whose counts
 *  are pinned in docs/matching-spec.md section 7. */
export const yearlyChangeset: Changeset = {
  id: 20,
  algorithm_version: "v1",
  snapshot_a_id: 1,
  snapshot_b_id: 2,
  time_a: "2025-07-01T00:00:00+00:00",
  time_b: "2026-07-01T00:00:00+00:00",
  span_label: "1 year",
  changed_count: 457,
  unchanged_count: 26628,
  modified_geometry_count: 145,
  modified_attributes_count: 130,
  modified_geometry_and_attributes_count: 5,
  added_count: 72,
  removed_count: 103,
  ambiguous_count: 2,
};

export const monthlyChangeset: Changeset = {
  ...yearlyChangeset,
  id: 19,
  time_a: "2026-06-01T00:00:00+00:00",
  span_label: "1 month",
  changed_count: 56,
  unchanged_count: 26944,
  modified_geometry_count: 30,
  modified_attributes_count: 4,
  modified_geometry_and_attributes_count: 0,
  added_count: 4,
  removed_count: 18,
  ambiguous_count: 0,
};

export const fiveYearChangeset: Changeset = {
  ...yearlyChangeset,
  id: 46,
  time_a: "2021-07-01T00:00:00+00:00",
  span_label: "5 years",
  changed_count: 5430,
  unchanged_count: 21825,
  modified_geometry_count: 1500,
  modified_attributes_count: 2200,
  modified_geometry_and_attributes_count: 200,
  added_count: 1000,
  removed_count: 500,
  ambiguous_count: 30,
};

const square = (x: number, y: number): [number, number][] => [
  [x, y], [x + 0.001, y], [x + 0.001, y + 0.001], [x, y + 0.001], [x, y],
];

/** The re-traced building from docs/matching-spec.md: low IoU but high
 *  centroid-aligned IoU, i.e. moved rather than reshaped. */
export const retracedChange: ChangeDetail = {
  id: 501,
  changeset_id: 20,
  classification: "modified_geometry",
  match_method: "osm_id",
  match_score: 0.1193,
  classification_reason: "osm_id_match_modified_geometry",
  osm_ids_a: ["way/149268397"],
  osm_ids_b: ["way/149268397"],
  involves_repaired_geometry: false,
  touches_aoi_boundary: false,
  iou: 0.1193,
  iou_centroid_aligned: 0.6904,
  centroid_shift_m: 9.72,
  area_ratio: 0.69,
  hausdorff_m: 14.1,
  attrs_changed: [],
  candidates: [],
  geom_a: { type: "Polygon", coordinates: [square(34.78, 32.08)] },
  geom_b: { type: "Polygon", coordinates: [square(34.7801, 32.0801)] },
  time_a: "2025-07-01T00:00:00+00:00",
  time_b: "2026-07-01T00:00:00+00:00",
};

export const ambiguousChange: ChangeDetail = {
  ...retracedChange,
  id: 502,
  classification: "ambiguous",
  classification_reason: "partial_overlap",
  match_method: null,
  match_score: null,
  iou: null,
  iou_centroid_aligned: null,
  centroid_shift_m: null,
  area_ratio: null,
  hausdorff_m: null,
  osm_ids_a: ["way/506832165"],
  osm_ids_b: ["way/1427652677"],
  candidates: [
    {
      osm_id_a: "way/506832165", osm_id_b: "way/1427652677", iou: 0.223,
      iou_centroid_aligned: 0.31, centroid_shift_m: 12.0, area_ratio: 4.1,
      hausdorff_m: 30.0, attrs_changed: [],
    },
  ],
};

export const featureHistory: FeatureHistory = {
  osm_id: "way/149268397",
  history: [2021, 2022, 2023, 2024, 2025].map((year, i): HistoryEntry => ({
    snapshot_id: i + 1,
    requested_time: `${year}-07-01T00:00:00+00:00`,
    building: "house",
    category: "residential",
    name: null,
    raw_tags: { building: "house" },
    original_valid: true,
    repair_method: null,
    geometry: { type: "Polygon", coordinates: [square(34.78, 32.08)] },
    area_m2: 333.4,
  })).concat([<HistoryEntry>{
    snapshot_id: 6,
    requested_time: "2026-07-01T00:00:00+00:00",
    building: "house",
    category: "residential",
    name: null,
    raw_tags: { building: "house" },
    original_valid: true,
    repair_method: null,
    geometry: { type: "Polygon", coordinates: [square(34.7801, 32.0801)] },
    area_m2: 230.2,
  }]),
  changes: [{
    change_feature_id: 501,
    changeset_id: 20,
    classification: "modified_geometry",
    time_a: "2025-07-01T00:00:00+00:00",
    time_b: "2026-07-01T00:00:00+00:00",
  }],
};
