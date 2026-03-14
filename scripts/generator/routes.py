from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from generator.route_naming import (
    build_variant_signature,
    iter_station_aliases,
    normalize_text,
    parse_name_endpoints,
    parse_other_tags,
    resolve_endpoints,
)
from generator.route_graph import (
    build_station_indexes,
    chain_ways,
    resolve_station_matches,
)
from generator.route_display import (
    assign_route_offset_slots,
    geometry_from_segments,
    normalize_hex_color,
    offset_segments_for_display,
    resolve_display_color,
    resolve_display_text_color,
)


@dataclass
class RouteCandidate:
    """Best-known geometry and metadata for a deduplicated route relation."""

    score: tuple[int, int, int]  # (point_count, metadata_count, -segment_count)
    feature: dict
    way_ids: set[int] = field(repr=False)
    offset_group_key: tuple[str, ...] = field(repr=False)
    segments: list[list[list[float]]] = field(repr=False)


def write_routes_geojson(
    routes_json_path: Path,
    routes_geojson_path: Path,
    routes_display_geojson_path: Path,
    stations_geojson_path: Path,
    bbox: str,
) -> tuple[int, int]:
    """Convert raw Overpass route relations into canonical and display-ready GeoJSON.

    The export keeps only relations relevant to Luxembourg, deduplicates multiple OSM
    variants of the same logical service, and emits both the unmodified geometry and
    an offset display geometry used for styling parallel colored route lines.

    Returns (feature_count, relation_count).
    """
    data = json.loads(routes_json_path.read_text(encoding="utf-8"))
    stations_geojson = json.loads(stations_geojson_path.read_text(encoding="utf-8"))
    elements = data.get("elements", [])

    nodes = {
        element["id"]: (element["lon"], element["lat"])
        for element in elements
        if element.get("type") == "node" and "lon" in element and "lat" in element
    }
    ways = {
        element["id"]: element for element in elements if element.get("type") == "way"
    }
    relations = [element for element in elements if element.get("type") == "relation"]

    luxembourg_station_names, station_matches_by_name = build_station_indexes(
        stations_geojson, bbox
    )
    station_match_cache: dict[str, list[list[float]]] = {}

    selected_routes: dict[tuple[str, ...], RouteCandidate] = {}

    for relation in relations:
        tags = relation.get("tags", {})
        ref = tags.get("ref", "")
        endpoint_from, endpoint_to = resolve_endpoints(
            tags.get("name", ""),
            ref,
            tags.get("from", "").strip(),
            tags.get("to", "").strip(),
        )

        if (
            normalize_text(endpoint_from) not in luxembourg_station_names
            and normalize_text(endpoint_to) not in luxembourg_station_names
        ):
            continue

        variant_signature = build_variant_signature(
            tags.get("name", ""), ref, endpoint_from, endpoint_to
        )
        # route_key: identity for deduplication; includes variant_signature
        # so branch variants (e.g., "via Wasserbillig" vs "via Trier") are
        # kept as separate routes
        route_key = (
            normalize_text(ref) or normalize_text(tags.get("name", "")),
            tuple(sorted({value for value in (endpoint_from, endpoint_to) if value})),
            variant_signature,
            normalize_text(tags.get("operator", "")),
            normalize_text(tags.get("network", "")),
            normalize_text(tags.get("route", "")),
        )
        # offset_group_key: identity for display offset grouping; excludes
        # variant_signature but includes colour, so visual duplicates share
        # a lateral offset slot while color-distinct services separate
        offset_group_key = (
            normalize_text(ref) or normalize_text(tags.get("name", "")),
            tuple(sorted({value for value in (endpoint_from, endpoint_to) if value})),
            normalize_text(tags.get("operator", "")),
            normalize_text(tags.get("network", "")),
            normalize_text(tags.get("route", "")),
            normalize_text(tags.get("colour", "")),
        )

        members = relation.get("members", [])
        way_ids = [
            member["ref"]
            for member in members
            if member.get("type") == "way"
            and member.get("role", "") not in {"platform", "stop", "station"}
        ]
        way_id_set = set(way_ids)
        from_station_matches = resolve_station_matches(
            endpoint_from,
            station_matches_by_name,
            station_match_cache,
        )
        to_station_matches = resolve_station_matches(
            endpoint_to,
            station_matches_by_name,
            station_match_cache,
        )

        segments = chain_ways(
            way_ids,
            ways,
            nodes,
            from_station_matches,
            to_station_matches,
        )
        if not segments:
            continue

        geometry = geometry_from_segments(segments)

        point_count = sum(len(segment) for segment in segments)
        metadata_count = sum(
            1
            for value in (
                ref,
                tags.get("name", ""),
                tags.get("operator", ""),
                tags.get("colour", ""),
                tags.get("network", ""),
                endpoint_from,
                endpoint_to,
            )
            if value
        )
        # ranking: prefer more geometry points, then richer metadata,
        # then fewer segments (contiguous routes over fragmented ones)
        score = (point_count, metadata_count, -len(segments))

        feature = {
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "ref": ref,
                "name": tags.get("name", ""),
                "route": tags.get("route", ""),
                "operator": tags.get("operator", ""),
                "colour": normalize_hex_color(tags.get("colour", "")),
                "network": tags.get("network", ""),
                "from": endpoint_from,
                "to": endpoint_to,
                "route_offset_slot": 0,
            },
        }

        existing = selected_routes.get(route_key)
        if existing is None or score > existing.score:
            selected_routes[route_key] = RouteCandidate(
                score=score,
                feature=feature,
                way_ids=way_id_set,
                offset_group_key=offset_group_key,
                segments=segments,
            )

    ordered_routes = sorted(
        selected_routes.values(),
        key=lambda candidate: (
            candidate.feature["properties"].get("ref", ""),
            candidate.feature["properties"].get("name", ""),
            candidate.feature["properties"].get("from", ""),
            candidate.feature["properties"].get("to", ""),
        ),
    )
    route_offset_slots = assign_route_offset_slots(
        [candidate.way_ids for candidate in ordered_routes],
        [candidate.offset_group_key for candidate in ordered_routes],
    )

    canonical_features: list[dict] = []
    display_features: list[dict] = []
    for index, candidate in enumerate(ordered_routes):
        feature = candidate.feature
        segments = candidate.segments
        route_offset_slot = route_offset_slots[index]
        feature["properties"]["route_offset_slot"] = route_offset_slot
        feature["properties"]["source_colour"] = feature["properties"].get("colour", "")
        feature["properties"]["display_colour"] = resolve_display_color(
            feature["properties"]
        )
        feature["properties"]["display_text_colour"] = resolve_display_text_color(
            feature["properties"]["display_colour"]
        )

        canonical_features.append(feature)
        display_segments = offset_segments_for_display(segments, route_offset_slot)
        display_features.append(
            {
                "type": "Feature",
                "geometry": geometry_from_segments(display_segments),
                "properties": dict(feature["properties"]),
            }
        )

    routes_geojson = {"type": "FeatureCollection", "features": canonical_features}
    routes_geojson_path.write_text(json.dumps(routes_geojson), encoding="utf-8")

    routes_display_geojson = {"type": "FeatureCollection", "features": display_features}
    routes_display_geojson_path.write_text(
        json.dumps(routes_display_geojson), encoding="utf-8"
    )
    return len(canonical_features), len(relations)
