import type { ChangeDetail, Changeset, FeatureHistory } from "./types";

/** Requests go to the same origin; Vite proxies /api and /tiles to the
 *  FastAPI service in development (see vite.config.ts). */
async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      // Non-JSON error body; the status text is the best we have.
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  listChangesets: () => getJson<Changeset[]>("/api/changesets"),
  getChange: (id: number) => getJson<ChangeDetail>(`/api/changes/${id}`),
  getHistory: (osmId: string) =>
    getJson<FeatureHistory>(`/api/history/${osmId}`),
};

export function changeTileUrl(
  changesetId: number,
  classifications: readonly string[],
): string {
  const query = classifications.length
    ? `?classifications=${classifications.join(",")}`
    : "";
  return `${window.location.origin}/tiles/changes/${changesetId}/{z}/{x}/{y}.mvt${query}`;
}

export function buildingTileUrl(snapshotId: number): string {
  return `${window.location.origin}/tiles/buildings/${snapshotId}/{z}/{x}/{y}.mvt`;
}
