from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

NORMALIZED_PUBLIC_LAYERS = frozenset(
    {
        "rail_tracks",
        "rail_tracks_lifecycle",
        "rail_stops",
        "rail_routes",
        "rail_routes_display",
        "rail_crossings",
        "rail_platforms",
        "rail_platform_labels",
        "rail_infrastructure_points",
        "rail_areas",
        "rail_tunnel_entrances",
    }
)

MODE_BY_RAILWAY = {
    "rail": "heavy_rail",
    "preserved": "heavy_rail",
    "light_rail": "light_rail",
    "tram": "tram",
    "subway": "metro",
    "narrow_gauge": "narrow_gauge",
    "monorail": "monorail",
    "funicular": "funicular",
    "miniature": "miniature",
}

MODE_BY_ROUTE = {
    "train": "heavy_rail",
    "railway": "heavy_rail",
    "light_rail": "light_rail",
    "tram": "tram",
    "subway": "metro",
    "metro": "metro",
    "monorail": "monorail",
    "funicular": "funicular",
}

MODE_BY_STOP = {
    "tram_stop": "tram",
    "subway_entrance": "metro",
}

MODE_BY_STATION_TAG = {
    "train": "heavy_rail",
    "rail": "heavy_rail",
    "railway": "heavy_rail",
    "light_rail": "light_rail",
    "tram": "tram",
    "subway": "metro",
    "metro": "metro",
    "monorail": "monorail",
    "funicular": "funicular",
}

LIFECYCLE_NAMESPACES = (
    "construction",
    "proposed",
    "disused",
    "abandoned",
    "razed",
)

INFRA_TYPES = frozenset(
    {
        "signal",
        "switch",
        "buffer_stop",
        "derail",
        "railway_crossing",
        "milestone",
        "turntable",
        "owner_change",
    }
)


def normalize_geojson_file(path: Path, layer_name: str) -> None:
    collection = json.loads(path.read_text(encoding="utf-8"))
    normalized = normalize_feature_collection(collection, layer_name)
    path.write_text(json.dumps(normalized), encoding="utf-8")


def normalize_feature_collection(
    collection: dict[str, Any], layer_name: str
) -> dict[str, Any]:
    if layer_name not in NORMALIZED_PUBLIC_LAYERS:
        raise ValueError(f"Unknown normalized rail layer: {layer_name}")

    normalized = copy.deepcopy(collection)
    features = normalized.get("features", [])
    if not isinstance(features, list):
        return normalized

    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            continue
        feature["properties"] = normalize_properties(properties, layer_name)

    return normalized


def normalize_properties(properties: dict[str, Any], layer_name: str) -> dict[str, Any]:
    normalized = {key: value for key, value in properties.items() if value is not None}
    railway = _railway_value(properties)
    osm_route = _string_value(properties.get("route"))

    if railway is not None:
        normalized["osm_railway"] = railway
    if osm_route is not None:
        normalized["osm_route"] = osm_route

    mode = _resolve_mode(railway, osm_route)
    if mode is not None:
        normalized["mode"] = mode

    lifecycle_state = _resolve_lifecycle_state(properties, layer_name)
    if lifecycle_state is not None:
        normalized["lifecycle_state"] = lifecycle_state

    if layer_name in {"rail_tracks", "rail_tracks_lifecycle"}:
        normalized["track_role"] = _resolve_track_role(properties)
        normalized["structure"] = _resolve_structure(properties)
        normalized["is_electrified"] = _truthy(properties.get("electrified"))
        normalized["is_highspeed"] = _truthy(properties.get("highspeed"))
        normalized["is_preserved"] = _truthy(_preserved_value(properties))

    if layer_name == "rail_stops":
        normalized["stop_type"] = railway
        stop_mode = _resolve_stop_mode(properties, railway)
        if stop_mode is not None:
            normalized["mode"] = stop_mode
        elif "mode" not in normalized and railway in {"station", "halt", "border"}:
            normalized["mode"] = "heavy_rail"

    if layer_name == "rail_crossings":
        normalized["crossing_type"] = railway
        normalized["has_barrier"] = _truthy(properties.get("crossing:barrier"))
        normalized["has_bell"] = _truthy(properties.get("crossing:bell"))
        normalized["has_light"] = _truthy(properties.get("crossing:light"))
        normalized["is_supervised"] = _truthy(properties.get("supervised"))

    if layer_name == "rail_infrastructure_points":
        normalized["infra_type"] = railway

    if layer_name == "rail_areas":
        normalized["area_type"] = railway or _string_value(properties.get("landuse"))

    if layer_name == "rail_tunnel_entrances":
        normalized["infra_type"] = "tunnel_entrance"
        normalized["structure"] = "tunnel"

    return normalized


def _railway_value(properties: dict[str, Any]) -> str | None:
    railway = _string_value(properties.get("railway"))
    if railway is not None:
        if railway in LIFECYCLE_NAMESPACES:
            lifecycle_railway = _lifecycle_railway_value(properties, railway)
            if lifecycle_railway is not None:
                return lifecycle_railway
        return railway

    for state in LIFECYCLE_NAMESPACES:
        lifecycle_value = _lifecycle_railway_value(properties, state)
        if lifecycle_value is not None:
            return lifecycle_value

    return None


def _lifecycle_railway_value(properties: dict[str, Any], state: str) -> str | None:
    lifecycle_value = first_non_empty(
        properties.get(f"{state}:railway"),
        properties.get(f"{state}_railway"),
    )
    if lifecycle_value is not None:
        return lifecycle_value

    legacy_value = _string_value(properties.get(state))
    if legacy_value in MODE_BY_RAILWAY:
        return legacy_value

    return None


def _resolve_mode(railway: str | None, route: str | None) -> str | None:
    if railway in MODE_BY_RAILWAY:
        return MODE_BY_RAILWAY[railway]
    if route in MODE_BY_ROUTE:
        return MODE_BY_ROUTE[route]
    return None


def _resolve_stop_mode(properties: dict[str, Any], railway: str | None) -> str | None:
    if railway in MODE_BY_STOP:
        return MODE_BY_STOP[railway]

    station_value = first_non_empty(
        properties.get("station"),
        properties.get("railway:station"),
    )
    if station_value in MODE_BY_STATION_TAG:
        return MODE_BY_STATION_TAG[station_value]

    for tag_name, mode in (
        ("subway", "metro"),
        ("tram", "tram"),
        ("light_rail", "light_rail"),
        ("monorail", "monorail"),
        ("funicular", "funicular"),
        ("train", "heavy_rail"),
    ):
        if _truthy(properties.get(tag_name)):
            return mode

    return None


def _resolve_lifecycle_state(properties: dict[str, Any], layer_name: str) -> str:
    railway = _string_value(properties.get("railway"))
    if railway in LIFECYCLE_NAMESPACES:
        return railway
    if railway == "preserved" or _truthy(_preserved_value(properties)):
        return "preserved"
    if layer_name == "rail_tracks":
        return "active"
    for state in LIFECYCLE_NAMESPACES:
        if _lifecycle_railway_value(properties, state) in MODE_BY_RAILWAY:
            return state
    return "active"


def _resolve_track_role(properties: dict[str, Any]) -> str:
    service = _string_value(properties.get("service"))
    if service is not None:
        return service
    usage = _string_value(properties.get("usage"))
    if usage is not None:
        return usage
    return "main"


def _resolve_structure(properties: dict[str, Any]) -> str:
    if _truthy(properties.get("tunnel")):
        return "tunnel"
    if _truthy(properties.get("bridge")):
        return "bridge"
    if _truthy(properties.get("cutting")):
        return "cutting"
    if _truthy(properties.get("embankment")):
        return "embankment"
    return "surface"


def _preserved_value(properties: dict[str, Any]) -> Any:
    return first_non_empty(
        properties.get("railway:preserved"),
        properties.get("railway_preserved"),
    )


def _truthy(value: Any) -> bool:
    normalized = _string_value(value)
    if normalized is None:
        return False
    return normalized not in {"no", "false", "0", "none"}


def first_non_empty(*values: Any) -> str | None:
    for value in values:
        string_value = _string_value(value)
        if string_value is not None:
            return string_value

    return None


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return str(value)
