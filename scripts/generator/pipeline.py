from __future__ import annotations

import json
import shutil
import urllib.error
from pathlib import Path

from generator.config import COUNTRY_BBOX, COUNTRY_NAMES, GEOFABRIK_URLS, Settings
from generator.console import Console, format_bytes, format_elapsed
from generator.layer_specs import (
    DETAIL_TILE_LAYER_SPECS,
    GEOJSON_LAYER_SPECS,
    GPKG_LAYER_SPECS,
    LINE_TILE_LAYER_SPECS,
    SHAPEFILE_LAYER_SPECS,
    STATION_TILE_LAYER_SPECS,
)
from generator.platform_references import build_platform_reference_feature_collection
from generator.pipeline_exports import (
    build_geopackage_command,
    export_vector_layers,
)
from generator.pipeline_reporting import (
    current_time,
    log_pipeline_complete,
    log_pipeline_start,
    print_pipeline_summary,
    start_step,
)
from generator.pipeline_sources import download_sources, filter_sources, merge_sources
from generator.pipeline_support import (
    PipelineError,
    check_required_tools,
    download_file,
    download_overpass,
    load_geojson,
    ogr2ogr,
    require_existing_file,
    run_command,
    run_commands_parallel,
    write_empty_geojson,
)
from generator.pipeline_tiles import (
    build_tile_artifacts,
    build_tile_join_command,
    build_tippecanoe_command,
    cleanup_intermediate_tiles,
)
from generator.routes import write_routes_geojson


class GeneratorPipeline:
    REQUIRED_TOOLS = ["osmium", "ogr2ogr", "tippecanoe", "tile-join"]
    VECTOR_TILE_PASSES = (
        (
            "Pass 1: Lines (track geometry at all zooms, no dropping)...",
            "lines_mbtiles",
            LINE_TILE_LAYER_SPECS,
            ["-r1", "--no-tile-size-limit", "--no-feature-limit"],
        ),
        (
            "Pass 2: Stations & routes (no dropping)...",
            "stations_mbtiles",
            STATION_TILE_LAYER_SPECS,
            ["-r1", "--no-tile-size-limit"],
        ),
        (
            "Pass 3: Detail layers (crossings, platforms, signals, etc.)...",
            "detail_mbtiles",
            DETAIL_TILE_LAYER_SPECS,
            ["--drop-densest-as-needed", "--extend-zooms-if-still-dropping"],
        ),
    )

    OVERPASS_API_URLS = (
        "https://overpass-api.de/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    )

    def __init__(self, settings: Settings, console: Console) -> None:
        self.settings = settings
        self.console = console

    def run(self) -> None:
        total_start = self._timer_start()

        check_required_tools(self.REQUIRED_TOOLS)
        self._osmconf_path = require_existing_file(
            self.settings.osmconf_path, "osmconf.ini"
        )

        log_pipeline_start(self.console, self.settings)

        for directory in (
            self.settings.sources_dir,
            self.settings.overpass_cache_dir,
            self.settings.filtered_sources_dir,
            self.settings.shapefile_dir,
            self.settings.geojson_dir,
            self.settings.intermediate_tiles_dir,
            self.settings.deliverables_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        self._run_generation_stages()

        log_pipeline_complete(self.console, total_start)

    def _run_generation_stages(self) -> None:
        for stage in (
            self.download,
            self.filter,
            self.merge,
            self.convert_shapefiles,
            self.create_indexes,
            self.convert_geojson,
            self.build_platform_reference_layer,
            self.extract_routes,
            self.generate_vector_tiles,
            self.convert_geopackage,
            self.print_summary,
        ):
            stage()

    def download(self) -> None:
        step_start = self._start_step("Downloading PBF files from Geofabrik")

        # skip downloading countries whose filtered railway PBFs are already
        # cached from a previous run (e.g., restored by CI cache)
        already_filtered = frozenset(
            code
            for code in self.settings.countries
            if (self.settings.filtered_sources_dir / f"{code}-railway.osm.pbf").exists()
        )

        download_sources(
            self.settings.countries,
            self.settings.sources_dir,
            GEOFABRIK_URLS,
            COUNTRY_NAMES,
            downloader=download_file,
            info=self.console.info,
            warn=self.console.warn,
            skip_codes=already_filtered,
        )

        self.console.info(f"Download complete ({format_elapsed(step_start)})")

    def filter(self) -> None:
        step_start = self._start_step("Filtering railway features")

        filter_sources(
            self.settings.countries,
            self.settings.sources_dir,
            self.settings.filtered_sources_dir,
            GEOFABRIK_URLS,
            COUNTRY_NAMES,
            runner=run_command,
            info=self.console.info,
            warn=self.console.warn,
            size_formatter=format_bytes,
        )

        self.console.info(f"Filter complete ({format_elapsed(step_start)})")

    def merge(self) -> None:
        step_start = self._start_step("Merging filtered files")

        merge_sources(
            self.settings.countries,
            self.settings.filtered_sources_dir,
            self.settings.merged_pbf_path,
            COUNTRY_NAMES,
            runner=run_command,
            info=self.console.info,
            size_formatter=format_bytes,
            copy_file=shutil.copyfile,
        )

        self.console.info(f"Merge complete ({format_elapsed(step_start)})")

    def convert_shapefiles(self) -> None:
        step_start = self._start_step("Converting to shapefiles (EPSG:3857)")
        merged_path = self.settings.merged_pbf_path

        for output_name, label, sql in SHAPEFILE_LAYER_SPECS:
            self.console.info(f"Extracting {label}...")
            ogr2ogr(
                self.settings.shapefile_dir / output_name,
                merged_path,
                "ESRI Shapefile",
                sql,
                extra_args=["-lco", "ENCODING=UTF-8", "-overwrite"],
                target_srs="EPSG:3857",
                osmconf_path=self._osmconf_path,
            )

        self.console.info(
            f"Shapefile conversion complete ({format_elapsed(step_start)})"
        )

    def create_indexes(self) -> None:
        step_start = self._start_step("Creating spatial indexes")

        if shutil.which("shapeindex") is None:
            self.console.warn("shapeindex not found - skipping spatial index creation")
            self.console.warn("Install Mapnik utilities for shapeindex support")
            return

        for shapefile in sorted(self.settings.shapefile_dir.glob("*.shp")):
            self.console.info(f"Indexing {shapefile.name}...")
            run_command(["shapeindex", str(shapefile)])

        self.console.info(
            f"Spatial index creation complete ({format_elapsed(step_start)})"
        )

    def convert_geojson(self) -> None:
        step_start = self._start_step("Converting to GeoJSON (EPSG:4326)")

        export_vector_layers(
            self.settings.geojson_dir,
            self.settings.merged_pbf_path,
            GEOJSON_LAYER_SPECS,
            output_format="GeoJSON",
            file_suffix=".geojson",
            extra_args=["-lco", "RFC7946=YES"],
            target_srs="EPSG:4326",
            osmconf_path=self._osmconf_path,
            logger=lambda layer_name: self.console.info(f"Extracting {layer_name}..."),
        )

        self.console.info(f"GeoJSON conversion complete ({format_elapsed(step_start)})")

    def build_platform_reference_layer(self) -> None:
        step_start = self._start_step("Building optional platform/quay reference layer")
        platforms_path = self.settings.geojson_dir / "railway_platforms.geojson"
        stations_path = self.settings.geojson_dir / "railway_stations.geojson"
        output_path = self.settings.geojson_dir / "railway_platform_refs.geojson"

        platform_data = load_geojson(platforms_path)
        station_data = load_geojson(stations_path)
        features, platform_count, stop_position_count = (
            build_platform_reference_feature_collection(platform_data, station_data)
        )

        output_path.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}),
            encoding="utf-8",
        )
        self.console.info(
            "Platform/quay references: "
            f"{len(features)} feature(s) "
            f"({platform_count} platform area labels, {stop_position_count} stop-position labels)"
        )
        self.console.info(
            f"Platform/quay reference layer complete ({format_elapsed(step_start)})"
        )

    def extract_routes(self) -> None:
        step_start = self._start_step("Extracting route relations (Overpass API)")
        routes_json = self.settings.overpass_routes_path
        routes_geojson = self.settings.geojson_dir / "railway_routes.geojson"
        routes_display_geojson = (
            self.settings.geojson_dir / "railway_routes_display.geojson"
        )
        stations_geojson = self.settings.geojson_dir / "railway_stations.geojson"
        bbox = COUNTRY_BBOX["lu"]

        if not self._ensure_route_response(
            routes_json,
            routes_geojson,
            routes_display_geojson,
            bbox,
        ):
            return

        self.console.info("Resolving route geometries...")
        feature_count, relation_count = write_routes_geojson(
            routes_json,
            routes_geojson,
            routes_display_geojson,
            stations_geojson,
            bbox,
        )
        deduplicated = relation_count - feature_count
        self.console.info(
            f"Extracted {feature_count} route(s) ({relation_count} relations, {deduplicated} deduplicated)"
        )
        self.console.info(f"Route extraction complete ({format_elapsed(step_start)})")

    def generate_vector_tiles(self) -> None:
        step_start = self._start_step("Generating vector tiles (.mbtiles)")

        artifacts = build_tile_artifacts(
            self.settings.intermediate_tiles_dir,
            self.settings.deliverables_dir,
        )

        self._run_vector_tile_passes(artifacts)

        self.console.info("Merging lines + stations + detail tiles...")
        run_command(build_tile_join_command(artifacts))

        cleanup_intermediate_tiles(artifacts)
        self.console.info("Cleaned up intermediate tile files")
        self.console.info(
            f"Vector tiles: {format_bytes(artifacts.merged_mbtiles.stat().st_size)}"
        )
        self.console.info(
            f"Vector tile generation complete ({format_elapsed(step_start)})"
        )

    def convert_geopackage(self) -> None:
        step_start = self._start_step("Converting to GeoPackage (EPSG:4326)")
        gpkg_path = self.settings.geopackage_path

        gpkg_path.unlink(missing_ok=True)

        self._export_geopackage_layers(gpkg_path)

        self.console.info(f"GeoPackage: {format_bytes(gpkg_path.stat().st_size)}")
        self.console.info(
            f"GeoPackage conversion complete ({format_elapsed(step_start)})"
        )

    def print_summary(self) -> None:
        self.console.step("Summary")
        print()
        print_pipeline_summary(self.settings, format_bytes)

    def _start_step(self, message: str) -> float:
        return start_step(self.console, message)

    def _timer_start(self) -> float:
        return current_time()

    def _ensure_route_response(
        self,
        routes_json: Path,
        routes_geojson: Path,
        routes_display_geojson: Path,
        bbox: str,
    ) -> bool:
        """Ensure route relation input exists before downstream geometry resolution.

        Cached responses are always preferred. Fresh Overpass failures are fatal by
        default so release automation cannot silently publish tiles without routes;
        local runs can opt into a soft-fail mode via the CLI.
        """
        if routes_json.exists():
            self.console.info(f"Using cached Overpass response ({routes_json})")
            return True

        self.console.info(
            f"Querying Overpass API for route relations (bbox: {bbox})..."
        )

        try:
            download_overpass(
                self._build_route_query(bbox),
                routes_json,
                self.OVERPASS_API_URLS,
            )
        except urllib.error.URLError as error:
            return self._handle_route_download_failure(
                error,
                routes_geojson,
                routes_display_geojson,
            )

        return True

    def _build_route_query(self, bbox: str) -> str:
        return (
            '[out:json][timeout:120];relation["route"~"train|tram|light_rail|subway"]('
            + bbox
            + ");(._;>;);out body;"
        )

    def _handle_route_download_failure(
        self,
        error: urllib.error.URLError,
        routes_geojson: Path,
        routes_display_geojson: Path,
    ) -> bool:
        """Handle Overpass failures according to the configured route strictness."""
        if not self.settings.allow_missing_routes:
            raise PipelineError(
                "Overpass API query failed during route extraction: "
                f"{error.reason}. Re-run with --allow-missing-routes only for local "
                "or manual builds where empty route layers are acceptable."
            ) from error

        self.console.warn("Overpass API query failed - skipping route extraction")
        self.console.warn(str(error.reason))
        if self._has_existing_route_outputs(routes_geojson, routes_display_geojson):
            self.console.warn("Preserving existing route GeoJSON and display GeoJSON")
            return False

        write_empty_geojson(routes_geojson)
        write_empty_geojson(routes_display_geojson)
        return False

    def _has_existing_route_outputs(
        self,
        routes_geojson: Path,
        routes_display_geojson: Path,
    ) -> bool:
        return (
            routes_geojson.exists()
            and routes_geojson.stat().st_size > 100
            and routes_display_geojson.exists()
            and routes_display_geojson.stat().st_size > 100
        )

    def _run_vector_tile_passes(self, artifacts) -> None:
        """Run the three tippecanoe passes in parallel since each reads disjoint
        GeoJSON inputs and writes to an independent output file.
        """
        for message, _, _, _ in self.VECTOR_TILE_PASSES:
            self.console.info(message)

        commands = [
            build_tippecanoe_command(
                self.settings.geojson_dir,
                getattr(artifacts, artifact_name),
                layer_specs,
                extra_args,
            )
            for _, artifact_name, layer_specs, extra_args in self.VECTOR_TILE_PASSES
        ]
        run_commands_parallel(commands)

    def _export_geopackage_layers(self, gpkg_path) -> None:
        """Append the configured GeoPackage layers in a fixed order."""
        for layer_name, sql, extra_args in GPKG_LAYER_SPECS:
            self.console.info(f"Adding layer: {layer_name}...")
            run_command(
                build_geopackage_command(
                    gpkg_path,
                    self.settings.merged_pbf_path,
                    self._osmconf_path,
                    layer_name,
                    sql,
                    extra_args,
                )
            )
