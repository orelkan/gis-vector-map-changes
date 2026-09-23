import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render } from "@testing-library/react";
import { useRef } from "react";

// maplibre-gl needs WebGL, which jsdom has not got. Stub it so the hook's
// own logic -- when it constructs, when it swaps style, and with which
// options -- can be asserted without a real map.
const setStyle = vi.fn();
const once = vi.fn();
const instance = {
  addControl: vi.fn(),
  remove: vi.fn(),
  setStyle,
  once,
};
vi.mock("maplibre-gl", () => ({
  Map: vi.fn(() => instance),
  NavigationControl: vi.fn(),
  ScaleControl: vi.fn(),
}));

import { useMapInstance } from "../map/useMapInstance";
import { SATELLITE_STYLE } from "../../theme";
import type { BasemapChoice } from "../../theme";
import type { PaletteMode } from "@mui/material";

let lastStyle: { ready: { current: boolean }; version: number } | null = null;

function Harness({ mode, basemap }: { mode: PaletteMode; basemap: BasemapChoice }) {
  const container = useRef<HTMLDivElement>(null);
  const { style } = useMapInstance(container, mode, basemap);
  lastStyle = style;
  return <div ref={container} />;
}

beforeEach(() => {
  setStyle.mockClear();
  once.mockClear();
});

describe("useMapInstance", () => {
  it("does not call setStyle for the style the map was constructed with", () => {
    render(<Harness mode="light" basemap="map" />);
    expect(setStyle).not.toHaveBeenCalled();
  });

  it("swaps to the satellite style with diff disabled", () => {
    // Regression: MapLibre's default `diff: true` applies an inline style
    // object as a delta, which strips this project's sources and layers
    // without ever firing `style.load`. `styleReady` then never flips back
    // to true, the layers are never rebuilt, and the satellite basemap
    // renders with no data on it at all. A full reload always fires
    // `style.load`, which is what the rebuild is driven by.
    const { rerender } = render(<Harness mode="light" basemap="map" />);
    rerender(<Harness mode="light" basemap="satellite" />);

    expect(setStyle).toHaveBeenCalledTimes(1);
    expect(setStyle).toHaveBeenCalledWith(SATELLITE_STYLE, { diff: false });
    // The rebuild signal must be re-armed for the incoming style.
    expect(once).toHaveBeenCalledWith("style.load", expect.any(Function));
  });

  it("swaps to the themed street style with diff disabled", () => {
    const { rerender } = render(<Harness mode="light" basemap="map" />);
    rerender(<Harness mode="dark" basemap="map" />);

    expect(setStyle).toHaveBeenCalledTimes(1);
    const [style, options] = setStyle.mock.calls[0];
    expect(typeof style).toBe("string");
    expect(options).toEqual({ diff: false });
  });

  it("marks the style not-ready synchronously when swapping", () => {
    // The layer hooks run later in the same commit as this swap. If
    // readiness were React state, they would still see `true` and call
    // addSource() against a style that is mid-reload, which MapLibre
    // rejects with "Style is not done loading". The ref has to be false by
    // the time setStyle returns.
    const { rerender } = render(<Harness mode="light" basemap="map" />);
    const styleLoad = once.mock.calls.find(([event]) => event === "style.load");
    act(() => styleLoad?.[1]());
    expect(lastStyle?.ready.current).toBe(true);

    let readyDuringSwap: boolean | undefined;
    setStyle.mockImplementationOnce(() => {
      readyDuringSwap = lastStyle?.ready.current;
    });
    rerender(<Harness mode="light" basemap="satellite" />);

    expect(readyDuringSwap).toBe(false);
    expect(lastStyle?.ready.current).toBe(false);
  });

  it("becomes ready again, and bumps the version, once the new style loads", () => {
    const { rerender } = render(<Harness mode="light" basemap="map" />);
    rerender(<Harness mode="light" basemap="satellite" />);
    const versionBefore = lastStyle?.version ?? -1;

    // Fire the style.load that was armed for the incoming style.
    const armed = once.mock.calls.filter(([event]) => event === "style.load");
    act(() => armed[armed.length - 1][1]());

    expect(lastStyle?.ready.current).toBe(true);
    expect(lastStyle?.version).toBeGreaterThan(versionBefore);
  });
});
