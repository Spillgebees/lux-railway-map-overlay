from __future__ import annotations

import json
import urllib.error
from types import MethodType

import pytest

from generator import platform_references
from generator.config import Settings
from generator.console import Console
from generator.pipeline import GeneratorPipeline, PipelineError


def test_build_platform_reference_layer_prefers_platform_areas_and_keeps_unmatched_stop_positions(
    tmp_path,
) -> None:
    output_dir = tmp_path / "data"
    geojson_dir = output_dir / "intermediate" / "geojson"
    geojson_dir.mkdir(parents=True)

    (geojson_dir / "railway_platforms.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "osm_id": 1,
                            "name": "Quai 2",
                            "railway": "platform",
                            "ref": "2",
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [6.0, 49.0],
                                    [6.002, 49.0],
                                    [6.002, 49.002],
                                    [6.0, 49.002],
                                    [6.0, 49.0],
                                ]
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (geojson_dir / "railway_stations.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "osm_id": 10,
                            "name": "Luxembourg stop position",
                            "railway": "station",
                            "public_transport": "stop_position",
                            "local_ref": "2",
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [6.001, 49.001],
                        },
                    },
                    {
                        "type": "Feature",
                        "properties": {
                            "osm_id": 11,
                            "name": "Track 3 stop",
                            "railway": "station",
                            "public_transport": "stop_position",
                            "local_ref": "3",
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [6.05, 49.05],
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    pipeline = GeneratorPipeline(
        Settings(
            countries=("lu",),
            output_dir=output_dir,
            script_dir=tmp_path,
        ),
        Console(use_color=False),
    )

    pipeline.build_platform_reference_layer()

    feature_collection = json.loads(
        (geojson_dir / "railway_platform_refs.geojson").read_text(encoding="utf-8")
    )
    features = feature_collection["features"]

    assert len(features) == 2
    assert [feature["properties"]["source_layer"] for feature in features] == [
        "railway_platforms",
        "railway_stations",
    ]
    assert features[0]["properties"]["platform_label"] == "Quai 2"
    assert features[1]["properties"]["platform_ref_label"] == "3"


def test_parse_other_tags_unescapes_values() -> None:
    parsed = platform_references.parse_other_tags(
        '"ref:IFOPT:description"=>"Quai 4",' + '"note"=>"Station \\"Nord\\""'
    )

    assert parsed == {
        "ref:IFOPT:description": "Quai 4",
        "note": 'Station "Nord"',
    }


def test_build_platform_reference_feature_uses_description_when_ref_missing() -> None:
    feature = platform_references.build_platform_reference_feature(
        {
            "type": "Feature",
            "properties": {
                "osm_id": 44,
                "railway": "station",
                "public_transport": "stop_position",
                "description": "Voie 7",
            },
            "geometry": {"type": "Point", "coordinates": [6.12, 49.61]},
        },
        source_layer="railway_stations",
        require_stop_position=True,
    )

    assert feature is not None
    assert feature["properties"]["platform_ref_label"] == "Voie 7"
    assert feature["properties"]["platform_label"] == "Voie 7"


def test_run_executes_pipeline_stages_in_order_and_creates_directories(
    monkeypatch, tmp_path
) -> None:
    settings = Settings(
        countries=("lu",),
        output_dir=tmp_path / "data",
        script_dir=tmp_path,
    )
    pipeline = GeneratorPipeline(settings, Console(use_color=False))
    calls: list[object] = []

    monkeypatch.setattr(
        "generator.pipeline.check_required_tools",
        lambda tool_names: calls.append(("check_required_tools", list(tool_names))),
    )
    monkeypatch.setattr(
        "generator.pipeline.require_existing_file",
        lambda path, description: path,
    )
    monkeypatch.setattr(
        "generator.pipeline.log_pipeline_start",
        lambda console, current_settings: calls.append(
            ("log_pipeline_start", current_settings.output_dir)
        ),
    )
    monkeypatch.setattr(
        "generator.pipeline.log_pipeline_complete",
        lambda console, total_start: calls.append(
            ("log_pipeline_complete", total_start)
        ),
    )
    monkeypatch.setattr("generator.pipeline.current_time", lambda: 42.0)

    for stage_name in (
        "download",
        "filter",
        "merge",
        "convert_shapefiles",
        "create_indexes",
        "convert_geojson",
        "build_platform_reference_layer",
        "extract_routes",
        "generate_vector_tiles",
        "convert_geopackage",
        "print_summary",
    ):
        setattr(
            pipeline,
            stage_name,
            MethodType(lambda self, name=stage_name: calls.append(name), pipeline),
        )

    pipeline.run()

    assert settings.sources_dir.is_dir()
    assert settings.overpass_cache_dir.is_dir()
    assert settings.filtered_sources_dir.is_dir()
    assert settings.shapefile_dir.is_dir()
    assert settings.geojson_dir.is_dir()
    assert settings.deliverables_dir.is_dir()
    assert settings.intermediate_tiles_dir.is_dir()
    assert calls == [
        ("check_required_tools", ["osmium", "ogr2ogr", "tippecanoe", "tile-join"]),
        ("log_pipeline_start", settings.output_dir),
        "download",
        "filter",
        "merge",
        "convert_shapefiles",
        "create_indexes",
        "convert_geojson",
        "build_platform_reference_layer",
        "extract_routes",
        "generate_vector_tiles",
        "convert_geopackage",
        "print_summary",
        ("log_pipeline_complete", 42.0),
    ]


def test_run_generation_stages_preserves_declared_stage_order(tmp_path) -> None:
    pipeline = GeneratorPipeline(
        Settings(countries=("lu",), output_dir=tmp_path / "data", script_dir=tmp_path),
        Console(use_color=False),
    )
    calls: list[str] = []

    for stage_name in (
        "download",
        "filter",
        "merge",
        "convert_shapefiles",
        "create_indexes",
        "convert_geojson",
        "build_platform_reference_layer",
        "extract_routes",
        "generate_vector_tiles",
        "convert_geopackage",
        "print_summary",
    ):
        setattr(
            pipeline,
            stage_name,
            MethodType(lambda self, name=stage_name: calls.append(name), pipeline),
        )

    pipeline._run_generation_stages()

    assert calls == [
        "download",
        "filter",
        "merge",
        "convert_shapefiles",
        "create_indexes",
        "convert_geojson",
        "build_platform_reference_layer",
        "extract_routes",
        "generate_vector_tiles",
        "convert_geopackage",
        "print_summary",
    ]


def test_generate_vector_tiles_runs_expected_commands_in_order(
    monkeypatch, tmp_path
) -> None:
    settings = Settings(
        countries=("lu",),
        output_dir=tmp_path / "data",
        script_dir=tmp_path,
    )
    settings.output_dir.mkdir(parents=True)
    settings.intermediate_tiles_dir.mkdir(parents=True, exist_ok=True)
    settings.deliverables_dir.mkdir(parents=True, exist_ok=True)
    pipeline = GeneratorPipeline(settings, Console(use_color=False))

    artifacts = type(
        "Artifacts",
        (),
        {
            "merged_mbtiles": settings.deliverables_dir
            / "lux-railway-map-overlay.mbtiles",
            "lines_mbtiles": settings.intermediate_tiles_dir / "lines.mbtiles",
            "stations_mbtiles": settings.intermediate_tiles_dir / "stations.mbtiles",
            "detail_mbtiles": settings.intermediate_tiles_dir / "detail.mbtiles",
        },
    )()
    calls: list[object] = []

    monkeypatch.setattr(
        "generator.pipeline.build_tile_artifacts",
        lambda _intermediate_tiles_dir, _deliverables_dir: artifacts,
    )
    monkeypatch.setattr(
        "generator.pipeline.build_tippecanoe_command",
        lambda geojson_dir, output_path, layer_specs, extra_args: [
            "tippecanoe",
            output_path.name,
            *extra_args,
        ],
    )
    monkeypatch.setattr(
        "generator.pipeline.build_tile_join_command",
        lambda current_artifacts: [
            "tile-join",
            current_artifacts.merged_mbtiles.name,
            current_artifacts.lines_mbtiles.name,
            current_artifacts.stations_mbtiles.name,
            current_artifacts.detail_mbtiles.name,
        ],
    )

    def fake_run_command(command: list[str]) -> None:
        calls.append(command)
        if command[0] == "tile-join":
            artifacts.merged_mbtiles.write_bytes(b"1234")

    def fake_run_commands_parallel(commands: list[list[str]], **kwargs) -> None:
        for cmd in commands:
            calls.append(cmd)

    monkeypatch.setattr("generator.pipeline.run_command", fake_run_command)
    monkeypatch.setattr(
        "generator.pipeline.run_commands_parallel", fake_run_commands_parallel
    )
    monkeypatch.setattr(
        "generator.pipeline.cleanup_intermediate_tiles",
        lambda current_artifacts: calls.append(("cleanup", current_artifacts)),
    )
    monkeypatch.setattr(pipeline, "_start_step", lambda message: 12.0)

    pipeline.generate_vector_tiles()

    assert calls == [
        [
            "tippecanoe",
            "lines.mbtiles",
            "-r1",
            "--no-tile-size-limit",
            "--no-feature-limit",
        ],
        [
            "tippecanoe",
            "stations.mbtiles",
            "-r1",
            "--no-tile-size-limit",
        ],
        [
            "tippecanoe",
            "detail.mbtiles",
            "--drop-densest-as-needed",
            "--extend-zooms-if-still-dropping",
        ],
        [
            "tile-join",
            "lux-railway-map-overlay.mbtiles",
            "lines.mbtiles",
            "stations.mbtiles",
            "detail.mbtiles",
        ],
        ("cleanup", artifacts),
    ]


def test_extract_routes_fails_by_default_when_overpass_unavailable(
    monkeypatch, tmp_path
) -> None:
    output_dir = tmp_path / "data"
    geojson_dir = output_dir / "intermediate" / "geojson"
    geojson_dir.mkdir(parents=True)
    (geojson_dir / "railway_stations.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": []}),
        encoding="utf-8",
    )

    pipeline = GeneratorPipeline(
        Settings(countries=("lu",), output_dir=output_dir, script_dir=tmp_path),
        Console(use_color=False),
    )

    monkeypatch.setattr(
        "generator.pipeline.download_overpass",
        lambda query, output_path, api_urls: (_ for _ in ()).throw(
            urllib.error.URLError("overpass down")
        ),
    )

    with pytest.raises(PipelineError, match=r"Overpass API query failed"):
        pipeline.extract_routes()


def test_extract_routes_can_soft_fail_when_missing_routes_are_allowed(
    monkeypatch, tmp_path
) -> None:
    output_dir = tmp_path / "data"
    geojson_dir = output_dir / "intermediate" / "geojson"
    geojson_dir.mkdir(parents=True)
    (geojson_dir / "railway_stations.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": []}),
        encoding="utf-8",
    )

    pipeline = GeneratorPipeline(
        Settings(
            countries=("lu",),
            output_dir=output_dir,
            script_dir=tmp_path,
            allow_missing_routes=True,
        ),
        Console(use_color=False),
    )

    monkeypatch.setattr(
        "generator.pipeline.download_overpass",
        lambda query, output_path, api_urls: (_ for _ in ()).throw(
            urllib.error.URLError("overpass down")
        ),
    )

    pipeline.extract_routes()

    assert json.loads(
        (geojson_dir / "railway_routes.geojson").read_text(encoding="utf-8")
    ) == {"type": "FeatureCollection", "features": []}
    assert json.loads(
        (geojson_dir / "railway_routes_display.geojson").read_text(encoding="utf-8")
    ) == {"type": "FeatureCollection", "features": []}
