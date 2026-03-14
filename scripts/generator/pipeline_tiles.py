from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from generator.pipeline_support import tippecanoe_layer_arg


@dataclass(frozen=True)
class TileArtifacts:
    merged_mbtiles: Path
    lines_mbtiles: Path
    stations_mbtiles: Path
    detail_mbtiles: Path


def build_tile_artifacts(
    intermediate_tiles_dir: Path,
    deliverables_dir: Path,
) -> TileArtifacts:
    return TileArtifacts(
        merged_mbtiles=deliverables_dir / "lux-railway-map-overlay.mbtiles",
        lines_mbtiles=intermediate_tiles_dir / "lines.mbtiles",
        stations_mbtiles=intermediate_tiles_dir / "stations.mbtiles",
        detail_mbtiles=intermediate_tiles_dir / "detail.mbtiles",
    )


def build_tippecanoe_command(
    geojson_dir: Path,
    output_path: Path,
    layer_specs: tuple[tuple[str, str, int], ...],
    extra_args: list[str],
) -> list[str]:
    return [
        "tippecanoe",
        "-o",
        str(output_path),
        "--force",
        "--maximum-zoom=14",
        "--no-tile-compression",
        *extra_args,
        *[
            tippecanoe_layer_arg(geojson_dir, file_stem, layer_name, minzoom)
            for file_stem, layer_name, minzoom in layer_specs
        ],
    ]


def build_tile_join_command(artifacts: TileArtifacts) -> list[str]:
    return [
        "tile-join",
        "-o",
        str(artifacts.merged_mbtiles),
        "--force",
        "--no-tile-compression",
        "--no-tile-size-limit",
        "--name=Luxembourg Railway Infrastructure Vector Tile Overlay",
        "--attribution=© OpenStreetMap contributors",
        str(artifacts.lines_mbtiles),
        str(artifacts.stations_mbtiles),
        str(artifacts.detail_mbtiles),
    ]


def cleanup_intermediate_tiles(artifacts: TileArtifacts) -> None:
    artifacts.lines_mbtiles.unlink(missing_ok=True)
    artifacts.stations_mbtiles.unlink(missing_ok=True)
    artifacts.detail_mbtiles.unlink(missing_ok=True)
