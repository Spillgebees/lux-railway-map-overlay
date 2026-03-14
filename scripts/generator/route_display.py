from __future__ import annotations

import math
import re

from shapely.geometry import GeometryCollection, LineString, MultiLineString

FALLBACK_DISPLAY_ROUTE_COLOR = "#5B6675"
WEB_MERCATOR_RADIUS = 6378137.0
WEB_MERCATOR_MAX_LATITUDE = 85.0511287798066
# lateral offset in Web Mercator meters between adjacent route slots;
# tuned for legibility at z8-z14 where parallel services are visible
ROUTE_DISPLAY_OFFSET_METERS_PER_SLOT = 8.0

# empirical thresholds tuned for Luxembourg's railway network;
# avoids false adjacency from incidental shared fragments
_MIN_SHARED_WAYS_FOR_OVERLAP = 3
_MIN_OVERLAP_FRACTION = 0.05


def normalize_hex_color(value: str) -> str:
    """Accept only canonical six-digit hex colors for downstream style output."""
    normalized_value = value.strip()
    if not normalized_value:
        return ""

    if re.fullmatch(r"#[0-9a-fA-F]{6}", normalized_value):
        return normalized_value.upper()

    return ""


def resolve_display_color(properties: dict[str, str]) -> str:
    source_color = normalize_hex_color(properties.get("colour", ""))
    if source_color:
        return source_color

    return FALLBACK_DISPLAY_ROUTE_COLOR


def resolve_display_text_color(display_color: str) -> str:
    """Choose a readable label color for route shields and line labels."""
    color_match = re.fullmatch(r"#([0-9A-Fa-f]{6})", display_color)
    if color_match is None:
        return "#0F172A"

    red = int(color_match.group(1)[0:2], 16)
    green = int(color_match.group(1)[2:4], 16)
    blue = int(color_match.group(1)[4:6], 16)
    perceived_brightness = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    # ITU-R BT.601 luma; 0.62 threshold is slightly above midpoint to
    # favor dark text, producing better contrast on white halo backgrounds
    if perceived_brightness >= 0.62:
        return "#0F172A"

    return display_color


def geometry_from_segments(segments: list[list[list[float]]]) -> dict:
    if len(segments) == 1:
        return {"type": "LineString", "coordinates": segments[0]}
    return {"type": "MultiLineString", "coordinates": segments}


def _project_coordinate_to_web_mercator(coordinate: list[float]) -> tuple[float, float]:
    lon, lat = coordinate
    clamped_lat = max(min(lat, WEB_MERCATOR_MAX_LATITUDE), -WEB_MERCATOR_MAX_LATITUDE)
    x = WEB_MERCATOR_RADIUS * math.radians(lon)
    y = WEB_MERCATOR_RADIUS * math.log(
        math.tan((math.pi / 4) + (math.radians(clamped_lat) / 2))
    )
    return x, y


def _unproject_coordinate_from_web_mercator(
    coordinate: tuple[float, float],
) -> list[float]:
    x, y = coordinate
    lon = math.degrees(x / WEB_MERCATOR_RADIUS)
    lat = math.degrees(
        (2 * math.atan(math.exp(y / WEB_MERCATOR_RADIUS))) - (math.pi / 2)
    )
    return [lon, lat]


def _normalize_line_direction(
    reference_coords: list[list[float]], candidate_coords: list[list[float]]
) -> list[list[float]]:
    if len(reference_coords) < 2 or len(candidate_coords) < 2:
        return candidate_coords

    forward_score = math.hypot(
        candidate_coords[0][0] - reference_coords[0][0],
        candidate_coords[0][1] - reference_coords[0][1],
    ) + math.hypot(
        candidate_coords[-1][0] - reference_coords[-1][0],
        candidate_coords[-1][1] - reference_coords[-1][1],
    )
    reverse_score = math.hypot(
        candidate_coords[0][0] - reference_coords[-1][0],
        candidate_coords[0][1] - reference_coords[-1][1],
    ) + math.hypot(
        candidate_coords[-1][0] - reference_coords[0][0],
        candidate_coords[-1][1] - reference_coords[0][1],
    )
    if reverse_score < forward_score:
        return list(reversed(candidate_coords))

    return candidate_coords


def _canonicalize_segment_direction(coords: list[list[float]]) -> list[list[float]]:
    if len(coords) < 2:
        return coords

    start = coords[0]
    end = coords[-1]
    if (end[0], end[1]) < (start[0], start[1]):
        return list(reversed(coords))

    return coords


def _offset_segment_for_display(
    coords: list[list[float]], offset_meters: float
) -> list[list[list[float]]]:
    """Offset one route segment in projected space while keeping only meaningful
    output fragments when the geometry splits during offsetting.
    """
    if len(coords) < 2 or abs(offset_meters) < 1e-9:
        return [coords]

    canonical_coords = _canonicalize_segment_direction(coords)
    projected_coords = [
        _project_coordinate_to_web_mercator(coordinate)
        for coordinate in canonical_coords
    ]
    source_line = LineString(projected_coords)
    if source_line.length < 1e-6:
        return [coords]

    offset_line = source_line.offset_curve(offset_meters, join_style=1, quad_segs=8)
    if offset_line.is_empty:
        return [coords]

    line_geometries: list[LineString] = []
    if isinstance(offset_line, LineString):
        line_geometries = [offset_line]
    elif isinstance(offset_line, MultiLineString):
        line_geometries = list(offset_line.geoms)
    elif isinstance(offset_line, GeometryCollection):
        line_geometries = [
            geometry
            for geometry in offset_line.geoms
            if isinstance(geometry, LineString)
        ]

    if not line_geometries:
        return [coords]

    longest_length = max(geometry.length for geometry in line_geometries)
    minimum_length = max(8.0, longest_length * 0.1)
    display_segments: list[list[list[float]]] = []

    for geometry in sorted(line_geometries, key=lambda item: item.length, reverse=True):
        if geometry.length < minimum_length:
            continue

        offset_coords = [
            _unproject_coordinate_from_web_mercator(coordinate)
            for coordinate in geometry.coords
        ]
        if len(offset_coords) < 2:
            continue

        display_segments.append(_normalize_line_direction(coords, offset_coords))

    return display_segments or [coords]


def offset_segments_for_display(
    segments: list[list[list[float]]], route_offset_slot: float
) -> list[list[list[float]]]:
    offset_meters = route_offset_slot * ROUTE_DISPLAY_OFFSET_METERS_PER_SLOT
    if abs(offset_meters) < 1e-9:
        return segments

    display_segments: list[list[list[float]]] = []
    for segment in segments:
        display_segments.extend(_offset_segment_for_display(segment, offset_meters))

    return display_segments or segments


# odd count: center slot is 0, then alternates -1, +1, -2, +2, ...
# even count: straddles center at -0.5, +0.5, -1.5, +1.5, ...
def _build_slot_sequence(size: int) -> list[float]:
    if size <= 0:
        return []

    if size % 2 == 1:
        slots: list[float] = [0.0]
        step = 1.0
        while len(slots) < size:
            slots.append(-step)
            if len(slots) < size:
                slots.append(step)
            step += 1.0
        return slots

    slots = []
    step = 0.5
    while len(slots) < size:
        slots.append(-step)
        if len(slots) < size:
            slots.append(step)
        step += 1.0
    return slots


def assign_route_offset_slots(
    route_way_sets: list[set[int]], offset_group_keys: list[tuple[str, ...]]
) -> list[float]:
    """Assign stable lateral offsets so overlapping route services remain legible.

    Routes that are effectively the same visual service share an offset group. The
    remaining groups are colored with a small graph-coloring pass based on shared way
    membership so parallel services separate only when they materially overlap.
    """
    offset_group_indices: dict[tuple[str, ...], int] = {}
    offset_group_way_sets: list[set[int]] = []

    for route_index, offset_group_key in enumerate(offset_group_keys):
        offset_group_index = offset_group_indices.get(offset_group_key)
        if offset_group_index is None:
            offset_group_index = len(offset_group_way_sets)
            offset_group_indices[offset_group_key] = offset_group_index
            offset_group_way_sets.append(set(route_way_sets[route_index]))
            continue

        offset_group_way_sets[offset_group_index].update(route_way_sets[route_index])

    adjacency: list[set[int]] = [set() for _ in offset_group_way_sets]

    for left_index, left_way_ids in enumerate(offset_group_way_sets):
        if not left_way_ids:
            continue

        for right_index in range(left_index + 1, len(offset_group_way_sets)):
            right_way_ids = offset_group_way_sets[right_index]
            if not right_way_ids:
                continue

            shared_way_ids = left_way_ids & right_way_ids
            if len(shared_way_ids) < _MIN_SHARED_WAYS_FOR_OVERLAP:
                continue

            smaller_route_size = min(len(left_way_ids), len(right_way_ids))
            if len(shared_way_ids) / smaller_route_size < _MIN_OVERLAP_FRACTION:
                continue

            adjacency[left_index].add(right_index)
            adjacency[right_index].add(left_index)

    group_slots = [0.0] * len(offset_group_way_sets)
    slot_candidates = _build_slot_sequence(len(offset_group_way_sets) + 1)
    route_order = sorted(
        range(len(offset_group_way_sets)),
        key=lambda index: len(adjacency[index]),
        reverse=True,
    )

    for route_index in route_order:
        used_slots = {
            group_slots[neighbor_index] for neighbor_index in adjacency[route_index]
        }
        for slot in slot_candidates:
            if slot not in used_slots:
                group_slots[route_index] = slot
                break

    return [
        group_slots[offset_group_indices[offset_group_key]]
        for offset_group_key in offset_group_keys
    ]
