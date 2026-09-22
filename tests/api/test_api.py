"""API tests against the real local Postgres with real published data.

Requires `make up && make migrate` plus a completed publish run. Marked `db`
and excluded from the default offline suite; run with `make test-db`.

Tiles are asserted by *decoding* the MVT and checking feature identity and
properties -- CLAUDE.md forbids tests that assert only counts or sizes.
"""

from __future__ import annotations

import os

import mapbox_vector_tile
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db

# Tile covering central Tel Aviv-Yafo at z12 (computed from the AOI centroid).
TILE_Z, TILE_X, TILE_Y = 12, 2443, 1662


@pytest.fixture(scope="module")
def client(): 
    os.environ.setdefault("GIS_DB_HOST", "localhost")
    os.environ.setdefault("GIS_DB_PORT", "5432")
    os.environ.setdefault("GIS_DB_NAME", "gis")
    os.environ.setdefault("GIS_DB_USER", "gis")
    os.environ.setdefault("GIS_DB_PASSWORD", "gis-local-dev")
    try:
        from api.main import app
        with TestClient(app) as c:
            if c.get("/api/health").status_code != 200:
                pytest.skip("API cannot reach the database")
            yield c
    except Exception as exc:  # noqa: BLE001 -- no local DB means skip, not fail
        pytest.skip(f"API/database unavailable: {exc}")


@pytest.fixture(scope="module")
def yearly_changeset(client):
    """The 2025-07-01 -> 2026-07-01 changeset, whose exact expected counts
    are pinned in docs/matching-behavior.md section 7."""
    for cs in client.get("/api/changesets").json():
        if cs["time_a"].startswith("2025-07-01") and cs["time_b"].startswith("2026-07-01"):
            return cs
    pytest.skip("yearly changeset not published")


# --- basic endpoints ------------------------------------------------------


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "OpenStreetMap" in body["attribution"]


def test_list_snapshots_returns_published_counts(client):
    snapshots = client.get("/api/snapshots").json()
    assert len(snapshots) >= 7
    for s in snapshots:
        # Every snapshot should be fully published: the serving layer's row
        # count must match what ingestion recorded.
        assert s["published_feature_count"] == s["feature_count"]


def test_changesets_expose_span_labels(client):
    changesets = client.get("/api/changesets").json()
    labels = {c["span_label"] for c in changesets}
    # The three named intervals the UI offers.
    assert "1 month" in labels
    assert "1 year" in labels
    assert "5 years" in labels


def test_changeset_counts_match_matching_spec(yearly_changeset):
    """Parity with docs/matching-behavior.md section 7's verified table."""
    cs = yearly_changeset
    assert cs["unchanged_count"] == 26628
    assert cs["modified_geometry_count"] == 145
    assert cs["modified_attributes_count"] == 130
    assert cs["modified_geometry_and_attributes_count"] == 5
    assert cs["added_count"] == 72
    assert cs["removed_count"] == 103
    assert cs["ambiguous_count"] == 2
    assert cs["changed_count"] == 457


def test_unknown_changeset_is_404(client):
    assert client.get("/api/changesets/99999999").status_code == 404


# --- tiles ----------------------------------------------------------------


def _decode(content: bytes) -> dict:
    return mapbox_vector_tile.decode(content)


def test_change_tile_decodes_to_real_features(client, yearly_changeset):
    r = client.get(f"/tiles/changes/{yearly_changeset['id']}/{TILE_Z}/{TILE_X}/{TILE_Y}.mvt")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.mapbox-vector-tile"

    tile = _decode(r.content)
    assert "changes" in tile
    features = tile["changes"]["features"]
    assert features, "expected change features in the central Tel Aviv tile"

    props = features[0]["properties"]
    # Exactly the properties the map styles and popups from.
    assert {"change_feature_id", "classification", "classification_reason"} <= set(props)
    assert props["classification"] in {
        "added", "removed", "modified_geometry", "modified_attributes",
        "modified_geometry_and_attributes", "ambiguous",
    }


def test_change_tile_never_contains_unchanged(client, yearly_changeset):
    """`unchanged` is derived from absence, never stored -- so it must never
    appear in a tile even though it is 98% of the comparison."""
    r = client.get(f"/tiles/changes/{yearly_changeset['id']}/{TILE_Z}/{TILE_X}/{TILE_Y}.mvt")
    classifications = {
        f["properties"]["classification"] for f in _decode(r.content)["changes"]["features"]
    }
    assert "unchanged" not in classifications


def test_change_tile_classification_filter_applies(client, yearly_changeset):
    r = client.get(
        f"/tiles/changes/{yearly_changeset['id']}/{TILE_Z}/{TILE_X}/{TILE_Y}.mvt",
        params={"classifications": "added"},
    )
    tile = _decode(r.content)
    if tile.get("changes", {}).get("features"):
        assert {f["properties"]["classification"] for f in tile["changes"]["features"]} == {"added"}


def test_change_tile_rejects_unknown_classification(client, yearly_changeset):
    r = client.get(
        f"/tiles/changes/{yearly_changeset['id']}/{TILE_Z}/{TILE_X}/{TILE_Y}.mvt",
        params={"classifications": "definitely_not_a_class"},
    )
    assert r.status_code == 400
    assert "unknown classification" in r.json()["detail"]


def test_change_tile_rejects_unchanged_as_a_filter(client, yearly_changeset):
    """Asking for `unchanged` is a 400 with an explanation, not an empty
    tile that silently looks like 'nothing changed'."""
    r = client.get(
        f"/tiles/changes/{yearly_changeset['id']}/{TILE_Z}/{TILE_X}/{TILE_Y}.mvt",
        params={"classifications": "unchanged"},
    )
    assert r.status_code == 400
    assert "derived from absence" in r.json()["detail"]


@pytest.mark.parametrize("z,x,y", [(-1, 0, 0), (30, 0, 0), (12, 99999, 1662), (12, 2443, -5)])
def test_tile_rejects_out_of_range_coordinates(client, yearly_changeset, z, x, y):
    r = client.get(f"/tiles/changes/{yearly_changeset['id']}/{z}/{x}/{y}.mvt")
    assert r.status_code in (400, 422), "bad tile coords must be 4xx, never 500"


def test_building_tile_decodes(client):
    snapshot = client.get("/api/snapshots").json()[-1]
    r = client.get(f"/tiles/buildings/{snapshot['id']}/15/19555/13300.mvt")
    assert r.status_code == 200
    tile = _decode(r.content)
    if tile.get("buildings", {}).get("features"):
        assert "osm_id" in tile["buildings"]["features"][0]["properties"]


def test_empty_tile_is_not_an_error(client, yearly_changeset):
    """A tile in the middle of the ocean has no data; that's a valid answer."""
    r = client.get(f"/tiles/changes/{yearly_changeset['id']}/12/100/100.mvt")
    assert r.status_code == 200


# --- detail + history -----------------------------------------------------


def test_change_detail_includes_before_and_after_geometry(client, yearly_changeset):
    """way/149268397 is the re-traced building from docs/matching-behavior.md;
    its metrics and both geometries must survive the round trip."""
    r = client.get(f"/tiles/changes/{yearly_changeset['id']}/{TILE_Z}/{TILE_X}/{TILE_Y}.mvt")
    ids = [f["properties"]["change_feature_id"] for f in _decode(r.content)["changes"]["features"]]

    target = None
    for cid in ids:
        detail = client.get(f"/api/changes/{cid}").json()
        if "way/149268397" in detail["osm_ids_a"]:
            target = detail
            break
    if target is None:
        pytest.skip("way/149268397 not in this tile")

    assert target["classification"] == "modified_geometry"
    assert target["iou"] == pytest.approx(0.1193, abs=1e-4)
    assert target["iou_centroid_aligned"] == pytest.approx(0.6904, abs=1e-4)
    assert target["centroid_shift_m"] == pytest.approx(9.72, abs=0.01)
    # Both geometries present -> the before/after overlay is renderable.
    assert target["geom_a"]["type"] in ("Polygon", "MultiPolygon")
    assert target["geom_b"]["type"] in ("Polygon", "MultiPolygon")
    assert target["geom_a"] != target["geom_b"]


def test_feature_history_spans_all_snapshots(client):
    r = client.get("/api/history/way/149268397")
    assert r.status_code == 200
    body = r.json()

    assert body["osm_id"] == "way/149268397"
    # Present in every published snapshot.
    assert len(body["history"]) == 7
    times = [h["requested_time"] for h in body["history"]]
    assert times == sorted(times), "history must be chronological"
    assert all(h["geometry"]["type"] in ("Polygon", "MultiPolygon") for h in body["history"])
    # And it participates in the changesets that classified it as changed.
    assert body["changes"], "expected this building to appear in at least one changeset"


def test_feature_history_unknown_id_is_404(client):
    assert client.get("/api/history/way/000000000").status_code == 404
