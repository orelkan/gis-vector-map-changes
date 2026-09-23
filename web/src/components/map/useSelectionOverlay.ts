import { useEffect, type RefObject } from "react";
import { LngLatBounds, Map as MapLibreMap, type GeoJSONSource } from "maplibre-gl";
import type { FeatureCollection } from "geojson";
import type { PaletteMode } from "@mui/material";
import type { ChangeDetail, GeoJsonGeometry } from "../../api/types";
import type { StyleState } from "./styleState";

const OVERLAY_SOURCE = "selected-outline";

type OverlayFeature = {
  type: "Feature";
  properties: { side: "before" | "after" };
  geometry: GeoJsonGeometry;
};

/** Every ring vertex of a polygon or multipolygon, flattened to positions. */
function positionsOf(geometry: GeoJsonGeometry): number[][] {
  return geometry.type === "Polygon"
    ? (geometry.coordinates as number[][][]).flat()
    : (geometry.coordinates as number[][][][]).flat(2);
}

/** Bounding box covering every given geometry, or null if there are none. */
function boundsOf(geometries: GeoJsonGeometry[]): LngLatBounds | null {
  const positions = geometries.flatMap(positionsOf);
  if (!positions.length) return null;
  const first = positions[0] as [number, number];
  return positions.reduce(
    (acc, [lng, lat]) => acc.extend([lng, lat] as [number, number]),
    new LngLatBounds(first, first),
  );
}

/** Draws the selected change's before/after outlines and flies to them.
 *
 *  The overlay source and its two layers are created once the style is
 *  ready; the data is then swapped per selection rather than rebuilt. */
export function useSelectionOverlay(
  map: RefObject<MapLibreMap | null>,
  style: StyleState,
  selectedChange: ChangeDetail | null,
  mode: PaletteMode,
) {
  useEffect(() => {
    const instance = map.current;
    // Read at run time, not from a captured render value -- see StyleState.
    if (!instance || !style.ready.current || instance.getSource(OVERLAY_SOURCE)) return;

    instance.addSource(OVERLAY_SOURCE, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    // "before" -- dashed, so it reads as the prior state.
    instance.addLayer({
      id: `${OVERLAY_SOURCE}-before`,
      type: "line",
      source: OVERLAY_SOURCE,
      filter: ["==", ["get", "side"], "before"],
      paint: {
        "line-color": mode === "dark" ? "#ffffff" : "#000000",
        "line-width": 2,
        "line-dasharray": [2, 2],
      },
    });
    // "after" -- solid.
    instance.addLayer({
      id: `${OVERLAY_SOURCE}-after`,
      type: "line",
      source: OVERLAY_SOURCE,
      filter: ["==", ["get", "side"], "after"],
      paint: { "line-color": "#ffeb3b", "line-width": 3 },
    });
  }, [map, style, style.version, mode]);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const source = instance.getSource(OVERLAY_SOURCE) as GeoJSONSource | undefined;
    if (!source) return;

    if (!selectedChange) {
      source.setData({ type: "FeatureCollection", features: [] });
      return;
    }

    const features: OverlayFeature[] = [];
    if (selectedChange.geom_a) {
      features.push({
        type: "Feature",
        properties: { side: "before" },
        geometry: selectedChange.geom_a,
      });
    }
    if (selectedChange.geom_b) {
      features.push({
        type: "Feature",
        properties: { side: "after" },
        geometry: selectedChange.geom_b,
      });
    }
    source.setData({ type: "FeatureCollection", features } as FeatureCollection);

    const bounds = boundsOf(features.map((f) => f.geometry));
    if (bounds) instance.fitBounds(bounds, { padding: 220, maxZoom: 19, duration: 800 });
  }, [map, selectedChange]);
}
