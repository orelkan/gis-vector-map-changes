import { createTheme, type PaletteMode, type Theme } from "@mui/material";
import type { StyleSpecification } from "maplibre-gl";
import type { Classification } from "./api/types";

/** Colours for the six stored classifications.
 *
 * Chosen to stay legible on both the light (positron) and dark basemaps,
 * and to remain distinguishable without relying on a red/green contrast
 * alone -- added/removed differ in lightness as well as hue, so the two
 * most important categories stay separable for the common forms of
 * colour-vision deficiency.
 */
export const CLASSIFICATION_COLORS: Record<Classification, string> = {
  added: "#2e7d32",
  removed: "#c62828",
  modified_geometry: "#ed6c02",
  modified_attributes: "#0288d1",
  modified_geometry_and_attributes: "#7b1fa2",
  ambiguous: "#f9a825",
};

export const CLASSIFICATION_LABELS: Record<Classification, string> = {
  added: "Added",
  removed: "Removed",
  modified_geometry: "Geometry changed",
  modified_attributes: "Attributes changed",
  modified_geometry_and_attributes: "Geometry + attributes",
  ambiguous: "Ambiguous",
};

/** Basemap paired to the UI mode.
 *
 * Both are muted by design so the classification colours dominate rather
 * than competing with the basemap, and switching with the theme avoids a
 * dark UI sitting over a bright map.
 */
export function basemapStyleUrl(mode: PaletteMode): string {
  return mode === "dark"
    ? "https://tiles.openfreemap.org/styles/dark"
    : "https://tiles.openfreemap.org/styles/positron";
}

/** Optional satellite imagery layer, chosen independently of the light/dark
 *  UI theme. Esri World Imagery: no API key or billing account required
 *  (matching the "no key/billing" bar the OpenFreeMap/MapLibre choice was
 *  already held to), which is why it -- rather than Mapbox/Maxar/Bing
 *  satellite, all of which need a key -- was picked here. Deliberately no
 *  label layer on top: MapLibre's built-in AttributionControl already
 *  picks up this source's `attribution` string automatically once it's the
 *  active style, so no separate attribution wiring is needed. */
export const SATELLITE_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    satellite: {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Imagery © Esri, Maxar, Earthstar Geographics, GIS User Community",
    },
  },
  layers: [{ id: "satellite", type: "raster", source: "satellite" }],
};

export type BasemapChoice = "map" | "satellite";

export function buildTheme(mode: PaletteMode): Theme {
  return createTheme({
    palette: {
      mode,
      primary: { main: mode === "light" ? "#00796b" : "#4db6ac" },
      secondary: { main: mode === "light" ? "#ef6c00" : "#ffa726" },
      ...(mode === "light"
        ? { background: { default: "#f5f5f5", paper: "#ffffff" } }
        : { background: { default: "#121212", paper: "#1e1e1e" } }),
    },
    shape: { borderRadius: 10 },
    typography: {
      fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
      h6: { fontWeight: 600 },
    },
    components: {
      MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } },
    },
  });
}
