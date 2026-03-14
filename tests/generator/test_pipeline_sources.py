from __future__ import annotations

import urllib.error

import pytest

from generator.pipeline_support import PipelineError
from generator.pipeline_sources import (
    build_filter_command,
    build_merge_command,
    download_sources,
    filter_sources,
    filtered_source_path,
    merge_sources,
    source_download_path,
    source_filename,
)


def test_source_helpers_build_expected_paths(tmp_path) -> None:
    assert source_filename("https://example.test/data/luxembourg-latest.osm.pbf") == (
        "luxembourg-latest.osm.pbf"
    )
    assert source_download_path(
        tmp_path, "https://example.test/data/luxembourg-latest.osm.pbf"
    ) == (tmp_path / "luxembourg-latest.osm.pbf")
    assert filtered_source_path(tmp_path, "lu") == (tmp_path / "lu-railway.osm.pbf")


def test_build_filter_and_merge_commands_use_expected_arguments(tmp_path) -> None:
    assert build_filter_command(
        tmp_path / "luxembourg-latest.osm.pbf",
        tmp_path / "lu-railway.osm.pbf",
    ) == [
        "osmium",
        "tags-filter",
        str(tmp_path / "luxembourg-latest.osm.pbf"),
        "nwr/railway",
        "nwr/disused:railway",
        "nwr/abandoned:railway",
        "nwr/razed:railway",
        "nwr/construction:railway",
        "nwr/proposed:railway",
        "-o",
        str(tmp_path / "lu-railway.osm.pbf"),
        "--overwrite",
    ]
    assert build_merge_command(
        [tmp_path / "lu-railway.osm.pbf", tmp_path / "be-railway.osm.pbf"],
        tmp_path / "railway-merged.osm.pbf",
    ) == [
        "osmium",
        "merge",
        str(tmp_path / "lu-railway.osm.pbf"),
        str(tmp_path / "be-railway.osm.pbf"),
        "-o",
        str(tmp_path / "railway-merged.osm.pbf"),
        "--overwrite",
    ]


def test_download_sources_skips_existing_and_cleans_up_failed_download(
    tmp_path,
) -> None:
    info_messages: list[str] = []
    warn_messages: list[str] = []
    existing_path = tmp_path / "luxembourg-latest.osm.pbf"
    existing_path.write_bytes(b"already-there")

    def downloader(url: str, output_path) -> None:
        if "belgium" in url:
            output_path.write_bytes(b"partial")
            raise urllib.error.URLError("network down")

    with pytest.raises(
        PipelineError, match=r"Failed to download Belgium: network down"
    ):
        download_sources(
            ["lu", "be"],
            tmp_path,
            {
                "lu": "https://example.test/luxembourg-latest.osm.pbf",
                "be": "https://example.test/belgium-latest.osm.pbf",
            },
            {"lu": "Luxembourg", "be": "Belgium"},
            downloader=downloader,
            info=info_messages.append,
            warn=warn_messages.append,
        )

    assert warn_messages == [
        "Skipping Luxembourg - luxembourg-latest.osm.pbf already exists"
    ]
    assert info_messages == ["Downloading Belgium (belgium-latest.osm.pbf)..."]
    assert not (tmp_path / "belgium-latest.osm.pbf").exists()


def test_filter_sources_runs_command_and_reports_size(tmp_path) -> None:
    calls: list[list[str]] = []
    messages: list[str] = []
    input_path = tmp_path / "luxembourg-latest.osm.pbf"
    input_path.write_bytes(b"source")

    def runner(command: list[str]) -> None:
        calls.append(command)
        (tmp_path / "filtered").mkdir(exist_ok=True)
        (tmp_path / "filtered" / "lu-railway.osm.pbf").write_bytes(b"filtered-output")

    filter_sources(
        ["lu"],
        tmp_path,
        tmp_path / "filtered",
        {"lu": "https://example.test/luxembourg-latest.osm.pbf"},
        {"lu": "Luxembourg"},
        runner=runner,
        info=messages.append,
        warn=messages.append,
        size_formatter=lambda size: f"{size}B",
    )

    assert calls == [
        build_filter_command(input_path, tmp_path / "filtered" / "lu-railway.osm.pbf")
    ]
    assert messages == [
        "Filtering Luxembourg...",
        "Filtered Luxembourg -> 15B",
    ]


def test_merge_sources_copies_single_country_and_runs_merge_for_multiple(
    tmp_path,
) -> None:
    single_calls: list[object] = []
    (tmp_path / "lu-railway.osm.pbf").write_bytes(b"single-country")

    def copy_file(source, destination) -> None:
        single_calls.append((source, destination))
        destination.write_bytes(source.read_bytes())

    merge_sources(
        ["lu"],
        tmp_path,
        tmp_path / "railway-merged.osm.pbf",
        {"lu": "Luxembourg"},
        runner=lambda command: single_calls.append(command),
        info=lambda message: single_calls.append(message),
        size_formatter=lambda size: f"{size}B",
        copy_file=copy_file,
    )

    assert single_calls == [
        "Single country - copying Luxembourg as merged file",
        (tmp_path / "lu-railway.osm.pbf", tmp_path / "railway-merged.osm.pbf"),
        "Merged file: 14B",
    ]

    multi_calls: list[object] = []
    (tmp_path / "be-railway.osm.pbf").write_bytes(b"be")

    def runner(command: list[str]) -> None:
        multi_calls.append(command)
        (tmp_path / "railway-merged.osm.pbf").write_bytes(b"merged")

    merge_sources(
        ["lu", "be"],
        tmp_path,
        tmp_path / "railway-merged.osm.pbf",
        {"lu": "Luxembourg", "be": "Belgium"},
        runner=runner,
        info=lambda message: multi_calls.append(message),
        size_formatter=lambda size: f"{size}B",
    )

    assert multi_calls == [
        "Merging 2 countries...",
        build_merge_command(
            [tmp_path / "lu-railway.osm.pbf", tmp_path / "be-railway.osm.pbf"],
            tmp_path / "railway-merged.osm.pbf",
        ),
        "Merged file: 6B",
    ]
