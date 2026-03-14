from __future__ import annotations

from generator.pipeline_tiles import (
    build_tile_artifacts,
    build_tile_join_command,
    build_tippecanoe_command,
    cleanup_intermediate_tiles,
)


def test_build_tile_artifacts_uses_expected_output_names(tmp_path) -> None:
    artifacts = build_tile_artifacts(
        tmp_path / "intermediate" / "tiles", tmp_path / "out"
    )

    assert (
        artifacts.merged_mbtiles == tmp_path / "out" / "lux-railway-map-overlay.mbtiles"
    )
    assert (
        artifacts.lines_mbtiles == tmp_path / "intermediate" / "tiles" / "lines.mbtiles"
    )
    assert (
        artifacts.stations_mbtiles
        == tmp_path / "intermediate" / "tiles" / "stations.mbtiles"
    )
    assert (
        artifacts.detail_mbtiles
        == tmp_path / "intermediate" / "tiles" / "detail.mbtiles"
    )


def test_build_tippecanoe_command_includes_common_flags_and_layers(tmp_path) -> None:
    command = build_tippecanoe_command(
        tmp_path,
        tmp_path / "lines.mbtiles",
        (("railway_lines", "railway_lines", 2),),
        ["-r1", "--no-feature-limit"],
    )

    assert command[:6] == [
        "tippecanoe",
        "-o",
        str(tmp_path / "lines.mbtiles"),
        "--force",
        "--maximum-zoom=14",
        "--no-tile-compression",
    ]
    assert "-r1" in command
    assert "--no-feature-limit" in command
    assert command[-1] == (
        f'-L{{"file":"{tmp_path / "railway_lines.geojson"}", '
        '"layer":"railway_lines", "minzoom":2}'
    )


def test_build_tile_join_command_uses_all_intermediate_tiles(tmp_path) -> None:
    artifacts = build_tile_artifacts(
        tmp_path / "intermediate" / "tiles", tmp_path / "out"
    )

    assert build_tile_join_command(artifacts) == [
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


def test_cleanup_intermediate_tiles_removes_only_intermediate_outputs(tmp_path) -> None:
    artifacts = build_tile_artifacts(
        tmp_path / "intermediate" / "tiles", tmp_path / "out"
    )
    artifacts.lines_mbtiles.parent.mkdir(parents=True)
    artifacts.merged_mbtiles.parent.mkdir(parents=True)
    artifacts.lines_mbtiles.write_bytes(b"1")
    artifacts.stations_mbtiles.write_bytes(b"2")
    artifacts.detail_mbtiles.write_bytes(b"3")
    artifacts.merged_mbtiles.write_bytes(b"4")

    cleanup_intermediate_tiles(artifacts)

    assert not artifacts.lines_mbtiles.exists()
    assert not artifacts.stations_mbtiles.exists()
    assert not artifacts.detail_mbtiles.exists()
    assert artifacts.merged_mbtiles.exists()
