import { useEffect, type RefObject } from "react";
import {
  Map as MapLibreMap,
  type ExpressionSpecification,
  type VectorTileSource,
} from "maplibre-gl";
import type { PaletteMode } from "@mui/material";
import { buildingTileUrl, changeTileUrl } from "../../api/client";
import type { Classification } from "../../api/types";
import type { StyleState } from "./styleState";
import { CLASSIFICATION_COLORS } from "../../theme";

// The context layer is ~27k buildings; below this zoom a single tile would
// cover the whole city, so it stays hidden and only the (small) change
// layer renders -- which is the useful city-wide view anyway.
const CONTEXT_MIN_ZOOM = 15;

export const CHANGE_SOURCE = "changes";
const CONTEXT_SOURCE = "buildings";

/** Style expression colouring each change by its classification -- one
 *  declarative rule rather than per-feature JavaScript.
 *
 *  Written out per branch rather than spread from CLASSIFICATION_COLORS:
 *  MapLibre types a `match` expression as a tuple, which a spread cannot
 *  satisfy, and the previous `as never` cast silenced all checking of the
 *  expression. Listing the branches keeps it fully type-checked, and the
 *  colours still come from the single source in theme.ts. */
function classificationColorExpression(): ExpressionSpecification {
  return [
    "match",
    ["get", "classification"],
    "added",
    CLASSIFICATION_COLORS.added,
    "removed",
    CLASSIFICATION_COLORS.removed,
    "modified_geometry",
    CLASSIFICATION_COLORS.modified_geometry,
    "modified_attributes",
    CLASSIFICATION_COLORS.modified_attributes,
    "modified_geometry_and_attributes",
    CLASSIFICATION_COLORS.modified_geometry_and_attributes,
    "ambiguous",
    CLASSIFICATION_COLORS.ambiguous,
    "#9e9e9e",
  ];
}

interface LayerOptions {
  changesetId: number | null;
  contextSnapshotId: number | null;
  visibleClassifications: Classification[];
  mode: PaletteMode;
}

/** (Re)builds this project's own layers on top of whatever basemap style is
 *  current, and keeps the change layer's tile URL in step with the selected
 *  interval and filter. */
export function useChangeLayers(
  map: RefObject<MapLibreMap | null>,
  style: StyleState,
  { changesetId, contextSnapshotId, visibleClassifications, mode }: LayerOptions,
) {
  useEffect(() => {
    const instance = map.current;
    // Read at run time, not from a captured render value -- see StyleState.
    if (!instance || !style.ready.current) return;

    if (contextSnapshotId !== null && !instance.getSource(CONTEXT_SOURCE)) {
      instance.addSource(CONTEXT_SOURCE, {
        type: "vector",
        tiles: [buildingTileUrl(contextSnapshotId)],
        minzoom: CONTEXT_MIN_ZOOM,
        maxzoom: 18,
      });
      instance.addLayer({
        id: CONTEXT_SOURCE,
        type: "fill",
        source: CONTEXT_SOURCE,
        "source-layer": "buildings",
        minzoom: CONTEXT_MIN_ZOOM,
        paint: {
          "fill-color": mode === "dark" ? "#5a5a5a" : "#c9c9c9",
          "fill-opacity": 0.45,
          "fill-outline-color": mode === "dark" ? "#7a7a7a" : "#b0b0b0",
        },
      });
    }

    if (changesetId !== null && !instance.getSource(CHANGE_SOURCE)) {
      instance.addSource(CHANGE_SOURCE, {
        type: "vector",
        tiles: [changeTileUrl(changesetId, visibleClassifications)],
        minzoom: 0,
        maxzoom: 18,
      });
      instance.addLayer({
        id: `${CHANGE_SOURCE}-fill`,
        type: "fill",
        source: CHANGE_SOURCE,
        "source-layer": "changes",
        paint: {
          "fill-color": classificationColorExpression(),
          "fill-opacity": 0.55,
        },
      });
      instance.addLayer({
        id: `${CHANGE_SOURCE}-outline`,
        type: "line",
        source: CHANGE_SOURCE,
        "source-layer": "changes",
        paint: {
          "line-color": classificationColorExpression(),
          "line-width": 1.5,
        },
      });
    }
    // changesetId / visibleClassifications are dependencies because a change
    // to either must create the layer if the previous render had none. When
    // the source already exists this body is a no-op for them by design --
    // the tile URL is updated by the effect below rather than by tearing the
    // layer down and rebuilding it.
  }, [map, style, style.version, mode, changesetId, contextSnapshotId, visibleClassifications]);

  // Update the change tile URL when the interval or filter changes, without
  // tearing down the map.
  useEffect(() => {
    const instance = map.current;
    if (!instance || changesetId === null) return;
    const source = instance.getSource(CHANGE_SOURCE) as VectorTileSource | undefined;
    if (source?.setTiles) source.setTiles([changeTileUrl(changesetId, visibleClassifications)]);
  }, [map, changesetId, visibleClassifications]);
}
