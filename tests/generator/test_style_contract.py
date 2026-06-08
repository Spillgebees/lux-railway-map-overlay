from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.etree import ElementTree

REPOSITORY_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from generator import platform_references
from generator.layer_specs import GEOJSON_LAYER_SPECS, SHAPEFILE_LAYER_SPECS

ACTIVE_RAIL_TRACK_LAYER_IDS = {
    "railway-line-rail",
    "railway-line-light-rail",
    "railway-line-subway",
    "railway-line-narrow-gauge",
    "railway-line-funicular",
    "railway-line-monorail",
    "railway-line-miniature",
    "railway-line-service",
    "tram-line-fill",
    "railway-line-tunnel",
    "tram-line-tunnel",
}


def _expression_contains(expression: object, expected: object) -> bool:
    if expression == expected:
        return True
    if isinstance(expression, list):
        return any(_expression_contains(item, expected) for item in expression)
    return False


def test_style_preserved_track_layer_reads_preserved_tagged_rail_tracks() -> None:
    # arrange
    style = json.loads((REPOSITORY_ROOT / "styles" / "style.json").read_text())

    # act
    preserved_layers = [
        layer
        for layer in style["layers"]
        if layer["id"] == "railway-lifecycle-preserved"
    ]

    # assert
    assert preserved_layers
    assert {layer["source-layer"] for layer in preserved_layers} == {"rail_tracks"}
    assert all(
        layer["metadata"]["toggle"][-1] == "preserved" for layer in preserved_layers
    )


def test_style_restores_key_visual_contract_for_old_layer_ids() -> None:
    # arrange
    style = json.loads((REPOSITORY_ROOT / "styles" / "style.json").read_text())

    # act
    layers = {layer["id"]: layer for layer in style["layers"]}

    # assert
    assert layers["railway-line-rail"]["paint"]["line-color"] == "#1e293b"
    assert layers["railway-line-rail"]["paint"]["line-width"] == [
        "interpolate",
        ["linear"],
        ["zoom"],
        6,
        1,
        10,
        2,
        14,
        3,
        18,
        4,
    ]
    assert layers["tram-line-fill"]["layout"]["visibility"] == "none"
    assert layers["railway-platforms-3d"]["paint"]["fill-extrusion-height"] == 1.5
    assert layers["railway-tunnel-label"]["layout"]["icon-size"] == 0.3
    assert layers["railway-switches"]["layout"]["visibility"] == "none"


def test_style_platform_label_filters_use_normalized_source_layer() -> None:
    # arrange
    style = json.loads((REPOSITORY_ROOT / "styles" / "style.json").read_text())
    platform_label_layer_ids = {
        "railway-platform-refs-label",
        "railway-platform-names-label",
    }

    # act
    platform_label_layers = [
        layer for layer in style["layers"] if layer["id"] in platform_label_layer_ids
    ]

    # assert
    assert len(platform_label_layers) == len(platform_label_layer_ids)
    for layer in platform_label_layers:
        serialized_layer = json.dumps(layer)
        assert "railway_platforms" not in serialized_layer
        assert "rail_platforms" in serialized_layer


def test_style_active_track_layers_filter_to_active_lifecycle_state() -> None:
    # arrange
    style = json.loads((REPOSITORY_ROOT / "styles" / "style.json").read_text())
    layers = {layer["id"]: layer for layer in style["layers"]}
    expected_filter = ["==", ["get", "lifecycle_state"], "active"]

    # act
    active_track_layers = [layers[layer_id] for layer_id in ACTIVE_RAIL_TRACK_LAYER_IDS]

    # assert
    for layer in active_track_layers:
        assert layer["source-layer"] == "rail_tracks"
        assert _expression_contains(layer["filter"], expected_filter)


def test_style_splits_tram_lifecycle_layers_by_mode_and_state_for_visibility_toggles() -> (
    None
):
    # arrange
    style = json.loads((REPOSITORY_ROOT / "styles" / "style.json").read_text())
    lifecycle_states = {"construction", "proposed", "disused", "abandoned", "razed"}
    expected_pairs = {
        (mode, state) for mode in {"tram", "light_rail"} for state in lifecycle_states
    }
    expected_non_tram_filter = [
        "!",
        ["in", ["get", "mode"], ["literal", ["tram", "light_rail"]]],
    ]
    expected_width = ["interpolate", ["linear"], ["zoom"], 10, 1.5, 14, 2.5]
    expected_paints = {
        "construction": ("#b45309", 0.8),
        "proposed": ("#d97706", 0.4),
        "disused": ("#a8a29e", 0.5),
        "abandoned": ("#d6d3d1", 0.35),
        "razed": ("#e7e5e4", 0.25),
    }

    # act
    tram_lifecycle_layers = [
        layer
        for layer in style["layers"]
        if layer["id"].startswith("tram-lifecycle-")
        or layer["id"].startswith("light-rail-lifecycle-")
    ]
    actual_pairs = {
        (layer["metadata"]["mode"], layer["metadata"]["state"])
        for layer in tram_lifecycle_layers
    }
    generic_lifecycle_layers = [
        layer
        for layer in style["layers"]
        if layer["id"] in {f"railway-lifecycle-{state}" for state in lifecycle_states}
    ]

    # assert
    assert actual_pairs == expected_pairs
    for layer in generic_lifecycle_layers:
        assert _expression_contains(layer["filter"], expected_non_tram_filter)
    for layer in tram_lifecycle_layers:
        state = layer["metadata"]["state"]
        assert layer["layout"]["visibility"] == "none"
        assert layer["metadata"]["toggle"] == [
            "tracks",
            layer["metadata"]["mode"],
            state,
        ]
        assert _expression_contains(
            layer["filter"], ["==", ["get", "mode"], layer["metadata"]["mode"]]
        )
        assert _expression_contains(
            layer["filter"], ["==", ["get", "lifecycle_state"], state]
        )
        assert layer["paint"]["line-color"] == expected_paints[state][0]
        assert layer["paint"]["line-opacity"] == expected_paints[state][1]
        assert layer["paint"]["line-width"] == expected_width
        assert '"railway"' not in json.dumps(layer["paint"])


def test_viewer_dependency_docs_match_package_only_project() -> None:
    # arrange
    readme = (REPOSITORY_ROOT / "README.md").read_text()
    project = ElementTree.parse(REPOSITORY_ROOT / "viewer" / "RailwayViewer.csproj")

    # act
    has_project_reference = project.getroot().find(".//ProjectReference") is not None

    # assert
    assert not has_project_reference
    assert "Spillgebees.Blazor.Map` package by default (`0.16.0`)" in readme
    assert "Supported resolution order" not in readme
    assert "BLAZOR_MAP_PROJECT_PATH" not in readme
    assert "BlazorMapProjectPath" not in readme


def test_geojson_lifecycle_sql_restricts_namespaced_values_to_actual_track_modes() -> (
    None
):
    # arrange
    sql_by_layer = {layer_name: sql for layer_name, sql, _ in GEOJSON_LAYER_SPECS}

    # act
    lifecycle_sql = sql_by_layer["rail_tracks_lifecycle"]

    # assert
    assert "construction_railway IN" in lifecycle_sql
    assert "platform" not in lifecycle_sql
    assert "turntable" not in lifecycle_sql


def test_geojson_layer_specs_keep_preserved_tracks_in_rendered_track_layer() -> None:
    # arrange
    sql_by_layer = {layer_name: sql for layer_name, sql, _ in GEOJSON_LAYER_SPECS}

    # act
    track_sql = sql_by_layer["rail_tracks"]
    lifecycle_sql = sql_by_layer["rail_tracks_lifecycle"]

    # assert
    assert "'preserved'" in track_sql
    assert "'preserved'" not in lifecycle_sql


def test_shapefile_active_track_sql_includes_all_rendered_active_modes() -> None:
    # arrange
    shapefile_sql_by_file = {
        file_name: sql for file_name, _, sql in SHAPEFILE_LAYER_SPECS
    }
    expected_railway_values = {
        "rail",
        "light_rail",
        "tram",
        "subway",
        "narrow_gauge",
        "monorail",
        "funicular",
        "miniature",
        "preserved",
    }

    # act
    active_track_sql = shapefile_sql_by_file["rail_tracks.shp"]

    # assert
    for railway_value in expected_railway_values:
        assert f"'{railway_value}'" in active_track_sql


def test_style_route_layers_read_display_layer_with_intended_default_visibility() -> (
    None
):
    # arrange
    style = json.loads((REPOSITORY_ROOT / "styles" / "style.json").read_text())
    route_layer_ids = {
        "railway-routes-casing",
        "railway-routes",
        "railway-routes-label",
    }

    # act
    route_layers = [
        layer for layer in style["layers"] if layer["id"] in route_layer_ids
    ]
    route_line_layer = next(
        layer for layer in route_layers if layer["id"] == "railway-routes"
    )
    casing_layer = next(
        layer for layer in route_layers if layer["id"] == "railway-routes-casing"
    )
    label_layer = next(
        layer for layer in route_layers if layer["id"] == "railway-routes-label"
    )

    # assert
    assert len(route_layers) == len(route_layer_ids)
    assert {layer["source-layer"] for layer in route_layers} == {"rail_routes_display"}
    assert casing_layer["layout"]["visibility"] == "none"
    assert route_line_layer.get("layout", {}).get("visibility") != "none"
    assert label_layer.get("layout", {}).get("visibility") != "none"
    for layer in route_layers:
        assert not _expression_contains(layer["filter"], ["has", "display_colour"])
    assert _expression_contains(
        route_line_layer["paint"]["line-color"], "display_colour"
    )
    assert _expression_contains(route_line_layer["paint"]["line-color"], "#5B6675")
    assert _expression_contains(
        label_layer["paint"]["text-color"], "display_text_colour"
    )
    assert _expression_contains(label_layer["paint"]["text-color"], "#0F172A")


def test_publish_image_workflow_validates_normalized_route_geojson_names() -> None:
    # arrange
    workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "publish-image.yml"
    ).read_text()

    # act
    validates_canonical_routes = (
        "data/intermediate/geojson/rail_routes.geojson" in workflow
    )
    validates_display_routes = (
        "data/intermediate/geojson/rail_routes_display.geojson" in workflow
    )

    # assert
    assert validates_canonical_routes
    assert validates_display_routes
    assert "railway_routes.geojson" not in workflow
    assert "railway_routes_display.geojson" not in workflow


def test_viewer_route_toggle_targets_every_route_style_layer() -> None:
    # arrange
    viewer_page = (REPOSITORY_ROOT / "viewer" / "Pages" / "Home.razor").read_text()
    expected_route_layers = {
        'new("railway-routes-casing", ["routes"])',
        'new("railway-routes", ["routes"])',
        'new("railway-routes-label", ["routes"])',
    }

    # act
    missing_route_layers = {
        route_layer
        for route_layer in expected_route_layers
        if route_layer not in viewer_page
    }

    # assert
    assert not missing_route_layers


def test_geojson_lifecycle_sql_matches_shapefile_razed_schema() -> None:
    # arrange
    geojson_sql_by_layer = {
        layer_name: sql for layer_name, sql, _ in GEOJSON_LAYER_SPECS
    }
    shapefile_sql_by_file = {
        file_name: sql for file_name, _, sql in SHAPEFILE_LAYER_SPECS
    }

    # act
    geojson_lifecycle_sql = geojson_sql_by_layer["rail_tracks_lifecycle"]
    shapefile_lifecycle_sql = shapefile_sql_by_file["rail_tracks_lifecycle.shp"]

    # assert
    assert "'razed'" in geojson_lifecycle_sql
    assert "'razed'" in shapefile_lifecycle_sql
    assert "razed_railway IN" in geojson_lifecycle_sql
    assert "razed_railway IN" in shapefile_lifecycle_sql


def test_lifecycle_sql_keeps_razed_support_without_non_track_namespaced_values() -> (
    None
):
    # arrange
    geojson_sql_by_layer = {
        layer_name: sql for layer_name, sql, _ in GEOJSON_LAYER_SPECS
    }
    shapefile_sql_by_file = {
        file_name: sql for file_name, _, sql in SHAPEFILE_LAYER_SPECS
    }

    # act
    lifecycle_sql_queries = [
        geojson_sql_by_layer["rail_tracks_lifecycle"],
        shapefile_sql_by_file["rail_tracks_lifecycle.shp"],
    ]

    # assert
    for lifecycle_sql in lifecycle_sql_queries:
        assert (
            "railway IN ('construction','proposed','disused','abandoned','razed')"
            in lifecycle_sql
        )
        assert "razed_railway IN" in lifecycle_sql
        assert "'platform'" not in lifecycle_sql
        assert "'turntable'" not in lifecycle_sql


def test_vscode_run_viewer_task_uses_packaged_blazor_map_dependency() -> None:
    # arrange
    tasks_path = REPOSITORY_ROOT / ".vscode" / "tasks.json"
    tasks_config = json.loads(tasks_path.read_text())

    # act
    run_viewer_task = next(
        task for task in tasks_config["tasks"] if task["label"] == "Run Viewer"
    )
    serialized_tasks = json.dumps(tasks_config)

    # assert
    assert "BLAZOR_MAP_PROJECT_PATH" not in run_viewer_task.get("options", {}).get(
        "env", {}
    )
    assert "blazorMapProjectPath" not in serialized_tasks
    assert "BLAZOR_MAP_PROJECT_PATH" not in serialized_tasks


def test_osmconf_exposes_platform_label_fallback_tags_as_fields() -> None:
    # arrange
    osmconf = (REPOSITORY_ROOT / "scripts" / "osmconf.ini").read_text()
    expected_tags = {
        "local_ref",
        "ref:IFOPT",
        "ref:IFOPT:description",
        "description",
        "route_ref",
    }

    # act
    section_attributes = {}
    current_section = None
    for line in osmconf.splitlines():
        if line.startswith("[") and line.endswith("]"):
            current_section = line.strip("[]")
        elif current_section in {"points", "multipolygons"} and line.startswith(
            "attributes="
        ):
            section_attributes[current_section] = set(
                line.removeprefix("attributes=").split(",")
            )

    # assert
    assert expected_tags <= section_attributes["points"]
    assert expected_tags <= section_attributes["multipolygons"]


def test_osmconf_keeps_other_tags_for_platform_label_fallbacks() -> None:
    # arrange
    osmconf = (REPOSITORY_ROOT / "scripts" / "osmconf.ini").read_text()

    # act
    section_other_tags = {}
    current_section = None
    for line in osmconf.splitlines():
        if line.startswith("[") and line.endswith("]"):
            current_section = line.strip("[]")
        elif current_section in {"points", "multipolygons"} and line.startswith(
            "other_tags="
        ):
            section_other_tags[current_section] = line.removeprefix("other_tags=")

    # assert
    assert section_other_tags["points"] == "yes"
    assert section_other_tags["multipolygons"] == "yes"


def test_platform_references_use_ogr_normalized_ifopt_description() -> None:
    # arrange
    raw_feature = {
        "type": "Feature",
        "properties": {
            "osm_id": 45,
            "railway": "platform",
            "ref_IFOPT_description": "Gleis 4B",
        },
        "geometry": {"type": "Point", "coordinates": [6.12, 49.61]},
    }

    # act
    feature = platform_references.build_platform_reference_feature(
        raw_feature,
        source_layer="rail_platforms",
        require_stop_position=False,
    )

    # assert
    assert feature is not None
    assert feature["properties"]["platform_ref_label"] == "Gleis 4B"
    assert feature["properties"]["ref_ifopt_description"] == "Gleis 4B"


def test_viewer_project_has_no_stray_blazor_map_path_text_nodes() -> None:
    # arrange
    project_path = REPOSITORY_ROOT / "viewer" / "RailwayViewer.csproj"

    # act
    project = ElementTree.parse(project_path)
    property_group = project.getroot().find("PropertyGroup")

    # assert
    assert property_group is not None
    assert property_group.text is None or property_group.text.strip() == ""
    assert all(
        child.tail is None or child.tail.strip() == "" for child in property_group
    )
    assert (
        project.getroot().find(".//PackageReference[@Include='Spillgebees.Blazor.Map']")
        is not None
    )


def test_consumer_docs_platform_fallback_matches_style_expression() -> None:
    # arrange
    style = json.loads((REPOSITORY_ROOT / "styles" / "style.json").read_text())
    docs = (REPOSITORY_ROOT / "docs" / "consumer-integration.md").read_text()

    # act
    platform_layer = next(
        layer
        for layer in style["layers"]
        if layer["id"] == "railway-platform-refs-label"
    )
    fallback_fields = [entry[1] for entry in platform_layer["layout"]["text-field"][1:]]
    expected_snippet = "\n".join(
        ['["coalesce",']
        + [f'  ["get", "{field}"],' for field in fallback_fields[:-1]]
        + [f'  ["get", "{fallback_fields[-1]}"]', "]"]
    )

    # assert
    assert expected_snippet in docs
