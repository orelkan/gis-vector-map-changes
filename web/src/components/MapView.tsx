import { useRef } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import { Box, type PaletteMode } from "@mui/material";
import type { Classification, ChangeDetail } from "../api/types";
import type { BasemapChoice } from "../theme";
import { useMapInstance } from "./map/useMapInstance";
import { useChangeLayers } from "./map/useChangeLayers";
import { useChangeClickHandler } from "./map/useChangeClickHandler";
import { useSelectionOverlay } from "./map/useSelectionOverlay";

interface MapViewProps {
  mode: PaletteMode;
  basemap: BasemapChoice;
  changesetId: number | null;
  contextSnapshotId: number | null;
  visibleClassifications: Classification[];
  selectedChange: ChangeDetail | null;
  onSelectChange: (changeFeatureId: number) => void;
}

/** The map, assembled from four hooks that each own one concern: the
 *  MapLibre instance and its basemap, this project's tile layers, the
 *  click-to-select behaviour, and the before/after overlay for the current
 *  selection. See ./map/ for each. */
export function MapView({
  mode,
  basemap,
  changesetId,
  contextSnapshotId,
  visibleClassifications,
  selectedChange,
  onSelectChange,
}: MapViewProps) {
  const container = useRef<HTMLDivElement>(null);
  const { map, style } = useMapInstance(container, mode, basemap);

  useChangeLayers(map, style, {
    changesetId,
    contextSnapshotId,
    visibleClassifications,
    mode,
  });
  useChangeClickHandler(map, onSelectChange);
  useSelectionOverlay(map, style, selectedChange, mode);

  return <Box ref={container} sx={{ position: "absolute", inset: 0 }} />;
}
