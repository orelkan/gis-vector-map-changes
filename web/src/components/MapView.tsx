import { useEffect, useRef, useState } from "react";
import {
  LngLatBounds,
  Map as MapLibreMap,
  NavigationControl,
  ScaleControl,
  type GeoJSONSource,
  type MapGeoJSONFeature,
  type MapMouseEvent,
  type VectorTileSource,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Box, type PaletteMode } from "@mui/material";
import { buildingTileUrl, changeTileUrl } from "../api/client";
import type { Classification, ChangeDetail } from "../api/types";
import { CLASSIFICATION_COLORS, basemapStyleUrl, SATELLITE_STYLE, type BasemapChoice } from "../theme";

// AOI centroid / bounds from aoi/tel_aviv_yafo_v1.geojson.
const TEL_AVIV_CENTER: [number, number] = [34.7899, 32.0847];
const DEFAULT_ZOOM = 12;

// The context layer is ~27k buildings; below this zoom a single tile would
// cover the whole city, so it stays hidden and only the (small) change
// layer renders -- which is the useful city-wide view anyway.
const CONTEXT_MIN_ZOOM = 15;

const CHANGE_SOURCE = "changes";
const CONTEXT_SOURCE = "buildings";
const OVERLAY_SOURCE = "selected-outline";

interface MapViewProps {
  mode: PaletteMode;
  basemap: BasemapChoice;
  changesetId: number | null;
  contextSnapshotId: number | null;
  visibleClassifications: Classification[];
  selectedChange: ChangeDetail | null;
  onSelectChange: (changeFeatureId: number) => void;
}

/** The satellite style has no theme pairing of its own -- it stays whatever
 *  imagery Esri serves regardless of light/dark mode -- so it doesn't need
 *  a `mode` argument the way basemapStyleUrl does. */
function styleFor(mode: PaletteMode, basemap: BasemapChoice) {
  return basemap === "satellite" ? SATELLITE_STYLE : basemapStyleUrl(mode);
}

/** Style expression colouring each change by its classification -- one
 *  declarative rule rather than per-feature JavaScript. */
function classificationColorExpression() {
  const cases = Object.entries(CLASSIFICATION_COLORS).flatMap(([name, color]) => [name, color]);
  return ["match", ["get", "classification"], ...cases, "#9e9e9e"] as never;
}

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
  const map = useRef<MapLibreMap | null>(null);
  // The basemap+mode combination the current map instance was built with.
  // setStyle() must not be called for a style the map already has -- doing
  // so on a freshly constructed map whose initial style is still loading can
  // leave MapLibre without a completed style, and then no tiles are ever
  // requested. React StrictMode's double-invoked effects make that easy to
  // hit.
  const appliedStyleKey = useRef<string | null>(null);
  // Whether the *current* style has fired its one-time "style.load" event --
  // i.e. its sources/layers are structurally in place and it is safe to
  // addSource/addLayer. This is deliberately not `map.isStyleLoaded()`:
  // that method (per MapLibre's own Style#loaded()) also requires every
  // current source's *tiles* to have finished downloading, so the
  // `styledata` event that eventually flips it true does not reliably fire
  // again for a listener registered after the fact -- which silently
  // dropped the very first-selected changeset's layer on page load (no
  // exception, just a build() that never ran). `style.load` fires once the
  // style spec/sources/layers are parsed, independent of tile downloads,
  // which is the actual precondition for addSource/addLayer.
  const [styleReady, setStyleReady] = useState(false);
  // Kept in a ref so the click handler, registered once, always calls the
  // latest callback without needing to be re-bound.
  const onSelect = useRef(onSelectChange);
  onSelect.current = onSelectChange;

  // Create the map once.
  useEffect(() => {
    if (!container.current || map.current) return;
    const instance = new MapLibreMap({
      container: container.current,
      style: styleFor(mode, basemap),
      center: TEL_AVIV_CENTER,
      zoom: DEFAULT_ZOOM,
      attributionControl: { compact: false },
    });
    instance.addControl(new NavigationControl(), "top-right");
    instance.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");
    map.current = instance;
    appliedStyleKey.current = `${mode}:${basemap}`;
    instance.once("style.load", () => setStyleReady(true));
    return () => {
      instance.remove();
      map.current = null;
      appliedStyleKey.current = null;
      setStyleReady(false);
    };
    // Only the initial mode/basemap are used here; changes are handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Swap the basemap when the theme or satellite toggle changes. setStyle
  // drops all custom layers, so they are rebuilt by the effect below once
  // the new style loads.
  useEffect(() => {
    const instance = map.current;
    const key = `${mode}:${basemap}`;
    // Skip when the map already carries this style -- notably on mount,
    // where the constructor has just set it.
    if (!instance || appliedStyleKey.current === key) return;
    appliedStyleKey.current = key;
    setStyleReady(false);
    instance.setStyle(styleFor(mode, basemap));
    instance.once("style.load", () => setStyleReady(true));
  }, [mode, basemap]);

  // (Re)build our layers on top of whatever basemap style is current.
  useEffect(() => {
    const instance = map.current;
    if (!instance || !styleReady) return;

    const build = () => {
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

      // Before/after overlay for the selected feature.
      if (!instance.getSource(OVERLAY_SOURCE)) {
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
      }
    };

    build();
  }, [styleReady, mode, basemap, changesetId, contextSnapshotId, visibleClassifications]);

  // Update the change tile URL when the interval or filter changes, without
  // tearing down the map.
  useEffect(() => {
    const instance = map.current;
    if (!instance || changesetId === null) return;
    const source = instance.getSource(CHANGE_SOURCE) as VectorTileSource | undefined;
    if (source?.setTiles) source.setTiles([changeTileUrl(changesetId, visibleClassifications)]);
  }, [changesetId, visibleClassifications]);

  // Click -> select. Registered once; reads the current callback from a ref.
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const handleClick = (event: MapMouseEvent) => {
      if (!instance.getLayer(`${CHANGE_SOURCE}-fill`)) return;
      const hits: MapGeoJSONFeature[] = instance.queryRenderedFeatures(event.point, {
        layers: [`${CHANGE_SOURCE}-fill`],
      });
      const id = hits[0]?.properties?.change_feature_id;
      if (typeof id === "number") onSelect.current(id);
    };
    instance.on("click", handleClick);
    const setPointer = () => (instance.getCanvas().style.cursor = "pointer");
    const clearPointer = () => (instance.getCanvas().style.cursor = "");
    instance.on("mouseenter", `${CHANGE_SOURCE}-fill`, setPointer);
    instance.on("mouseleave", `${CHANGE_SOURCE}-fill`, clearPointer);
    return () => {
      instance.off("click", handleClick);
      instance.off("mouseenter", `${CHANGE_SOURCE}-fill`, setPointer);
      instance.off("mouseleave", `${CHANGE_SOURCE}-fill`, clearPointer);
    };
  }, []);

  // Draw the selected feature's before/after outlines and fly to it.
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const source = instance.getSource(OVERLAY_SOURCE) as GeoJSONSource | undefined;
    if (!source) return;

    if (!selectedChange) {
      source.setData({ type: "FeatureCollection", features: [] });
      return;
    }

    const features = [];
    if (selectedChange.geom_a) {
      features.push({
        type: "Feature" as const,
        properties: { side: "before" },
        geometry: selectedChange.geom_a,
      });
    }
    if (selectedChange.geom_b) {
      features.push({
        type: "Feature" as const,
        properties: { side: "after" },
        geometry: selectedChange.geom_b,
      });
    }
    source.setData({ type: "FeatureCollection", features } as never);

    const coords = features.flatMap((f) =>
      (f.geometry.type === "Polygon"
        ? (f.geometry.coordinates as number[][][]).flat()
        : (f.geometry.coordinates as number[][][][]).flat(2)),
    );
    if (coords.length) {
      const bounds = coords.reduce(
        (acc, [lng, lat]) => acc.extend([lng, lat] as [number, number]),
        new LngLatBounds(
          coords[0] as [number, number],
          coords[0] as [number, number],
        ),
      );
      instance.fitBounds(bounds, { padding: 220, maxZoom: 19, duration: 800 });
    }
  }, [selectedChange]);

  return <Box ref={container} sx={{ position: "absolute", inset: 0 }} />;
}
