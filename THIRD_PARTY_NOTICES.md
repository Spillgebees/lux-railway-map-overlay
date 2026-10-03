# Third-Party Notices

This repository contains original project code and styles licensed under the MIT License. It also depends on third-party software, fonts, and data sources with their own licenses and attribution requirements.

This file is a practical notice summary for this repository and its standard build/runtime flow. It is not a substitute for reviewing the upstream license texts when preparing a production release.

## Code and Runtime Dependencies

### Martin

- Project: https://github.com/maplibre/martin
- Usage here: vector tile server binary included in the tile image
- License: dual-licensed under MIT or Apache License 2.0

### MapLibre font-maker

- Project: https://github.com/maplibre/font-maker
- Usage here: generates self-hosted glyph PBFs during the tile image build
- License: BSD 3-Clause

### Tippecanoe

- Project: https://github.com/felt/tippecanoe
- Usage here: generates and merges MBTiles in the generator image
- License: BSD 2-Clause

### nginx

- Project: https://nginx.org/
- Usage here: reverse proxy in front of Martin in the tile image
- License: BSD 2-Clause

### osmium-tool

- Project: https://github.com/osmcode/osmium-tool
- Usage here: filters and merges OSM extracts in the generator image
- License: GPL-3.0
- Note: the generator calls osmium as a separate command-line program. It is not linked into project code and is not included in the tile image.

### GDAL

- Project: https://gdal.org/
- Usage here: `ogr2ogr` converts OSM data to GeoJSON and GeoPackage in the generator image
- License: MIT

### Shapely

- Project: https://github.com/shapely/shapely
- Usage here: geometry processing in the Python generator
- License: BSD 3-Clause
- Note: Shapely uses GEOS, which is available under LGPL 2.1

## Fonts

### IBM Plex Sans

- Project: https://github.com/IBM/plex
- Usage here: self-hosted MapLibre glyphs
- License: SIL Open Font License 1.1

### Noto Sans

- Project: https://github.com/google/fonts/tree/main/ofl/notosans
- Usage here: self-hosted MapLibre glyphs
- License: SIL Open Font License 1.1

## Data and Attribution

### OpenStreetMap

- Project: https://www.openstreetmap.org/
- Usage here: source data for railway infrastructure and route extraction
- License: Open Database License (ODbL) 1.0
- Required attribution: © OpenStreetMap contributors

The generated database artifacts and tile outputs remain subject to OpenStreetMap's data license obligations. If you publicly distribute database-form outputs or operate a public service backed directly by them, review your ODbL compliance obligations before release.

### Geofabrik Extracts

- Project: https://download.geofabrik.de/
- Usage here: country extract download source for OSM data
- License context: Geofabrik distributes OpenStreetMap-derived extracts; the underlying data remains subject to ODbL

### Overpass API

- Project: https://overpass-api.de/
- Usage here: route relation queries used during data generation
- License context: returned data is derived from OpenStreetMap and remains subject to ODbL

## Art Assets

### Tunnel Icon

- File: styles/symbols/tunnel.svg
- Usage here: tunnel entrance sprite
- Source note: based on Maki by Mapbox, adapted for this project
- License: CC0 / public domain as noted in the asset file

### Tram Stop Icon

- File: styles/symbols/tram-stop.svg
- Usage here: tram stop sprite
- Source note: original work for this project
- License: MIT (same as project styles)

### Subway Entrance Icon

- File: styles/symbols/subway-entrance.svg
- Usage here: subway entrance sprite
- Source note: original work for this project
- License: MIT (same as project styles)

## Operational Notes

- The repository avoids GPL dependencies in its own code and in the tile image. The generator image includes osmium-tool (GPL-3.0) as a standalone program.
- Container base images and distribution packages may introduce additional transitive license notices. For production releases, generate an SBOM or equivalent dependency inventory for the exact images you publish.
- Keep the OpenStreetMap attribution visible on maps, exports, and user-facing experiences that use the generated data.
