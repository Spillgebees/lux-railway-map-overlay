from __future__ import annotations

import heapq
import math
import re

from generator.route_naming import iter_station_aliases, normalize_text

# maximum candidate nodes to consider per endpoint when searching for the
# best component path; keeps the O(n*m) pair search bounded
_MAX_ENDPOINT_CANDIDATES = 8

# maximum distance in degrees (~5.5 km at Luxembourg latitude) between a
# graph node and a station coordinate for the node to be considered a
# plausible route endpoint
_STATION_PROXIMITY_THRESHOLD_DEG = 0.05

# distance threshold for _endpoint_distance checks when selecting the best
# segment subset that spans a route
_SEGMENT_ENDPOINT_MATCH_THRESHOLD_DEG = 0.1

# maximum gap in degrees (~5.5 km) between two segment endpoints for them
# to be considered connected when building the segment adjacency graph
_SEGMENT_JOIN_THRESHOLD_DEG = 0.05

# minimum number of coordinates in a secondary segment to be kept, expressed
# as a fraction of the longest segment's length
_MIN_SEGMENT_LENGTH_FRACTION = 0.05
_MIN_SEGMENT_LENGTH_ABSOLUTE = 10

# maximum endpoint distance in degrees (~5.5 km) for two segments
# to be considered duplicates of each other
_SEGMENT_SIMILARITY_THRESHOLD_DEG = 0.05


def build_station_indexes(
    stations_geojson: dict[str, object],
    bbox: str,
) -> tuple[set[str], dict[str, list[list[float]]]]:
    """Build both the Luxembourg station name set and the station match index in one pass."""
    south, west, north, east = (float(value) for value in bbox.split(","))

    luxembourg_names: set[str] = set()
    match_index: dict[str, list[list[float]]] = {}

    for feature in stations_geojson.get("features", []):
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "Point":
            continue
        coordinates = geometry.get("coordinates", [])
        if len(coordinates) != 2:
            continue

        lon, lat = coordinates
        is_in_lux = west <= lon <= east and south <= lat <= north

        for alias in iter_station_aliases(feature):
            normalized = normalize_text(alias)
            if not normalized:
                continue
            match_index.setdefault(normalized, []).append(coordinates)
            if is_in_lux:
                luxembourg_names.add(normalized)

    return luxembourg_names, match_index


def build_luxembourg_station_names(
    stations_geojson: dict[str, object],
    bbox: str,
) -> set[str]:
    """Collect normalized station aliases that fall inside the Luxembourg bbox.

    Route relations are only kept when at least one endpoint resolves to a station in
    Luxembourg, so this set acts as the geographic gate for otherwise cross-border
    relations.
    """
    luxembourg_names, _ = build_station_indexes(stations_geojson, bbox)
    return luxembourg_names


def build_station_match_index(
    stations_geojson: dict[str, object],
) -> dict[str, list[list[float]]]:
    # Use a bbox that covers the entire world so all stations are included.
    _, match_index = build_station_indexes(stations_geojson, "-90,-180,90,180")
    return match_index


def resolve_station_matches(
    endpoint_name: str,
    station_matches_by_name: dict[str, list[list[float]]],
    station_match_cache: dict[str, list[list[float]]] | None = None,
) -> list[list[float]]:
    """Resolve a route endpoint name to candidate station coordinates.

    Exact normalized name matches win. When no exact hit exists, the function falls
    back to boundary-aware substring matching so names like "Luxembourg Ville" can
    still satisfy route endpoints such as "Ville" without matching arbitrary text.
    """
    normalized_endpoint_name = normalize_text(endpoint_name)
    if not normalized_endpoint_name:
        return []

    cache = station_match_cache if station_match_cache is not None else {}
    cached_matches = cache.get(normalized_endpoint_name)
    if cached_matches is not None:
        return cached_matches

    exact_matches = station_matches_by_name.get(normalized_endpoint_name)
    if exact_matches:
        cache[normalized_endpoint_name] = exact_matches
        return exact_matches

    fuzzy_matches: list[tuple[tuple[int, int], list[list[float]]]] = []
    boundary_pattern = re.compile(
        rf"(^|[\s\-/,(]){re.escape(normalized_endpoint_name)}($|[\s\-/,)])"
    )
    for normalized_station_name, coordinates in station_matches_by_name.items():
        if boundary_pattern.search(normalized_station_name):
            fuzzy_matches.append(
                (
                    (
                        0,
                        abs(
                            len(normalized_station_name) - len(normalized_endpoint_name)
                        ),
                    ),
                    coordinates,
                )
            )
            continue

        if (
            normalized_endpoint_name in normalized_station_name
            or normalized_station_name in normalized_endpoint_name
        ):
            fuzzy_matches.append(
                (
                    (
                        1,
                        abs(
                            len(normalized_station_name) - len(normalized_endpoint_name)
                        ),
                    ),
                    coordinates,
                )
            )

    if not fuzzy_matches:
        cache[normalized_endpoint_name] = []
        return []

    fuzzy_matches.sort(key=lambda item: item[0])
    best_score = fuzzy_matches[0][0]
    matches: list[list[float]] = []
    for score, coordinates in fuzzy_matches:
        if score != best_score:
            break
        matches.extend(coordinates)

    cache[normalized_endpoint_name] = matches
    return matches


def chain_ways(
    way_ids: list[int],
    ways: dict[int, dict],
    nodes: dict[int, tuple[float, float]],
    from_station_matches: list[list[float]],
    to_station_matches: list[list[float]],
) -> list[list[list[float]]]:
    """Turn unordered relation members into one or more ordered route segments.

    The input relation members often arrive fragmented, duplicated, or split into
    disconnected components. This routine builds a lightweight graph over way
    endpoints, tries to extract the component path that best connects the resolved
    route endpoints, and only falls back to greedy stitching when no clear endpoint
    path exists.
    """
    deduplicated_way_ids = _dedupe_way_ids(way_ids)
    way_records: list[dict] = []
    endpoint_index: dict[int, list[int]] = {}

    for way_id in deduplicated_way_ids:
        way = ways.get(way_id)
        if way is None:
            continue

        way_coords = _resolve_way_coords(way, nodes)
        way_nodes = way.get("nodes", [])
        if len(way_coords) < 2 or len(way_nodes) < 2:
            continue

        record_index = len(way_records)
        start_node = way_nodes[0]
        end_node = way_nodes[-1]
        record = {
            "way_id": way_id,
            "coords": way_coords,
            "start_node": start_node,
            "end_node": end_node,
            "point_count": len(way_coords),
            "geo_length": sum(
                math.hypot(
                    way_coords[index + 1][0] - way_coords[index][0],
                    way_coords[index + 1][1] - way_coords[index][1],
                )
                for index in range(len(way_coords) - 1)
            ),
        }
        way_records.append(record)
        endpoint_index.setdefault(start_node, []).append(record_index)
        endpoint_index.setdefault(end_node, []).append(record_index)

    if not way_records:
        return []

    adjacency: list[set[int]] = [set() for _ in way_records]
    for connected_records in endpoint_index.values():
        for left_position, left_index in enumerate(connected_records):
            for right_index in connected_records[left_position + 1 :]:
                adjacency[left_index].add(right_index)
                adjacency[right_index].add(left_index)

    component_ids = [-1] * len(way_records)
    component_count = 0
    for record_index in range(len(way_records)):
        if component_ids[record_index] != -1:
            continue

        stack = [record_index]
        component_ids[record_index] = component_count
        while stack:
            current_index = stack.pop()
            for neighbor_index in adjacency[current_index]:
                if component_ids[neighbor_index] != -1:
                    continue
                component_ids[neighbor_index] = component_count
                stack.append(neighbor_index)

        component_count += 1

    component_record_indices: list[list[int]] = [[] for _ in range(component_count)]
    for record_index, component_id in enumerate(component_ids):
        component_record_indices[component_id].append(record_index)

    segments: list[list[list[float]]] = []
    for component_indices in component_record_indices:
        remaining_indices = set(component_indices)

        component_path = _extract_component_path(
            remaining_indices,
            way_records,
            endpoint_index,
            nodes,
            from_station_matches,
            to_station_matches,
        )
        if component_path is not None:
            segments.append(component_path)
            continue

        seed_index = max(
            remaining_indices,
            key=lambda record_index: way_records[record_index]["point_count"],
        )
        seed_record = way_records[seed_index]

        start_node = seed_record["start_node"]
        end_node = seed_record["end_node"]
        if _endpoint_degree(
            remaining_indices, end_node, endpoint_index
        ) < _endpoint_degree(remaining_indices, start_node, endpoint_index):
            start_node, end_node = end_node, start_node

        oriented_seed_coords, oriented_end_node = _orient_coords(
            seed_record, start_node
        )
        remaining_indices.remove(seed_index)
        current_line = list(oriented_seed_coords)
        line_start_node = start_node
        line_end_node = oriented_end_node

        extended = True
        while extended:
            extended = False

            next_front_index = _choose_next_record(
                remaining_indices,
                line_start_node,
                way_records,
                endpoint_index,
            )
            if next_front_index is not None:
                next_front_record = way_records[next_front_index]
                front_coords, front_other_node = _orient_coords(
                    next_front_record, line_start_node
                )
                current_line = list(reversed(front_coords[:-1])) + current_line
                line_start_node = front_other_node
                remaining_indices.remove(next_front_index)
                extended = True

            next_back_index = _choose_next_record(
                remaining_indices,
                line_end_node,
                way_records,
                endpoint_index,
            )
            if next_back_index is not None:
                next_back_record = way_records[next_back_index]
                back_coords, back_other_node = _orient_coords(
                    next_back_record, line_end_node
                )
                current_line.extend(back_coords[1:])
                line_end_node = back_other_node
                remaining_indices.remove(next_back_index)
                extended = True

        if len(current_line) >= 2:
            segments.append(current_line)

    segments.sort(key=len, reverse=True)
    if len(segments) <= 1:
        return segments

    return _select_best_segments(segments, from_station_matches, to_station_matches)


def _dedupe_way_ids(way_ids: list[int]) -> list[int]:
    return list(dict.fromkeys(way_ids))


def _resolve_way_coords(
    way: dict, nodes: dict[int, tuple[float, float]]
) -> list[list[float]]:
    return [
        list(nodes[node_id]) for node_id in way.get("nodes", []) if node_id in nodes
    ]


def _endpoint_degree(
    record_indices: set[int],
    node_id: int,
    endpoint_index: dict[int, list[int]],
) -> int:
    return sum(
        1
        for record_index in endpoint_index.get(node_id, [])
        if record_index in record_indices
    )


def _orient_coords(record: dict, from_node: int) -> tuple[list[list[float]], int]:
    if record["start_node"] == from_node:
        return record["coords"], record["end_node"]
    return list(reversed(record["coords"])), record["start_node"]


def _choose_next_record(
    record_indices: set[int],
    node_id: int,
    way_records: list[dict],
    endpoint_index: dict[int, list[int]],
) -> int | None:
    candidates = [
        record_index
        for record_index in endpoint_index.get(node_id, [])
        if record_index in record_indices
    ]
    if not candidates:
        return None

    # prefer ways with more points; among ties, prefer ways whose
    # least-connected endpoint has higher degree (avoids dead ends)
    candidates.sort(
        key=lambda record_index: (
            way_records[record_index]["point_count"],
            -min(
                _endpoint_degree(
                    record_indices,
                    way_records[record_index]["start_node"],
                    endpoint_index,
                ),
                _endpoint_degree(
                    record_indices,
                    way_records[record_index]["end_node"],
                    endpoint_index,
                ),
            ),
        ),
        reverse=True,
    )
    return candidates[0]


def _node_distance(
    node_id: int,
    station_matches: list[list[float]],
    nodes: dict[int, tuple[float, float]],
) -> float | None:
    if not station_matches or node_id not in nodes:
        return None

    node_lon, node_lat = nodes[node_id]
    best_distance = None
    for station_coordinates in station_matches:
        distance = math.hypot(
            node_lon - station_coordinates[0],
            node_lat - station_coordinates[1],
        )
        if best_distance is None or distance < best_distance:
            best_distance = distance
    return best_distance


def _build_path_coords(
    path_record_indices: list[int],
    start_node: int,
    way_records: list[dict],
) -> list[list[float]]:
    if not path_record_indices:
        return []

    current_node = start_node
    path_coords: list[list[float]] = []
    for position, record_index in enumerate(path_record_indices):
        record = way_records[record_index]
        oriented_coords, next_node = _orient_coords(record, current_node)
        if position == 0:
            path_coords.extend(oriented_coords)
        else:
            path_coords.extend(oriented_coords[1:])
        current_node = next_node
    return path_coords


def _shortest_component_path(
    record_indices: set[int],
    start_node: int,
    end_node: int,
    way_records: list[dict],
) -> list[int] | None:
    """Find the lowest-cost path through one connected component using geometric
    length as the edge cost.
    """
    if start_node == end_node:
        return []

    node_edges: dict[int, list[tuple[int, int, float]]] = {}
    for record_index in record_indices:
        record = way_records[record_index]
        start = record["start_node"]
        end = record["end_node"]
        edge_cost = max(float(record["geo_length"]), 1e-9)
        node_edges.setdefault(start, []).append((end, record_index, edge_cost))
        node_edges.setdefault(end, []).append((start, record_index, edge_cost))

    queue: list[tuple[float, int]] = [(0.0, start_node)]
    best_cost_by_node = {start_node: 0.0}
    predecessor_by_node: dict[int, tuple[int, int]] = {}

    while queue:
        current_cost, current_node = heapq.heappop(queue)
        if current_cost > best_cost_by_node.get(current_node, float("inf")):
            continue
        if current_node == end_node:
            break

        for neighbor_node, record_index, edge_cost in node_edges.get(current_node, []):
            neighbor_cost = current_cost + edge_cost
            if neighbor_cost >= best_cost_by_node.get(neighbor_node, float("inf")):
                continue
            best_cost_by_node[neighbor_node] = neighbor_cost
            predecessor_by_node[neighbor_node] = (current_node, record_index)
            heapq.heappush(queue, (neighbor_cost, neighbor_node))

    if end_node not in predecessor_by_node:
        return None

    path_record_indices: list[int] = []
    current_node = end_node
    while current_node != start_node:
        previous_node, record_index = predecessor_by_node[current_node]
        path_record_indices.append(record_index)
        current_node = previous_node
    path_record_indices.reverse()
    return path_record_indices


def _extract_component_path(
    record_indices: set[int],
    way_records: list[dict],
    endpoint_index: dict[int, list[int]],
    nodes: dict[int, tuple[float, float]],
    from_station_matches: list[list[float]],
    to_station_matches: list[list[float]],
) -> list[list[float]] | None:
    """Try to recover the subpath in a component that best links both route endpoints.

    Rather than testing every node pair, the search first ranks the nodes nearest to
    the resolved stations, then evaluates only that shortlist. The resulting score
    favors paths whose ends are spatially close to the requested stations while still
    preferring longer, better-connected geometries over trivial fragments.
    """
    component_node_ids = sorted(
        {way_records[record_index]["start_node"] for record_index in record_indices}
        | {way_records[record_index]["end_node"] for record_index in record_indices}
    )
    if not component_node_ids:
        return None

    if not from_station_matches or not to_station_matches:
        return None

    ranked_from_nodes = sorted(
        component_node_ids,
        key=lambda node_id: (
            _node_distance(node_id, from_station_matches, nodes) or float("inf"),
            -_endpoint_degree(record_indices, node_id, endpoint_index),
        ),
    )[:_MAX_ENDPOINT_CANDIDATES]
    ranked_to_nodes = sorted(
        component_node_ids,
        key=lambda node_id: (
            _node_distance(node_id, to_station_matches, nodes) or float("inf"),
            -_endpoint_degree(record_indices, node_id, endpoint_index),
        ),
    )[:_MAX_ENDPOINT_CANDIDATES]

    best_component_path: (
        tuple[tuple[int, float, float, int], list[list[float]]] | None
    ) = None
    for from_node in ranked_from_nodes:
        from_distance = _node_distance(from_node, from_station_matches, nodes)
        if from_distance is None:
            continue

        for to_node in ranked_to_nodes:
            if from_node == to_node:
                continue

            to_distance = _node_distance(to_node, to_station_matches, nodes)
            if to_distance is None:
                continue

            path_record_indices = _shortest_component_path(
                record_indices,
                from_node,
                to_node,
                way_records,
            )
            if not path_record_indices:
                continue

            path_coords = _build_path_coords(
                path_record_indices, from_node, way_records
            )
            if len(path_coords) < 2:
                continue

            # ranking: (1) both endpoints within station proximity threshold,
            # (2) minimize total distance to stations, (3) prefer longer
            # geometries, (4) prefer more ways (better-connected paths)
            path_score = (
                int(
                    from_distance <= _STATION_PROXIMITY_THRESHOLD_DEG
                    and to_distance <= _STATION_PROXIMITY_THRESHOLD_DEG
                ),
                -(from_distance + to_distance),
                len(path_coords),
                len(path_record_indices),
            )
            if best_component_path is None or path_score > best_component_path[0]:
                best_component_path = (path_score, path_coords)

    if best_component_path is None:
        return None

    return best_component_path[1]


def _endpoint_distance(
    segment: list[list[float]],
    station_matches: list[list[float]],
) -> float | None:
    if not station_matches:
        return None

    best_distance = None
    for station_coordinates in station_matches:
        for point in (segment[0], segment[-1]):
            distance = math.hypot(
                point[0] - station_coordinates[0],
                point[1] - station_coordinates[1],
            )
            if best_distance is None or distance < best_distance:
                best_distance = distance
    return best_distance


def _nearest_segment_index(
    segments: list[list[list[float]]],
    station_matches: list[list[float]],
) -> tuple[int | None, float | None]:
    best_index = None
    best_distance = None
    for index, segment in enumerate(segments):
        distance = _endpoint_distance(segment, station_matches)
        if distance is None:
            continue
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_index = index
    return best_index, best_distance


def _segment_gap(left: list[list[float]], right: list[list[float]]) -> float:
    return min(
        math.hypot(left_point[0] - right_point[0], left_point[1] - right_point[1])
        for left_point in (left[0], left[-1])
        for right_point in (right[0], right[-1])
    )


def _are_similar_segments(left: list[list[float]], right: list[list[float]]) -> bool:
    direct_distance = math.hypot(
        left[0][0] - right[0][0], left[0][1] - right[0][1]
    ) + math.hypot(left[-1][0] - right[-1][0], left[-1][1] - right[-1][1])
    reverse_distance = math.hypot(
        left[0][0] - right[-1][0], left[0][1] - right[-1][1]
    ) + math.hypot(left[-1][0] - right[0][0], left[-1][1] - right[0][1])
    return min(direct_distance, reverse_distance) < _SEGMENT_SIMILARITY_THRESHOLD_DEG


def _select_best_segments(
    segments: list[list[list[float]]],
    from_station_matches: list[list[float]],
    to_station_matches: list[list[float]],
) -> list[list[list[float]]]:
    """Keep the segment subset that best represents the requested route.

    Relations sometimes include side branches, duplicated alignments, or nearby but
    unrelated fragments. This filter first looks for a single segment matching both
    endpoints, then preserves endpoint-relevant segments and joins only the connected
    chain needed to span the route.
    """
    if not from_station_matches or not to_station_matches:
        return [segments[0]]

    endpoint_match_threshold = _SEGMENT_ENDPOINT_MATCH_THRESHOLD_DEG
    full_match_segment_indices = [
        index
        for index, segment in enumerate(segments)
        if (_endpoint_distance(segment, from_station_matches) or float("inf"))
        <= endpoint_match_threshold
        and (_endpoint_distance(segment, to_station_matches) or float("inf"))
        <= endpoint_match_threshold
    ]
    if full_match_segment_indices:
        best_index = max(
            full_match_segment_indices, key=lambda index: len(segments[index])
        )
        return [segments[best_index]]

    preserve_indices = {0}
    preserve_indices.add(
        min(
            range(len(segments)),
            key=lambda index: _endpoint_distance(segments[index], from_station_matches)
            or float("inf"),
        )
    )
    preserve_indices.add(
        min(
            range(len(segments)),
            key=lambda index: _endpoint_distance(segments[index], to_station_matches)
            or float("inf"),
        )
    )

    minimum_segment_length = max(
        _MIN_SEGMENT_LENGTH_ABSOLUTE,
        int(len(segments[0]) * _MIN_SEGMENT_LENGTH_FRACTION),
    )
    filtered_segments = [
        segment
        for index, segment in enumerate(segments)
        if index in preserve_indices or len(segment) >= minimum_segment_length
    ]

    deduplicated_segments: list[list[list[float]]] = []
    for segment in filtered_segments:
        if any(
            _are_similar_segments(segment, existing_segment)
            for existing_segment in deduplicated_segments
        ):
            continue
        deduplicated_segments.append(segment)

    segments = deduplicated_segments
    if len(segments) <= 1:
        return segments

    from_segment_index, from_segment_distance = _nearest_segment_index(
        segments,
        from_station_matches,
    )
    to_segment_index, to_segment_distance = _nearest_segment_index(
        segments,
        to_station_matches,
    )

    if (
        from_segment_index is None
        or to_segment_index is None
        or from_segment_distance is None
        or to_segment_distance is None
        or from_segment_distance > endpoint_match_threshold
        or to_segment_distance > endpoint_match_threshold
    ):
        return [segments[0]]

    if from_segment_index == to_segment_index:
        return [segments[from_segment_index]]

    segment_adjacency: list[set[int]] = [set() for _ in segments]
    segment_join_threshold = _SEGMENT_JOIN_THRESHOLD_DEG
    for left_index, left_segment in enumerate(segments):
        for right_index in range(left_index + 1, len(segments)):
            right_segment = segments[right_index]
            if _segment_gap(left_segment, right_segment) > segment_join_threshold:
                continue
            segment_adjacency[left_index].add(right_index)
            segment_adjacency[right_index].add(left_index)

    predecessor_by_index = {from_segment_index: None}
    queue = [from_segment_index]
    for current_index in queue:
        if current_index == to_segment_index:
            break
        for neighbor_index in segment_adjacency[current_index]:
            if neighbor_index in predecessor_by_index:
                continue
            predecessor_by_index[neighbor_index] = current_index
            queue.append(neighbor_index)

    if to_segment_index not in predecessor_by_index:
        return [segments[0]]

    path_indices: list[int] = []
    current_index = to_segment_index
    while current_index is not None:
        path_indices.append(current_index)
        current_index = predecessor_by_index[current_index]
    path_indices.reverse()
    return [segments[index] for index in path_indices]
