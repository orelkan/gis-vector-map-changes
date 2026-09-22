import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  fiveYearChangeset, monthlyChangeset, retracedChange, featureHistory, yearlyChangeset,
} from "../components/__tests__/fixtures";

// MapLibre needs WebGL, which jsdom does not provide. The map itself is
// exercised in a real browser; here we verify the surrounding data flow --
// fetch -> picker -> filter -> selection -> detail panel -- and capture the
// props the map would have received.
const mapProps: Record<string, unknown>[] = [];
vi.mock("../components/MapView", () => ({
  MapView: (props: Record<string, unknown>) => {
    mapProps.push(props);
    return <div data-testid="map" />;
  },
}));

import App from "../App";

beforeEach(() => {
  mapProps.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const json = (body: unknown) =>
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      if (url.endsWith("/api/changesets")) return json([monthlyChangeset, yearlyChangeset]);
      if (url.includes("/api/changes/")) return json(retracedChange);
      if (url.includes("/api/history/")) return json(featureHistory);
      return new Response("not found", { status: 404 });
    }),
  );
});

describe("App", () => {
  it("loads changesets and falls back to the first one when there is no 5-year interval", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    await waitFor(() => expect(mapProps.at(-1)?.changesetId).toBe(monthlyChangeset.id));
  });

  it("defaults to the 5-year interval when one exists -- most data on first paint", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const json = (body: unknown) =>
          new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
        if (url.endsWith("/api/changesets")) {
          return json([monthlyChangeset, yearlyChangeset, fiveYearChangeset]);
        }
        return new Response("not found", { status: 404 });
      }),
    );
    render(<App />);
    await waitFor(() => expect(mapProps.at(-1)?.changesetId).toBe(fiveYearChangeset.id));
  });

  it("passes the after-snapshot as the map's context layer", async () => {
    // The grey context layer shows the interval's *later* state, and is the
    // shared layer reused across intervals.
    render(<App />);
    await waitFor(() =>
      expect(mapProps.at(-1)?.contextSnapshotId).toBe(monthlyChangeset.snapshot_b_id),
    );
  });

  it("shows the selected changeset's counts in the filter", async () => {
    render(<App />);
    await waitFor(() =>
      expect(screen.getByText(/26,944 buildings unchanged/)).toBeInTheDocument(),
    );
  });

  it("loads change detail and history when the map reports a selection", async () => {
    render(<App />);
    // Wait for the changesets fetch to actually settle (not just for the map
    // div to exist -- that renders on the very first pass). Firing the
    // selection before selectedChangesetId's *first* value lands would race
    // against the effect that clears `change` whenever selectedChangesetId
    // changes, which would otherwise wipe the selection right back out.
    await waitFor(() => expect(mapProps.at(-1)?.changesetId).toBe(monthlyChangeset.id));

    const onSelect = mapProps.at(-1)?.onSelectChange as (id: number) => void;
    onSelect(retracedChange.id);

    await waitFor(() => expect(screen.getByText("0.1193")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("2021-07-01")).toBeInTheDocument());
  });

  it("clears the selection when the interval changes", async () => {
    // A change record belongs to one changeset; keeping it visible across a
    // switch would misattribute it to the wrong interval.
    render(<App />);
    await waitFor(() => expect(mapProps.at(-1)?.changesetId).toBe(monthlyChangeset.id));
    (mapProps.at(-1)?.onSelectChange as (id: number) => void)(retracedChange.id);
    await waitFor(() => expect(screen.getByText("0.1193")).toBeInTheDocument());

    await userEvent.click(screen.getByText("1 year").closest("button")!);

    await waitFor(() =>
      expect(screen.getByText(/Click a highlighted building/)).toBeInTheDocument(),
    );
  });

  it("defaults to the street basemap and can switch to satellite", async () => {
    render(<App />);
    await waitFor(() => expect(mapProps.at(-1)?.basemap).toBe("map"));
    await userEvent.click(screen.getByLabelText("Satellite imagery view"));
    await waitFor(() => expect(mapProps.at(-1)?.basemap).toBe("satellite"));
  });

  it("always shows OpenStreetMap attribution", async () => {
    render(<App />);
    expect(screen.getByText(/OpenStreetMap contributors/)).toBeInTheDocument();
    expect(screen.getByText(/ODbL/)).toBeInTheDocument();
  });

  it("shows the About dialog with attribution and a link to the project", async () => {
    render(<App />);
    expect(screen.queryByText(/by Orel Kanditan/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "About" }));

    expect(screen.getByText(/by Orel Kanditan/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /GitHub/ })).toHaveAttribute(
      "href",
      "https://github.com/orelkan/gis-vector-map-changes",
    );
  });

  it("toggles colour mode and hands it to the map", async () => {
    render(<App />);
    await userEvent.click(screen.getByLabelText("toggle color mode"));
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    // The map receives the mode so the basemap can follow the theme.
    expect(["light", "dark"]).toContain(mapProps.at(-1)?.mode);
  });
});
