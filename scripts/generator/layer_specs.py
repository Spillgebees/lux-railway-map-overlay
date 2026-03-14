from __future__ import annotations

# (output_filename, human_label, sql_query)
SHAPEFILE_LAYER_SPECS = (
    (
        "railway_lines.shp",
        "railway_lines (active rail, light_rail, tram, subway, narrow_gauge)",
        "SELECT * FROM lines WHERE railway IN ('rail','light_rail','tram','subway','narrow_gauge')",
    ),
    (
        "railway_lines_lifecycle.shp",
        "railway_lines_lifecycle (construction, proposed, disused, abandoned)",
        "SELECT * FROM lines WHERE railway IN ('construction','proposed','disused','abandoned')",
    ),
    (
        "railway_stations.shp",
        "railway_stations (station, halt, tram_stop)",
        "SELECT * FROM points WHERE railway IN ('station','halt','tram_stop')",
    ),
    (
        "railway_crossings.shp",
        "railway_crossings (level_crossing, crossing)",
        "SELECT * FROM points WHERE railway IN ('level_crossing','crossing')",
    ),
    (
        "railway_areas.shp",
        "railway_areas (all polygons with railway tag)",
        "SELECT * FROM multipolygons WHERE railway IS NOT NULL",
    ),
)

# (layer_name, sql_query, per_layer_extra_ogr2ogr_args)
GEOJSON_LAYER_SPECS = (
    (
        "railway_lines",
        "SELECT * FROM lines WHERE railway IN ('rail','light_rail','tram','subway','narrow_gauge','monorail','funicular','miniature')",
        [],
    ),
    (
        "railway_lines_lifecycle",
        "SELECT * FROM lines WHERE railway IN ('construction','proposed','disused','abandoned','preserved','razed')",
        [],
    ),
    (
        "railway_stations",
        "SELECT * FROM points WHERE railway IN ('station','halt','tram_stop','subway_entrance','border')",
        [],
    ),
    (
        "railway_crossings",
        "SELECT * FROM points WHERE railway IN ('level_crossing','crossing','tram_level_crossing','tram_crossing')",
        [],
    ),
    (
        "railway_platforms",
        "SELECT * FROM multipolygons WHERE railway = 'platform'",
        [],
    ),
    ("railway_signals", "SELECT * FROM points WHERE railway = 'signal'", []),
    ("railway_switches", "SELECT * FROM points WHERE railway = 'switch'", []),
    ("railway_buffer_stops", "SELECT * FROM points WHERE railway = 'buffer_stop'", []),
    ("railway_derails", "SELECT * FROM points WHERE railway = 'derail'", []),
    (
        "railway_track_crossings",
        "SELECT * FROM points WHERE railway = 'railway_crossing'",
        [],
    ),
    ("railway_milestones", "SELECT * FROM points WHERE railway = 'milestone'", []),
    ("railway_turntables", "SELECT * FROM points WHERE railway = 'turntable'", []),
    (
        "railway_owner_changes",
        "SELECT * FROM points WHERE railway = 'owner_change'",
        [],
    ),
    (
        "railway_areas",
        "SELECT * FROM multipolygons WHERE (railway IS NOT NULL AND railway != 'platform') OR landuse = 'railway'",
        [],
    ),
    (
        "railway_tunnel_entrances",
        "SELECT ST_StartPoint(geometry) AS geometry, osm_id, name, tunnel_name, "
        "railway, operator FROM lines WHERE tunnel = 'yes' AND tunnel_name IS NOT "
        "NULL AND tunnel_name != ''",
        ["-dialect", "sqlite"],
    ),
)

# (layer_name, sql_query, per_layer_extra_ogr2ogr_args)
GPKG_LAYER_SPECS = (
    ("railway_lines", "SELECT * FROM lines WHERE railway IS NOT NULL", []),
    ("railway_points", "SELECT * FROM points WHERE railway IS NOT NULL", ["-append"]),
    (
        "railway_areas",
        "SELECT * FROM multipolygons WHERE railway IS NOT NULL",
        ["-append"],
    ),
)

# (geojson_file_stem, tile_layer_name, tippecanoe_minzoom)
LINE_TILE_LAYER_SPECS = (
    ("railway_lines", "railway_lines", 2),
    ("railway_lines_lifecycle", "railway_lines_lifecycle", 8),
)

# (geojson_file_stem, tile_layer_name, tippecanoe_minzoom)
STATION_TILE_LAYER_SPECS = (
    ("railway_stations", "railway_stations", 7),
    ("railway_routes", "railway_routes", 5),
    ("railway_routes_display", "railway_routes_display", 5),
)

# (geojson_file_stem, tile_layer_name, tippecanoe_minzoom)
DETAIL_TILE_LAYER_SPECS = (
    ("railway_crossings", "railway_crossings", 11),
    ("railway_platforms", "railway_platforms", 10),
    ("railway_platform_refs", "railway_platform_refs", 12),
    ("railway_signals", "railway_signals", 12),
    ("railway_switches", "railway_switches", 13),
    ("railway_buffer_stops", "railway_buffer_stops", 14),
    ("railway_derails", "railway_derails", 14),
    ("railway_track_crossings", "railway_track_crossings", 13),
    ("railway_milestones", "railway_milestones", 14),
    ("railway_turntables", "railway_turntables", 12),
    ("railway_owner_changes", "railway_owner_changes", 10),
    ("railway_areas", "railway_areas", 8),
    ("railway_tunnel_entrances", "railway_tunnel_entrances", 11),
)
