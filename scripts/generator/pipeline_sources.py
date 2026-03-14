from __future__ import annotations

import shutil
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from generator.pipeline_support import PipelineError


def source_filename(url: str) -> str:
    return Path(urllib.parse.urlparse(url).path).name


def source_download_path(sources_dir: Path, url: str) -> Path:
    return sources_dir / source_filename(url)


def filtered_source_path(filtered_sources_dir: Path, country_code: str) -> Path:
    return filtered_sources_dir / f"{country_code}-railway.osm.pbf"


def build_filter_command(input_path: Path, output_path: Path) -> list[str]:
    return [
        "osmium",
        "tags-filter",
        str(input_path),
        "nwr/railway",
        "nwr/disused:railway",
        "nwr/abandoned:railway",
        "nwr/razed:railway",
        "nwr/construction:railway",
        "nwr/proposed:railway",
        "-o",
        str(output_path),
        "--overwrite",
    ]


def build_merge_command(input_paths: list[Path], output_path: Path) -> list[str]:
    return [
        "osmium",
        "merge",
        *[str(path) for path in input_paths],
        "-o",
        str(output_path),
        "--overwrite",
    ]


def download_sources(
    countries: list[str],
    sources_dir: Path,
    country_urls: dict[str, str],
    country_names: dict[str, str],
    *,
    downloader,
    info,
    warn,
    skip_codes: frozenset[str] = frozenset(),
) -> None:
    tasks = []
    for code in countries:
        if code in skip_codes:
            warn(f"Skipping {country_names[code]} - filtered data already cached")
            continue

        url = country_urls[code]
        filename = source_filename(url)
        output_path = source_download_path(sources_dir, url)

        if output_path.exists() and output_path.stat().st_size > 0:
            warn(f"Skipping {country_names[code]} - {filename} already exists")
            continue

        tasks.append((code, url, filename, output_path))

    if not tasks:
        return

    def _download_one(code, url, filename, output_path):
        output_path.unlink(missing_ok=True)
        info(f"Downloading {country_names[code]} ({filename})...")
        try:
            downloader(url, output_path)
        except urllib.error.URLError as error:
            output_path.unlink(missing_ok=True)
            raise PipelineError(
                f"Failed to download {country_names[code]}: {error.reason}"
            ) from error
        info(f"Downloaded {country_names[code]}")

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(_download_one, *task): task for task in tasks}
        for future in as_completed(futures):
            future.result()


def filter_sources(
    countries: list[str],
    source_cache_dir: Path,
    filtered_sources_dir: Path,
    country_urls: dict[str, str],
    country_names: dict[str, str],
    *,
    runner,
    info,
    warn,
    size_formatter,
) -> None:
    filtered_sources_dir.mkdir(parents=True, exist_ok=True)

    to_filter = []
    for code in countries:
        output_path = filtered_source_path(filtered_sources_dir, code)
        if output_path.exists() and output_path.stat().st_size > 0:
            warn(f"Skipping {country_names[code]} - {output_path.name} already exists")
            continue
        to_filter.append(code)

    if not to_filter:
        return

    def _filter_one(code):
        input_path = source_download_path(source_cache_dir, country_urls[code])
        output_path = filtered_source_path(filtered_sources_dir, code)

        if not input_path.exists():
            raise PipelineError(f"Source file not found: {input_path}")

        info(f"Filtering {country_names[code]}...")
        runner(build_filter_command(input_path, output_path))
        info(
            f"Filtered {country_names[code]} -> {size_formatter(output_path.stat().st_size)}"
        )

    with ThreadPoolExecutor(max_workers=len(to_filter)) as executor:
        futures = {executor.submit(_filter_one, code): code for code in to_filter}
        for future in as_completed(futures):
            future.result()


def merge_sources(
    countries: list[str],
    filtered_sources_dir: Path,
    merged_path: Path,
    country_names: dict[str, str],
    *,
    runner,
    info,
    size_formatter,
    copy_file=shutil.copyfile,
) -> Path:
    if len(countries) == 1:
        code = countries[0]
        source_path = filtered_source_path(filtered_sources_dir, code)
        info(f"Single country - copying {country_names[code]} as merged file")
        copy_file(source_path, merged_path)
    else:
        input_paths = [
            filtered_source_path(filtered_sources_dir, code) for code in countries
        ]
        info(f"Merging {len(countries)} countries...")
        runner(build_merge_command(input_paths, merged_path))

    info(f"Merged file: {size_formatter(merged_path.stat().st_size)}")
    return merged_path
