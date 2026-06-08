from __future__ import annotations

RAIL_TRACK_MODE_SQL_VALUES = (
    "'rail','light_rail','tram','subway','narrow_gauge',"
    "'monorail','funicular','miniature'"
)

ACTIVE_RAIL_TRACK_SQL_VALUES = RAIL_TRACK_MODE_SQL_VALUES + ",'preserved'"

# (output_filename, human_label, sql_query)
SHAPEFILE_LAYER_SPECS = (
    (
        "rail_tracks.shp",
        "rail_tracks (active and preserved railway tracks)",
        f"SELECT * FROM lines WHERE railway IN ({ACTIVE_RAIL_TRACK_SQL_VALUES})",
    ),
    (
        "rail_tracks_lifecycle.shp",
        "rail_tracks_lifecycle (construction, proposed, disused, abandoned, razed)",
        "SELECT * FROM lines WHERE railway IN "
        "('construction','proposed','disused','abandoned','razed') "
        f"OR construction_railway IN ({RAIL_TRACK_MODE_SQL_VALUES}) "
        f"OR proposed_railway IN ({RAIL_TRACK_MODE_SQL_VALUES}) "
        f"OR disused_railway IN ({RAIL_TRACK_MODE_SQL_VALUES}) "
        f"OR abandoned_railway IN ({RAIL_TRACK_MODE_SQL_VALUES}) "
        f"OR razed_railway IN ({RAIL_TRACK_MODE_SQL_VALUES})",
    ),
    (
        "rail_stops.shp",
        "rail_stops (station, halt, tram_stop)",
        "SELECT * FROM points WHERE railway IN ('station','halt','tram_stop')",
    ),
    (
        "rail_crossings.shp",
        "rail_crossings (level_crossing, crossing)",
        "SELECT * FROM points WHERE railway IN ('level_crossing','crossing')",
    ),
    (
        "rail_areas.shp",
        "rail_areas (all polygons with railway tag)",
        "SELECT * FROM multipolygons WHERE railway IS NOT NULL",
    ),
)

# (layer_name, sql_query, per_layer_extra_ogr2ogr_args)
GEOJSON_LAYER_SPECS = (
    (
        "rail_tracks",
        f"SELECT * FROM lines WHERE railway IN ({ACTIVE_RAIL_TRACK_SQL_VALUES})",
        [],
    ),
    (
        "rail_tracks_lifecycle",
        "SELECT * FROM lines WHERE railway IN "
        "('construction','proposed','disused','abandoned','razed') "
        f"OR construction_railway IN ({RAIL_TRACK_MODE_SQL_VALUES}) "
        f"OR proposed_railway IN ({RAIL_TRACK_MODE_SQL_VALUES}) "
        f"OR disused_railway IN ({RAIL_TRACK_MODE_SQL_VALUES}) "
        f"OR abandoned_railway IN ({RAIL_TRACK_MODE_SQL_VALUES}) "
        f"OR razed_railway IN ({RAIL_TRACK_MODE_SQL_VALUES})",
        [],
    ),
    (
        "rail_stops",
        "SELECT * FROM points WHERE railway IN "
        "('station','halt','tram_stop','subway_entrance','border')",
        [],
    ),
    (
        "rail_crossings",
        "SELECT * FROM points WHERE railway IN "
        "('level_crossing','crossing','tram_level_crossing','tram_crossing')",
        [],
    ),
    (
        "rail_platforms",
        "SELECT * FROM multipolygons WHERE railway = 'platform'",
        [],
    ),
    (
        "rail_infrastructure_points",
        "SELECT * FROM points WHERE railway IN "
        "('signal','switch','buffer_stop','derail','railway_crossing',"
        "'milestone','turntable','owner_change')",
        [],
    ),
    (
        "rail_areas",
        "SELECT * FROM multipolygons WHERE "
        "(railway IS NOT NULL AND railway != 'platform') OR landuse = 'railway'",
        [],
    ),
    (
        "rail_tunnel_entrances",
        "SELECT ST_StartPoint(geometry) AS geometry, osm_id, name, tunnel_name, "
        "railway, operator FROM lines WHERE tunnel = 'yes' AND tunnel_name IS NOT "
        "NULL AND tunnel_name != ''",
        ["-dialect", "sqlite"],
    ),
)

# (layer_name, sql_query, per_layer_extra_ogr2ogr_args)
GPKG_LAYER_SPECS = (
    ("rail_tracks", "SELECT * FROM lines WHERE railway IS NOT NULL", []),
    (
        "rail_infrastructure_points",
        "SELECT * FROM points WHERE railway IS NOT NULL",
        ["-update"],
    ),
    (
        "rail_areas",
        "SELECT * FROM multipolygons WHERE railway IS NOT NULL",
        ["-update"],
    ),
)

# (geojson_file_stem, tile_layer_name, tippecanoe_minzoom)
LINE_TILE_LAYER_SPECS = (
    ("rail_tracks", "rail_tracks", 2),
    ("rail_tracks_lifecycle", "rail_tracks_lifecycle", 8),
)

# (geojson_file_stem, tile_layer_name, tippecanoe_minzoom)
STATION_TILE_LAYER_SPECS = (
    ("rail_stops", "rail_stops", 7),
    ("rail_routes", "rail_routes", 5),
    ("rail_routes_display", "rail_routes_display", 5),
)

# (geojson_file_stem, tile_layer_name, tippecanoe_minzoom)
DETAIL_TILE_LAYER_SPECS = (
    ("rail_crossings", "rail_crossings", 11),
    ("rail_platforms", "rail_platforms", 10),
    ("rail_platform_labels", "rail_platform_labels", 12),
    ("rail_infrastructure_points", "rail_infrastructure_points", 12),
    ("rail_areas", "rail_areas", 8),
    ("rail_tunnel_entrances", "rail_tunnel_entrances", 11),
)
