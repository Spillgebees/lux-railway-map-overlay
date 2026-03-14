from __future__ import annotations

import re

# squared distance threshold (~50m at Luxembourg latitude) for treating
# a stop-position label as a duplicate of a nearby platform-area label
_PLATFORM_PROXIMITY_THRESHOLD_SQ_DEG = 0.0005**2


def build_platform_reference_feature_collection(
    platform_data: dict[str, object],
    station_data: dict[str, object],
) -> tuple[list[dict[str, object]], int, int]:
    """Combine polygon platform labels with stop-position fallbacks.

    OSM data is inconsistent across operators: some stations encode usable platform
    refs on platform areas, others only on stop positions. This collector prefers
    platform-area labels and only keeps stop positions that add missing information.
    """
    platform_features: list[dict[str, object]] = []
    stop_position_features: list[dict[str, object]] = []

    for feature in platform_data.get("features", []):
        platform_ref_feature = build_platform_reference_feature(
            feature,
            source_layer="railway_platforms",
            require_stop_position=False,
        )
        if platform_ref_feature is not None:
            platform_features.append(platform_ref_feature)

    for feature in station_data.get("features", []):
        platform_ref_feature = build_platform_reference_feature(
            feature,
            source_layer="railway_stations",
            require_stop_position=True,
        )
        if platform_ref_feature is not None:
            stop_position_features.append(platform_ref_feature)

    features = list(platform_features)
    for feature in stop_position_features:
        if has_matching_platform_reference(platform_features, feature):
            continue
        features.append(feature)

    platform_count = sum(
        1
        for feature in features
        if feature.get("properties", {}).get("source_layer") == "railway_platforms"
    )
    stop_position_count = len(features) - platform_count
    return features, platform_count, stop_position_count


def build_platform_reference_feature(
    feature: dict[str, object],
    *,
    source_layer: str,
    require_stop_position: bool,
) -> dict[str, object] | None:
    """Extract the best available platform label from one raw OSM feature."""
    properties = feature.get("properties")
    geometry = feature.get("geometry")

    if not isinstance(properties, dict) or not isinstance(geometry, dict):
        return None

    tags = parse_other_tags(properties.get("other_tags"))
    public_transport = first_non_empty(
        properties.get("public_transport"),
        tags.get("public_transport"),
    )
    if require_stop_position and public_transport != "stop_position":
        return None

    ref = first_non_empty(properties.get("ref"), tags.get("ref"))
    local_ref = first_non_empty(
        properties.get("local_ref"),
        tags.get("local_ref"),
    )
    ref_ifopt = first_non_empty(
        properties.get("ref_IFOPT"),
        properties.get("ref:IFOPT"),
        tags.get("ref:IFOPT"),
    )
    ref_ifopt_description = first_non_empty(
        properties.get("ref_IFOPT_description"),
        properties.get("ref:IFOPT:description"),
        tags.get("ref:IFOPT:description"),
    )
    description = first_non_empty(
        properties.get("description"),
        tags.get("description"),
    )
    route_ref = first_non_empty(
        properties.get("route_ref"),
        tags.get("route_ref"),
    )
    extracted_name_label = extract_platform_label(properties.get("name"))
    extracted_ref_ifopt_label = extract_platform_label(ref_ifopt_description)
    extracted_description_label = extract_platform_label(description)

    # platform_ref_label: short identifier (e.g., "1A", "Quai 3")
    # platform_name_label: descriptive name extracted from feature name
    # platform_label_short: same as ref_label (used for compact display)
    # platform_label: best available label (name preferred over ref)
    platform_ref_label = first_non_empty(
        local_ref,
        ref,
        extracted_ref_ifopt_label,
        extracted_description_label,
    )
    platform_label_short = platform_ref_label
    platform_name_label = extracted_name_label
    platform_label = first_non_empty(
        platform_name_label,
        platform_ref_label,
    )

    if platform_label is None:
        return None

    point_geometry = point_geometry_for_feature(geometry)
    if point_geometry is None:
        return None

    return {
        "type": "Feature",
        "properties": {
            "source_layer": source_layer,
            "source_id": first_non_empty(
                properties.get("osm_id"),
                properties.get("osm_way_id"),
            ),
            "name": properties.get("name"),
            "railway": properties.get("railway"),
            "public_transport": public_transport,
            "platform_label": platform_label,
            "platform_label_short": platform_label_short,
            "platform_name_label": platform_name_label,
            "platform_ref_label": platform_ref_label,
            "ref": ref,
            "local_ref": local_ref,
            "ref_ifopt": ref_ifopt,
            "ref_ifopt_description": ref_ifopt_description,
            "description": description,
            "route_ref": route_ref,
        },
        "geometry": point_geometry,
    }


def point_geometry_for_feature(
    geometry: dict[str, object],
) -> dict[str, object] | None:
    """Collapse arbitrary feature geometry to a representative label point."""
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if geometry_type == "Point" and isinstance(coordinates, list):
        return {"type": "Point", "coordinates": coordinates}

    collected: list[tuple[float, float]] = []
    collect_positions(coordinates, collected)
    if not collected:
        return None

    longitudes = [position[0] for position in collected]
    latitudes = [position[1] for position in collected]
    return {
        "type": "Point",
        "coordinates": [
            (min(longitudes) + max(longitudes)) / 2,
            (min(latitudes) + max(latitudes)) / 2,
        ],
    }


def has_matching_platform_reference(
    platform_features: list[dict[str, object]],
    candidate_feature: dict[str, object],
) -> bool:
    """Treat a stop-position label as duplicate when it is both nearby and names the
    same platform as an already accepted polygon-derived label.
    """
    candidate_properties = candidate_feature.get("properties")
    candidate_geometry = candidate_feature.get("geometry")

    if not isinstance(candidate_properties, dict) or not isinstance(
        candidate_geometry, dict
    ):
        return False

    candidate_coordinates = candidate_geometry.get("coordinates")
    if (
        not isinstance(candidate_coordinates, list)
        or len(candidate_coordinates) < 2
        or not isinstance(candidate_coordinates[0], (int, float))
        or not isinstance(candidate_coordinates[1], (int, float))
    ):
        return False

    candidate_ref = first_non_empty(
        candidate_properties.get("platform_ref_label"),
        candidate_properties.get("platform_label_short"),
        candidate_properties.get("ref"),
        candidate_properties.get("local_ref"),
    )
    candidate_name = first_non_empty(
        candidate_properties.get("platform_name_label"),
        candidate_properties.get("name"),
    )

    for platform_feature in platform_features:
        platform_properties = platform_feature.get("properties")
        platform_geometry = platform_feature.get("geometry")

        if not isinstance(platform_properties, dict) or not isinstance(
            platform_geometry, dict
        ):
            continue

        platform_coordinates = platform_geometry.get("coordinates")
        if (
            not isinstance(platform_coordinates, list)
            or len(platform_coordinates) < 2
            or not isinstance(platform_coordinates[0], (int, float))
            or not isinstance(platform_coordinates[1], (int, float))
        ):
            continue

        platform_ref = first_non_empty(
            platform_properties.get("platform_ref_label"),
            platform_properties.get("platform_label_short"),
            platform_properties.get("ref"),
            platform_properties.get("local_ref"),
        )
        platform_name = first_non_empty(
            platform_properties.get("platform_name_label"),
            platform_properties.get("name"),
        )

        has_matching_ref = candidate_ref is not None and candidate_ref == platform_ref
        has_matching_name = (
            candidate_name is not None and candidate_name == platform_name
        )
        if not has_matching_ref and not has_matching_name:
            continue

        longitude_delta = float(platform_coordinates[0]) - float(
            candidate_coordinates[0]
        )
        latitude_delta = float(platform_coordinates[1]) - float(
            candidate_coordinates[1]
        )
        if (longitude_delta * longitude_delta) + (
            latitude_delta * latitude_delta
        ) <= _PLATFORM_PROXIMITY_THRESHOLD_SQ_DEG:
            return True

    return False


def collect_positions(
    coordinates: object,
    collected: list[tuple[float, float]],
) -> None:
    if (
        isinstance(coordinates, list)
        and len(coordinates) >= 2
        and isinstance(coordinates[0], (int, float))
        and isinstance(coordinates[1], (int, float))
    ):
        collected.append((float(coordinates[0]), float(coordinates[1])))
        return

    if isinstance(coordinates, list):
        for item in coordinates:
            collect_positions(item, collected)


def extract_platform_label(value: object) -> str | None:
    """Find embedded platform refs in free-form names and descriptions."""
    if not isinstance(value, str):
        return None

    compact = re.sub(r"\s+", " ", value).strip()
    if compact == "":
        return None

    patterns = (
        r"\b(?:Quai|Gleis|Bahnsteig|Steig|Platform|Track|Voie)s?\s+[A-Za-z0-9][A-Za-z0-9 +/;:-]*",
        r"\b[A-Z]?\d+(?:\s*[+/;-]\s*[A-Z]?\d+)+\b",
    )
    for pattern in patterns:
        match = re.search(pattern, compact, flags=re.IGNORECASE)
        if match is not None:
            return match.group(0).strip()

    return None


def parse_other_tags(value: object) -> dict[str, str]:
    """Parse GDAL's serialized other_tags payload into a normal dictionary."""
    if not isinstance(value, str) or value == "":
        return {}

    tags: dict[str, str] = {}
    for key, parsed_value in re.findall(
        r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"',
        value,
    ):
        tags[unescape_other_tag_value(key)] = unescape_other_tag_value(parsed_value)
    return tags


def unescape_other_tag_value(value: str) -> str:
    return value.replace(r"\\", "\\").replace(r"\"", '"').strip()


def first_non_empty(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped != "":
                return stripped
    return None
