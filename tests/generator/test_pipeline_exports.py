from __future__ import annotations

from generator.pipeline_exports import (
    build_geopackage_command,
    export_vector_layers,
)


def test_export_vector_layers_builds_expected_geojson_outputs(
    monkeypatch, tmp_path
) -> None:
    calls: list[dict[str, object]] = []
    messages: list[str] = []

    monkeypatch.setattr(
        "generator.pipeline_exports.ogr2ogr",
        lambda output_path, source_path, output_format, sql, **kwargs: calls.append(
            {
                "output_path": output_path,
                "source_path": source_path,
                "output_format": output_format,
                "sql": sql,
                **kwargs,
            }
        ),
    )

    export_vector_layers(
        tmp_path,
        tmp_path / "merged.osm.pbf",
        (("railway_lines", "SELECT * FROM lines", []),),
        output_format="GeoJSON",
        file_suffix=".geojson",
        extra_args=["-lco", "RFC7946=YES"],
        target_srs="EPSG:4326",
        osmconf_path=tmp_path / "osmconf.ini",
        logger=messages.append,
    )

    assert messages == ["railway_lines"]
    assert calls == [
        {
            "output_path": tmp_path / "railway_lines.geojson",
            "source_path": tmp_path / "merged.osm.pbf",
            "output_format": "GeoJSON",
            "sql": "SELECT * FROM lines",
            "extra_args": ["-lco", "RFC7946=YES"],
            "target_srs": "EPSG:4326",
            "osmconf_path": tmp_path / "osmconf.ini",
        }
    ]


def test_export_vector_layers_merges_per_layer_extra_args(
    monkeypatch, tmp_path
) -> None:
    calls: list[dict[str, object]] = []
    messages: list[str] = []

    monkeypatch.setattr(
        "generator.pipeline_exports.ogr2ogr",
        lambda output_path, source_path, output_format, sql, **kwargs: calls.append(
            {
                "output_path": output_path,
                "source_path": source_path,
                "output_format": output_format,
                "sql": sql,
                **kwargs,
            }
        ),
    )

    export_vector_layers(
        tmp_path,
        tmp_path / "merged.osm.pbf",
        (("railway_tunnel", "SELECT * FROM lines", ["-dialect", "sqlite"]),),
        output_format="GeoJSON",
        file_suffix=".geojson",
        extra_args=["-lco", "RFC7946=YES"],
        target_srs="EPSG:4326",
        osmconf_path=tmp_path / "osmconf.ini",
        logger=messages.append,
    )

    assert messages == ["railway_tunnel"]
    assert calls == [
        {
            "output_path": tmp_path / "railway_tunnel.geojson",
            "source_path": tmp_path / "merged.osm.pbf",
            "output_format": "GeoJSON",
            "sql": "SELECT * FROM lines",
            "extra_args": ["-lco", "RFC7946=YES", "-dialect", "sqlite"],
            "target_srs": "EPSG:4326",
            "osmconf_path": tmp_path / "osmconf.ini",
        }
    ]


def test_build_geopackage_command_uses_expected_arguments(tmp_path) -> None:
    assert build_geopackage_command(
        tmp_path / "railway-data.gpkg",
        tmp_path / "merged.osm.pbf",
        tmp_path / "osmconf.ini",
        "railway_lines",
        "SELECT * FROM lines",
        ["-append"],
    ) == [
        "ogr2ogr",
        "-f",
        "GPKG",
        str(tmp_path / "railway-data.gpkg"),
        str(tmp_path / "merged.osm.pbf"),
        "--config",
        "OSM_CONFIG_FILE",
        str(tmp_path / "osmconf.ini"),
        "-t_srs",
        "EPSG:4326",
        "-sql",
        "SELECT * FROM lines",
        "-nln",
        "railway_lines",
        "-append",
    ]
