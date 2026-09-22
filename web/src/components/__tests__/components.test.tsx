import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "@mui/material";
import { buildTheme } from "../../theme";
import { CLASSIFICATIONS } from "../../api/types";
import { ChangesetTimeline } from "../ChangesetTimeline";
import { ClassificationFilter } from "../ClassificationFilter";
import { FeatureDetailPanel } from "../FeatureDetailPanel";
import { FeatureTimeline } from "../FeatureTimeline";
import {
  ambiguousChange, featureHistory, monthlyChangeset, retracedChange, yearlyChangeset,
} from "./fixtures";

function renderWith(ui: React.ReactElement, mode: "light" | "dark" = "light") {
  return render(<ThemeProvider theme={buildTheme(mode)}>{ui}</ThemeProvider>);
}

describe("ChangesetTimeline", () => {
  it("shows each interval's span label as a bracket on the track", () => {
    renderWith(
      <ChangesetTimeline
        changesets={[monthlyChangeset, yearlyChangeset]}
        selectedId={monthlyChangeset.id}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("1 month")).toBeInTheDocument();
    expect(screen.getByText("1 year")).toBeInTheDocument();
  });

  it("marks the selected interval's bracket as pressed", () => {
    renderWith(
      <ChangesetTimeline
        changesets={[monthlyChangeset, yearlyChangeset]}
        selectedId={monthlyChangeset.id}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("1 month").closest("button")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("1 year").closest("button")).toHaveAttribute("aria-pressed", "false");
  });

  it("reports the chosen interval when its bracket is clicked", async () => {
    const onChange = vi.fn();
    renderWith(
      <ChangesetTimeline
        changesets={[monthlyChangeset, yearlyChangeset]}
        selectedId={monthlyChangeset.id}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByText("1 year").closest("button")!);
    expect(onChange).toHaveBeenCalledWith(yearlyChangeset.id);
  });

  it("labels the start and end date of each interval on the axis", () => {
    renderWith(
      <ChangesetTimeline
        changesets={[monthlyChangeset, yearlyChangeset]}
        selectedId={monthlyChangeset.id}
        onChange={vi.fn()}
      />,
    );
    // yearlyChangeset: 2025-07-01 -> 2026-07-01; monthlyChangeset starts 2026-06-01.
    expect(screen.getByText("2025-07")).toBeInTheDocument();
    expect(screen.getByText("2026-06")).toBeInTheDocument();
    expect(screen.getByText("2026-07")).toBeInTheDocument();
  });
});

describe("ClassificationFilter", () => {
  it("lists every stored classification with its count", () => {
    renderWith(
      <ClassificationFilter
        changeset={yearlyChangeset}
        visible={[...CLASSIFICATIONS]}
        onToggle={vi.fn()}
      />,
    );
    expect(screen.getByText("Added")).toBeInTheDocument();
    expect(screen.getByText("72")).toBeInTheDocument();   // added_count
    expect(screen.getByText("103")).toBeInTheDocument();  // removed_count
  });

  it("never offers `unchanged` as a filter, since it is derived not stored", () => {
    renderWith(
      <ClassificationFilter
        changeset={yearlyChangeset}
        visible={[...CLASSIFICATIONS]}
        onToggle={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText(/^Unchanged$/i)).not.toBeInTheDocument();
    // It is still *reported*, just not drawable.
    expect(screen.getByText(/26,628 buildings unchanged/)).toBeInTheDocument();
  });

  it("toggles a classification", async () => {
    const onToggle = vi.fn();
    renderWith(
      <ClassificationFilter
        changeset={yearlyChangeset}
        visible={[...CLASSIFICATIONS]}
        onToggle={onToggle}
      />,
    );
    await userEvent.click(screen.getByLabelText("Added"));
    expect(onToggle).toHaveBeenCalledWith("added");
  });
});

describe("FeatureDetailPanel", () => {
  it("prompts when nothing is selected", () => {
    renderWith(
      <FeatureDetailPanel change={null} history={null} loading={false} error={null} />,
    );
    expect(screen.getByText(/Click a highlighted building/)).toBeInTheDocument();
  });

  it("shows the metrics for a geometry change", () => {
    renderWith(
      <FeatureDetailPanel change={retracedChange} history={null} loading={false} error={null} />,
    );
    expect(screen.getByText("Geometry changed")).toBeInTheDocument();
    expect(screen.getByText("way/149268397")).toBeInTheDocument();
    expect(screen.getByText("0.1193")).toBeInTheDocument();  // iou
    expect(screen.getByText("0.6904")).toBeInTheDocument();  // centroid-aligned
    expect(screen.getByText("9.72 m")).toBeInTheDocument();  // centroid shift
  });

  it("explains a re-trace as movement rather than a rebuild", () => {
    // The whole point of carrying iou_centroid_aligned: a low IoU with a
    // much higher aligned IoU means moved, not unrecognisably different.
    renderWith(
      <FeatureDetailPanel change={retracedChange} history={null} loading={false} error={null} />,
    );
    expect(screen.getByText(/re-trace or re-survey rather than a rebuild/)).toBeInTheDocument();
  });

  it("explains the before/after outline convention", () => {
    renderWith(
      <FeatureDetailPanel change={retracedChange} history={null} loading={false} error={null} />,
    );
    expect(screen.getByText(/Dashed outline = before/)).toBeInTheDocument();
  });

  it("says ambiguous matches were left unresolved", () => {
    renderWith(
      <FeatureDetailPanel change={ambiguousChange} history={null} loading={false} error={null} />,
    );
    expect(screen.getByText(/kept unresolved rather than/)).toBeInTheDocument();
  });

  it("surfaces errors", () => {
    renderWith(
      <FeatureDetailPanel change={null} history={null} loading={false} error="404: nope" />,
    );
    expect(screen.getByText("404: nope")).toBeInTheDocument();
  });
});

describe("FeatureTimeline", () => {
  it("lists the building at every snapshot, chronologically", () => {
    renderWith(<FeatureTimeline history={featureHistory} />);
    expect(screen.getByText("2021-07-01")).toBeInTheDocument();
    expect(screen.getByText("2026-07-01")).toBeInTheDocument();
  });

  it("marks the interval where the footprint changed", () => {
    renderWith(<FeatureTimeline history={featureHistory} />);
    // 333.4 -> 230.2 m2 between 2025 and 2026.
    expect(screen.getByText("-103 m²")).toBeInTheDocument();
    expect(screen.getByText("Geometry changed")).toBeInTheDocument();
  });
});

describe("theming", () => {
  it.each(["light", "dark"] as const)("renders in %s mode", (mode) => {
    renderWith(
      <FeatureDetailPanel change={retracedChange} history={null} loading={false} error={null} />,
      mode,
    );
    expect(screen.getByText("Geometry changed")).toBeInTheDocument();
  });
});
