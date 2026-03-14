from __future__ import annotations

import shutil
import subprocess
import time

from generator.config import COUNTRY_NAMES, Settings
from generator.console import Console, format_elapsed
from generator.pipeline_support import print_summary_file


def current_time() -> float:
    return time.time()


def log_pipeline_start(console: Console, settings: Settings) -> None:
    console.step("lux-railway-map-overlay data generation")
    console.info(f"Countries: {' '.join(settings.countries)}")
    console.info(f"Output directory: {settings.output_dir}")


def log_pipeline_complete(console: Console, total_start: float) -> None:
    console.info(f"Total elapsed time: {format_elapsed(total_start)}")
    console.info("Data attribution: (c) OpenStreetMap contributors (ODbL)")


def start_step(console: Console, message: str) -> float:
    console.step(message)
    return current_time()


def print_pipeline_summary(
    settings: Settings,
    size_formatter,
    *,
    tool_lookup=shutil.which,
    command_runner=subprocess.run,
) -> None:
    print("Countries:", " ".join(COUNTRY_NAMES[code] for code in settings.countries))
    print(f"Output directory: {settings.output_dir}")
    print()
    print("Generated files:")

    print_summary_file(
        settings.merged_pbf_path,
        "intermediate/railway-merged.osm.pbf",
        size_formatter,
    )

    for shapefile in sorted(settings.shapefile_dir.glob("*.shp")):
        print_summary_file(
            shapefile,
            f"intermediate/shp/{shapefile.name}",
            size_formatter,
        )

    for geojson_file in sorted(settings.geojson_dir.glob("*.geojson")):
        print_summary_file(
            geojson_file,
            f"intermediate/geojson/{geojson_file.name}",
            size_formatter,
        )

    print_summary_file(
        settings.mbtiles_path,
        "out/lux-railway-map-overlay.mbtiles",
        size_formatter,
    )
    print_summary_file(
        settings.geopackage_path,
        "out/railway-data.gpkg",
        size_formatter,
    )
    print()

    if tool_lookup("ogrinfo") and settings.geopackage_path.exists():
        print("GeoPackage layers:")
        result = command_runner(
            ["ogrinfo", "-so", str(settings.geopackage_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if line and line[0].isdigit() and ":" in line:
                print(f"  {line}")
        print()
