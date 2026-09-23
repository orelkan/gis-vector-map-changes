import { useEffect, useRef, useState, type RefObject } from "react";
import { Map as MapLibreMap, NavigationControl, ScaleControl } from "maplibre-gl";
import type { PaletteMode } from "@mui/material";
import { basemapStyleUrl, SATELLITE_STYLE, type BasemapChoice } from "../../theme";

// AOI centroid / bounds from aoi/tel_aviv_yafo_v1.geojson.
const TEL_AVIV_CENTER: [number, number] = [34.7899, 32.0847];
const DEFAULT_ZOOM = 12;

/** The satellite style has no theme pairing of its own -- it stays whatever
 *  imagery Esri serves regardless of light/dark mode -- so it doesn't need
 *  a `mode` argument the way basemapStyleUrl does. */
function styleFor(mode: PaletteMode, basemap: BasemapChoice) {
  return basemap === "satellite" ? SATELLITE_STYLE : basemapStyleUrl(mode);
}

/** Owns the MapLibre instance: construction, controls, basemap swapping and
 *  teardown.
 *
 *  Returns the map ref plus `styleReady`, which is the signal every other
 *  map hook waits on before touching sources or layers.
 */
export function useMapInstance(
  container: RefObject<HTMLDivElement | null>,
  mode: PaletteMode,
  basemap: BasemapChoice,
) {
  const map = useRef<MapLibreMap | null>(null);
  // The basemap+mode combination the current map instance was built with.
  // setStyle() must not be called for a style the map already has -- doing
  // so on a freshly constructed map whose initial style is still loading can
  // leave MapLibre without a completed style, and then no tiles are ever
  // requested. React StrictMode's double-invoked effects make that easy to
  // hit.
  const appliedStyleKey = useRef<string | null>(null);
  // Readiness is a ref, not state, because it has to be accurate
  // *synchronously*. The layer hooks below run later in the same commit as
  // the style swap, and a state update scheduled here would not be visible
  // to them until the next render -- so they would see a stale `true`, call
  // addSource() against a style that is mid-reload, and MapLibre would throw
  // "Style is not done loading". `styleVersion` is the state that actually
  // triggers the rebuild render once the new style has loaded.
  //
  // What the ref records: whether the *current* style has fired its one-time "style.load" event --
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
  const styleReady = useRef(false);
  const [styleVersion, setStyleVersion] = useState(0);

  const markStyleLoaded = () => {
    styleReady.current = true;
    setStyleVersion((v) => v + 1);
  };

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
    instance.once("style.load", markStyleLoaded);
    return () => {
      instance.remove();
      map.current = null;
      appliedStyleKey.current = null;
      styleReady.current = false;
    };
    // Only the initial mode/basemap are used here; changes are handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Swap the basemap when the theme or satellite toggle changes. setStyle
  // drops all custom layers, so they are rebuilt by useChangeLayers once
  // the new style loads.
  useEffect(() => {
    const instance = map.current;
    const key = `${mode}:${basemap}`;
    // Skip when the map already carries this style -- notably on mount,
    // where the constructor has just set it.
    if (!instance || appliedStyleKey.current === key) return;
    appliedStyleKey.current = key;
    // Synchronous, so the layer hooks later in this same commit see it.
    styleReady.current = false;
    // `diff: false` forces a full style reload. MapLibre's default is to
    // diff the new style against the current one and apply the delta in
    // place -- which, for the satellite style (an inline object rather than
    // a URL), succeeds: it removes this project's sources and layers,
    // because they are not part of the new style spec, WITHOUT ever firing
    // `style.load`. `styleReady` then never flips back to true, so the
    // layers are never rebuilt and the satellite basemap shows no data at
    // all (switching interval does not help either, since there is no
    // source left to retarget). A full reload always fires `style.load`,
    // which is the signal the rebuild depends on.
    instance.setStyle(styleFor(mode, basemap), { diff: false });
    instance.once("style.load", markStyleLoaded);
  }, [mode, basemap]);

  // `ready` is read at effect-run time (always current); `version` is what
  // puts the rebuild in a dependency array.
  return { map, style: { ready: styleReady, version: styleVersion } };
}
