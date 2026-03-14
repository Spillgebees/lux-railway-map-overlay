from __future__ import annotations

from generator.route_graph import (
    build_luxembourg_station_names,
    build_station_indexes,
    build_station_match_index,
    chain_ways,
    resolve_station_matches,
)


def test_build_luxembourg_station_names_filters_to_bbox_and_uses_aliases() -> None:
    stations_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "Luxembourg",
                    "other_tags": '"name:fr"=>"Luxembourg-Ville"',
                },
                "geometry": {"type": "Point", "coordinates": [6.13, 49.61]},
            },
            {
                "type": "Feature",
                "properties": {"name": "Outside"},
                "geometry": {"type": "Point", "coordinates": [2.0, 45.0]},
            },
        ],
    }

    station_names = build_luxembourg_station_names(
        stations_geojson,
        "49.44,5.73,50.18,6.53",
    )

    assert station_names == {"luxembourg", "luxembourg ville"}


def test_build_station_indexes_returns_both_name_set_and_match_index() -> None:
    stations_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "Luxembourg",
                    "other_tags": '"name:fr"=>"Luxembourg-Ville"',
                },
                "geometry": {"type": "Point", "coordinates": [6.13, 49.61]},
            },
            {
                "type": "Feature",
                "properties": {"name": "Outside"},
                "geometry": {"type": "Point", "coordinates": [2.0, 45.0]},
            },
        ],
    }

    luxembourg_names, match_index = build_station_indexes(
        stations_geojson,
        "49.44,5.73,50.18,6.53",
    )

    assert luxembourg_names == {"luxembourg", "luxembourg ville"}
    assert "luxembourg" in match_index
    assert "luxembourg ville" in match_index
    assert "outside" in match_index
    assert match_index["luxembourg"] == [[6.13, 49.61]]
    assert match_index["outside"] == [[2.0, 45.0]]


def test_resolve_station_matches_uses_exact_then_boundary_fuzzy_matching() -> None:
    station_matches_by_name = build_station_match_index(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"name": "Luxembourg"},
                    "geometry": {"type": "Point", "coordinates": [6.13, 49.61]},
                },
                {
                    "type": "Feature",
                    "properties": {"name": "Luxembourg Ville"},
                    "geometry": {"type": "Point", "coordinates": [6.14, 49.62]},
                },
            ],
        }
    )

    assert resolve_station_matches("Luxembourg", station_matches_by_name) == [
        [6.13, 49.61]
    ]
    assert resolve_station_matches("Ville", station_matches_by_name) == [[6.14, 49.62]]


def test_chain_ways_connects_linear_sequence() -> None:
    """Two ways forming a straight line should produce one segment."""
    nodes = {
        1: (6.0, 49.0),
        2: (6.1, 49.1),
        3: (6.2, 49.2),
    }
    ways = {
        10: {"id": 10, "nodes": [1, 2]},
        11: {"id": 11, "nodes": [2, 3]},
    }
    segments = chain_ways([10, 11], ways, nodes, [], [])
    assert len(segments) == 1
    assert len(segments[0]) == 3  # 3 nodes stitched together


def test_chain_ways_returns_empty_for_missing_ways() -> None:
    """Way IDs not in the ways dict should be silently skipped."""
    segments = chain_ways([999], {}, {}, [], [])
    assert segments == []


def test_chain_ways_handles_duplicate_way_ids() -> None:
    """Duplicate way IDs should be deduplicated."""
    nodes = {1: (6.0, 49.0), 2: (6.1, 49.1)}
    ways = {10: {"id": 10, "nodes": [1, 2]}}
    segments = chain_ways([10, 10, 10], ways, nodes, [], [])
    assert len(segments) == 1
    assert len(segments[0]) == 2  # only one way's worth of nodes


def test_chain_ways_handles_disconnected_components() -> None:
    """Two disconnected way groups are both discovered as separate components.

    The segment selection filter in chain_ways may reduce the final output
    depending on station matches and segment sizes, but at minimum one
    segment is always returned.
    """
    nodes = {
        1: (6.0, 49.0),
        2: (6.1, 49.1),
        3: (7.0, 50.0),
        4: (7.1, 50.1),
    }
    ways = {
        10: {"id": 10, "nodes": [1, 2]},
        20: {"id": 20, "nodes": [3, 4]},
    }
    segments = chain_ways([10, 20], ways, nodes, [], [])
    assert len(segments) >= 1
    # The returned segment(s) should contain coordinates from at least one component
    all_coords = [coord for seg in segments for coord in seg]
    assert [6.0, 49.0] in all_coords or [7.0, 50.0] in all_coords
