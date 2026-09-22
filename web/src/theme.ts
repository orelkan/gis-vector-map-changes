import { createTheme, type PaletteMode, type Theme } from "@mui/material";
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

export function buildTheme(mode: PaletteMode): Theme {
  return createTheme({
    palette: {
      mode,
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
