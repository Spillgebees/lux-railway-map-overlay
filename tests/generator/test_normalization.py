from __future__ import annotations

from generator.normalization import normalize_feature_collection


def test_normalize_feature_collection_maps_track_properties() -> None:
    # arrange
    collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[6.0, 49.6], [6.1, 49.7]],
                },
                "properties": {
                    "railway": "rail",
                    "usage": "main",
                    "service": "yard",
                    "bridge": "yes",
                    "tunnel": "no",
                    "electrified": "contact_line",
                    "abandoned": None,
                },
            }
        ],
    }

    # act
    normalized = normalize_feature_collection(collection, "rail_tracks")

    # assert
    properties = normalized["features"][0]["properties"]
    assert properties["mode"] == "heavy_rail"
    assert properties["lifecycle_state"] == "active"
    assert properties["track_role"] == "yard"
    assert properties["structure"] == "bridge"
    assert properties["is_electrified"] is True
    assert properties["osm_railway"] == "rail"


def test_normalize_feature_collection_keeps_active_track_active_when_lifecycle_namespace_exists() -> (
    None
):
    # arrange
    collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[6.0, 49.6], [6.1, 49.7]],
                },
                "properties": {
                    "railway": "rail",
                    "disused_railway": "station",
                    "abandoned_railway": "platform",
                    "construction_railway": "turntable",
                },
            }
        ],
    }

    # act
    normalized = normalize_feature_collection(collection, "rail_tracks")

    # assert
    properties = normalized["features"][0]["properties"]
    assert properties["mode"] == "heavy_rail"
    assert properties["lifecycle_state"] == "active"


def test_normalize_feature_collection_drops_null_fields_that_style_checks_with_has() -> (
    None
):
    # arrange
    collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[6.0, 49.6], [6.1, 49.7]],
                },
                "properties": {
                    "railway": "rail",
                    "service": None,
                    "usage": None,
                    "name": "Main line",
                },
            }
        ],
    }

    # act
    normalized = normalize_feature_collection(collection, "rail_tracks")

    # assert
    properties = normalized["features"][0]["properties"]
    assert "service" not in properties
    assert "usage" not in properties
    assert properties["name"] == "Main line"
    assert properties["mode"] == "heavy_rail"


def test_normalize_feature_collection_uses_lifecycle_namespace_tags() -> None:
    # arrange
    collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[6.0, 49.6], [6.1, 49.7]],
                },
                "properties": {
                    "railway": None,
                    "construction_railway": "tram",
                    "construction": "station",
                },
            }
        ],
    }

    # act
    normalized = normalize_feature_collection(collection, "rail_tracks_lifecycle")

    # assert
    properties = normalized["features"][0]["properties"]
    assert properties["mode"] == "tram"
    assert properties["lifecycle_state"] == "construction"
    assert properties["osm_railway"] == "tram"


def test_normalize_feature_collection_maps_ogr_preserved_field_name() -> None:
    # arrange
    collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[6.0, 49.6], [6.1, 49.7]],
                },
                "properties": {
                    "railway": "rail",
                    "railway_preserved": "yes",
                },
            }
        ],
    }

    # act
    normalized = normalize_feature_collection(collection, "rail_tracks")

    # assert
    properties = normalized["features"][0]["properties"]
    assert properties["mode"] == "heavy_rail"
    assert properties["lifecycle_state"] == "preserved"
    assert properties["is_preserved"] is True


def test_normalize_feature_collection_maps_stop_crossing_and_infra_types() -> None:
    # arrange
    stop_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [6.0, 49.6]},
                "properties": {"railway": "tram_stop"},
            }
        ],
    }
    crossing_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [6.0, 49.6]},
                "properties": {
                    "railway": "tram_level_crossing",
                    "crossing:bell": "yes",
                },
            }
        ],
    }
    infra_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [6.0, 49.6]},
                "properties": {"railway": "signal"},
            }
        ],
    }

    # act
    stop = normalize_feature_collection(stop_collection, "rail_stops")
    crossing = normalize_feature_collection(crossing_collection, "rail_crossings")
    infra = normalize_feature_collection(infra_collection, "rail_infrastructure_points")

    # assert
    assert stop["features"][0]["properties"]["stop_type"] == "tram_stop"
    assert stop["features"][0]["properties"]["mode"] == "tram"
    assert (
        crossing["features"][0]["properties"]["crossing_type"] == "tram_level_crossing"
    )
    assert crossing["features"][0]["properties"]["has_bell"] is True
    assert infra["features"][0]["properties"]["infra_type"] == "signal"


def test_normalize_feature_collection_defaults_station_and_halt_stops_to_heavy_rail() -> (
    None
):
    # arrange
    collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [6.0, 49.6]},
                "properties": {"railway": "station"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [6.1, 49.7]},
                "properties": {"railway": "halt"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [6.2, 49.8]},
                "properties": {"railway": "station", "station": "subway"},
            },
        ],
    }

    # act
    normalized = normalize_feature_collection(collection, "rail_stops")

    # assert
    assert normalized["features"][0]["properties"]["mode"] == "heavy_rail"
    assert normalized["features"][1]["properties"]["mode"] == "heavy_rail"
    assert normalized["features"][2]["properties"]["mode"] == "metro"


def test_normalize_feature_collection_defaults_border_stops_to_heavy_rail() -> None:
    # arrange
    collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [6.0, 49.6]},
                "properties": {"railway": "border"},
            }
        ],
    }

    # act
    normalized = normalize_feature_collection(collection, "rail_stops")

    # assert
    properties = normalized["features"][0]["properties"]
    assert properties["stop_type"] == "border"
    assert properties["mode"] == "heavy_rail"


def test_normalize_feature_collection_uses_lifecycle_mode_when_railway_is_lifecycle_sentinel() -> (
    None
):
    # arrange
    collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[6.0, 49.6], [6.1, 49.7]],
                },
                "properties": {"railway": "construction", "construction": "rail"},
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[6.2, 49.8], [6.3, 49.9]],
                },
                "properties": {"railway": "proposed", "proposed": "tram"},
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[6.4, 49.6], [6.5, 49.7]],
                },
                "properties": {
                    "railway": "abandoned",
                    "abandoned:railway": "narrow_gauge",
                },
            },
        ],
    }

    # act
    normalized = normalize_feature_collection(collection, "rail_tracks_lifecycle")

    # assert
    assert normalized["features"][0]["properties"]["mode"] == "heavy_rail"
    assert normalized["features"][0]["properties"]["lifecycle_state"] == "construction"
    assert normalized["features"][1]["properties"]["mode"] == "tram"
    assert normalized["features"][1]["properties"]["lifecycle_state"] == "proposed"
    assert normalized["features"][2]["properties"]["mode"] == "narrow_gauge"
    assert normalized["features"][2]["properties"]["lifecycle_state"] == "abandoned"


def test_normalize_feature_collection_rejects_unknown_layer() -> None:
    # arrange
    collection = {"type": "FeatureCollection", "features": []}

    # act / assert
    try:
        normalize_feature_collection(collection, "rail_unknown")
    except ValueError as error:
        assert "rail_unknown" in str(error)
    else:
        raise AssertionError("expected ValueError")
