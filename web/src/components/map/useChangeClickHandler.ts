import { useEffect, useRef, type RefObject } from "react";
import { Map as MapLibreMap, type MapGeoJSONFeature, type MapMouseEvent } from "maplibre-gl";
import { CHANGE_SOURCE } from "./useChangeLayers";

/** Click -> select. Registered once; reads the current callback from a ref
 *  so the listener never needs re-binding. */
export function useChangeClickHandler(
  map: RefObject<MapLibreMap | null>,
  onSelectChange: (changeFeatureId: number) => void,
) {
  const onSelect = useRef(onSelectChange);
  onSelect.current = onSelectChange;

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const layerId = `${CHANGE_SOURCE}-fill`;

    const handleClick = (event: MapMouseEvent) => {
      if (!instance.getLayer(layerId)) return;
      const hits: MapGeoJSONFeature[] = instance.queryRenderedFeatures(event.point, {
        layers: [layerId],
      });
      const id = hits[0]?.properties?.change_feature_id;
      if (typeof id === "number") onSelect.current(id);
    };
    const setPointer = () => (instance.getCanvas().style.cursor = "pointer");
    const clearPointer = () => (instance.getCanvas().style.cursor = "");

    instance.on("click", handleClick);
    instance.on("mouseenter", layerId, setPointer);
    instance.on("mouseleave", layerId, clearPointer);
    return () => {
      instance.off("click", handleClick);
      instance.off("mouseenter", layerId, setPointer);
      instance.off("mouseleave", layerId, clearPointer);
    };
  }, [map]);
}
