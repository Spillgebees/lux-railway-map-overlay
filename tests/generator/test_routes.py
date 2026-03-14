from __future__ import annotations

import json

from generator.route_naming import (
    build_variant_signature,
    iter_station_aliases,
    normalize_text,
    parse_name_endpoints,
    resolve_endpoints,
)
from generator.routes import write_routes_geojson


def test_normalize_text_strips_accents_and_punctuation() -> None:
    assert (
        normalize_text("  Gare d'Éttelbrück / Quai-4  ") == "gare d ettelbruck quai 4"
    )


def test_parse_name_endpoints_removes_ref_prefix() -> None:
    assert parse_name_endpoints("RE 1: Luxembourg - Ettelbruck", "RE 1") == (
        "Luxembourg",
        "Ettelbruck",
    )


def test_resolve_endpoints_prefers_parsed_name_when_tags_are_missing() -> None:
    assert resolve_endpoints("RB 12: Wiltz -> Luxembourg", "RB 12", "", "") == (
        "Wiltz",
        "Luxembourg",
    )


def test_build_variant_signature_removes_endpoints_and_ref() -> None:
    assert (
        build_variant_signature(
            "RB 12: Wiltz - Luxembourg via Ettelbruck",
            "RB 12",
            "Wiltz",
            "Luxembourg",
        )
        == "via ettelbruck"
    )


def test_iter_station_aliases_deduplicates_normalized_names() -> None:
    aliases = iter_station_aliases(
        {
            "properties": {
                "name": "Luxembourg",
                "uic_name": "LUXEMBOURG",
                "other_tags": '"alt_name"=>"Luxembourg;luxembourg",'
                + '"name:fr"=>"Luxembourg"',
            }
        }
    )

    assert aliases == ["Luxembourg"]


def test_write_routes_geojson_deduplicates_relations_and_keeps_best_geometry(
    tmp_path,
) -> None:
    routes_json_path = tmp_path / "overpass_routes.json"
    stations_geojson_path = tmp_path / "railway_stations.geojson"
    routes_geojson_path = tmp_path / "railway_routes.geojson"
    routes_display_geojson_path = tmp_path / "railway_routes_display.geojson"

    routes_json_path.write_text(
        json.dumps(
            {
                "elements": [
                    {"type": "node", "id": 1, "lon": 6.0, "lat": 49.6},
                    {"type": "node", "id": 2, "lon": 6.1, "lat": 49.7},
                    {"type": "node", "id": 3, "lon": 6.2, "lat": 49.8},
                    {"type": "way", "id": 10, "nodes": [1, 2]},
                    {"type": "way", "id": 11, "nodes": [2, 3]},
                    {
                        "type": "relation",
                        "id": 100,
                        "members": [
                            {"type": "way", "ref": 10, "role": ""},
                            {"type": "way", "ref": 11, "role": ""},
                        ],
                        "tags": {
                            "route": "train",
                            "ref": "RE 1",
                            "name": "RE 1: Luxembourg - Ettelbruck",
                            "operator": "CFL",
                            "network": "RGTR",
                            "colour": "#ff0000",
                        },
                    },
                    {
                        "type": "relation",
                        "id": 101,
                        "members": [
                            {"type": "way", "ref": 10, "role": ""},
                        ],
                        "tags": {
                            "route": "train",
                            "ref": "RE 1",
                            "name": "RE 1: Luxembourg - Ettelbruck",
                            "operator": "CFL",
                            "network": "RGTR",
                            "colour": "#ff0000",
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    stations_geojson_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "Luxembourg"},
                        "geometry": {"type": "Point", "coordinates": [6.0, 49.6]},
                    },
                    {
                        "type": "Feature",
                        "properties": {"name": "Ettelbruck"},
                        "geometry": {"type": "Point", "coordinates": [6.2, 49.8]},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    feature_count, relation_count = write_routes_geojson(
        routes_json_path,
        routes_geojson_path,
        routes_display_geojson_path,
        stations_geojson_path,
        "49.44,5.73,50.18,6.53",
    )

    canonical = json.loads(routes_geojson_path.read_text(encoding="utf-8"))
    display = json.loads(routes_display_geojson_path.read_text(encoding="utf-8"))

    assert feature_count == 1
    assert relation_count == 2
    assert len(canonical["features"]) == 1
    assert len(display["features"]) == 1

    feature = canonical["features"][0]
    assert feature["geometry"]["type"] == "LineString"
    assert len(feature["geometry"]["coordinates"]) == 3
    assert feature["properties"] == {
        "ref": "RE 1",
        "name": "RE 1: Luxembourg - Ettelbruck",
        "route": "train",
        "operator": "CFL",
        "colour": "#FF0000",
        "network": "RGTR",
        "from": "Luxembourg",
        "to": "Ettelbruck",
        "route_offset_slot": -0.5,
        "source_colour": "#FF0000",
        "display_colour": "#FF0000",
        "display_text_colour": "#FF0000",
    }

    assert display["features"][0]["properties"] == feature["properties"]
