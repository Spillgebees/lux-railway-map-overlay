from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

GEOFABRIK_URLS = {
    "lu": "https://download.geofabrik.de/europe/luxembourg-latest.osm.pbf",
    "be": "https://download.geofabrik.de/europe/belgium-latest.osm.pbf",
    "de": "https://download.geofabrik.de/europe/germany-latest.osm.pbf",
    "fr": "https://download.geofabrik.de/europe/france-latest.osm.pbf",
}

COUNTRY_NAMES = {
    "lu": "Luxembourg",
    "be": "Belgium",
    "de": "Germany",
    "fr": "France",
}

COUNTRY_BBOX = {
    "lu": "49.44,5.73,50.18,6.53",
    "be": "49.49,2.54,51.51,6.41",
    "de": "47.27,5.87,55.10,15.04",
    "fr": "41.36,-5.14,51.09,9.56",
}

SUPPORTED_COUNTRIES = tuple(GEOFABRIK_URLS.keys())
SUPPORTED_COUNTRIES_TEXT = ", ".join(SUPPORTED_COUNTRIES)


@dataclass(frozen=True)
class Settings:
    countries: tuple[str, ...]
    output_dir: Path
    script_dir: Path
    allow_missing_routes: bool = False

    @property
    def cache_dir(self) -> Path:
        return self.output_dir / "cache"

    @property
    def sources_dir(self) -> Path:
        return self.cache_dir / "sources"

    @property
    def filtered_sources_dir(self) -> Path:
        return self.intermediate_dir / "sources"

    @property
    def overpass_cache_dir(self) -> Path:
        return self.cache_dir / "overpass"

    @property
    def overpass_routes_path(self) -> Path:
        return self.overpass_cache_dir / "overpass_routes.json"

    @property
    def intermediate_dir(self) -> Path:
        return self.output_dir / "intermediate"

    @property
    def shapefile_dir(self) -> Path:
        return self.intermediate_dir / "shp"

    @property
    def geojson_dir(self) -> Path:
        return self.intermediate_dir / "geojson"

    @property
    def intermediate_tiles_dir(self) -> Path:
        return self.intermediate_dir / "tiles"

    @property
    def merged_pbf_path(self) -> Path:
        return self.intermediate_dir / "railway-merged.osm.pbf"

    @property
    def deliverables_dir(self) -> Path:
        return self.output_dir / "out"

    @property
    def mbtiles_path(self) -> Path:
        return self.deliverables_dir / "lux-railway-map-overlay.mbtiles"

    @property
    def geopackage_path(self) -> Path:
        return self.deliverables_dir / "railway-data.gpkg"

    @property
    def osmconf_path(self) -> Path:
        return self.script_dir / "osmconf.ini"
