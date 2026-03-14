from __future__ import annotations

from pathlib import Path

from generator.pipeline_support import ogr2ogr


def export_vector_layers(
    output_dir: Path,
    merged_path: Path,
    layer_specs,
    *,
    output_format: str,
    file_suffix: str,
    extra_args: list[str],
    target_srs: str,
    osmconf_path: Path,
    logger,
) -> None:
    for layer_name, sql, layer_extra_args in layer_specs:
        logger(layer_name)
        combined_args = list(extra_args) + layer_extra_args
        ogr2ogr(
            output_dir / f"{layer_name}{file_suffix}",
            merged_path,
            output_format,
            sql,
            extra_args=combined_args,
            target_srs=target_srs,
            osmconf_path=osmconf_path,
        )


def build_geopackage_command(
    gpkg_path: Path,
    merged_path: Path,
    osmconf_path: Path,
    layer_name: str,
    sql: str,
    extra_args: list[str],
) -> list[str]:
    return [
        "ogr2ogr",
        "-f",
        "GPKG",
        str(gpkg_path),
        str(merged_path),
        "--config",
        "OSM_CONFIG_FILE",
        str(osmconf_path),
        "-t_srs",
        "EPSG:4326",
        "-sql",
        sql,
        "-nln",
        layer_name,
        *extra_args,
    ]
