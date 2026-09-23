import type { RefObject } from "react";

/** The signal the layer hooks use to know when it is safe to add sources and
 *  layers to the map's current style.
 *
 *  `ready` is a ref rather than a boolean because the style swap happens in
 *  an effect that runs *before* the layer hooks in the same commit: a state
 *  update would not reach them until the next render, so they would act on a
 *  stale `true` and MapLibre would throw "Style is not done loading".
 *  `version` changes each time a style finishes loading, which is what makes
 *  the layer hooks re-run and rebuild.
 */
export interface StyleState {
  ready: RefObject<boolean>;
  version: number;
}
