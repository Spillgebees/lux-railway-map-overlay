# Consumer integration

This guide shows how to draw the railway overlay on top of your own basemap in MapLibre GL JS. It covers the tile schema, the style metadata for building toggles, and the glyph setup for combined styles.

The examples use `https://tiles.example.com` as the tile server. Replace it with your own server, or with `http://localhost:3000` for a local one. [Self-hosting](self-hosting.md) explains how to run the server.

## Add the overlay

### Add the full style

MapLibre GL JS takes one style at construction time. It does not merge an array of style URLs. To use the prebuilt railway style, fetch it and add its sources and layers to the map after the basemap loads. Skip the `background` layer, or it will cover the basemap.

```javascript
map.on("load", async () => {
  const overlayStyle = await fetch("https://tiles.example.com/style.json").then((response) => response.json());

  for (const [sourceId, source] of Object.entries(overlayStyle.sources)) {
    map.addSource(sourceId, source);
  }

  for (const layer of overlayStyle.layers) {
    if (layer.type !== "background") {
      map.addLayer(layer);
    }
  }
});
```

The railway layers reference the railway sprite and glyphs. Your map's style must point `sprite` and `glyphs` at endpoints that serve them, or icons and labels will not render. See [Glyphs when combining styles](#glyphs-when-combining-styles).

Map libraries with style composition, such as [`Spillgebees.Blazor.Map`](https://github.com/Spillgebees/Blazor.Map), can take the basemap and `style.json` as separate styles. The demo viewer in `viewer/` does this.

### Add the source and your own layers

To style the data yourself, add the TileJSON as a vector source and add layers for the source layers you need.

```javascript
const map = new maplibregl.Map({
  container: "map",
  style: "your-basemap-style-url",
  center: [6.13, 49.61],
  zoom: 8,
});

map.on("load", () => {
  map.addSource("railway", {
    type: "vector",
    url: "https://tiles.example.com/lux-railway-map-overlay",
  });

  // active heavy rail tracks
  map.addLayer({
    id: "rail-tracks-heavy",
    type: "line",
    source: "railway",
    "source-layer": "rail_tracks",
    filter: ["all", ["==", ["get", "mode"], "heavy_rail"], ["==", ["get", "lifecycle_state"], "active"]],
    paint: {
      "line-color": "#1e293b",
      "line-width": 2,
    },
  });
});
```

## Source layers

Tiles go up to zoom 14. Each source layer starts at the minimum zoom listed below.

| Source layer                 | Contents                                                                                  | Min zoom | Key properties                                                                                                     |
| ---------------------------- | ----------------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------ |
| `rail_tracks`                | Active tracks, plus preserved tracks (`railway=preserved` or `railway:preserved=yes`)     | 2        | `mode`, `lifecycle_state`, `track_role`, `structure`, `is_electrified`, `osm_railway`                              |
| `rail_tracks_lifecycle`      | Construction, proposed, disused, abandoned, and razed tracks                              | 8        | `mode`, `lifecycle_state`, `track_role`, `structure`, `osm_railway`                                                |
| `rail_stops`                 | Stations, halts, tram stops, subway entrances, border points                              | 7        | `mode`, `stop_type`, `name`, `operator`, `network`, `osm_railway`                                                  |
| `rail_routes`                | Route relations as unmodified centerlines                                                 | 5        | `mode`, `osm_route`, `ref`, `name`, `operator`, `colour`, `network`, `from`, `to`                                  |
| `rail_routes_display`        | The same routes, offset sideways so parallel services do not overlap                     | 5        | Same as `rail_routes`, plus display colors and `route_offset_slot`                                                 |
| `rail_crossings`             | Road-rail level crossings and tram crossings                                              | 11       | `crossing_type`, `has_barrier`, `has_bell`, `has_light`, `is_supervised`                                           |
| `rail_platforms`             | Platform polygons                                                                         | 10       | `ref`, `name`, `public_transport`                                                                                  |
| `rail_platform_labels`       | Label points synthesized from platforms and stop positions                                | 12       | `platform_label`, `platform_label_short`, `platform_name_label`, `platform_ref_label`, `source_layer`, `source_id` |
| `rail_infrastructure_points` | Signals, switches, buffer stops, derails, track crossings, milestones, turntables, owner changes | 12 | `infra_type`, `name`, `osm_railway`                                                                                |
| `rail_areas`                 | Railway land use and facility polygons, excluding platforms                               | 8        | `area_type`, `name`, `landuse`, `osm_railway`                                                                      |
| `rail_tunnel_entrances`      | Tunnel entrance points, taken from the start of each named tunnel                         | 11       | `infra_type`, `structure`, `name`, `tunnel_name`, `operator`                                                       |

`mode` is the normalized transport mode: `heavy_rail`, `light_rail`, `tram`, `metro`, `narrow_gauge`, `monorail`, `funicular`, or `miniature`. The raw OSM value stays in `osm_railway` or `osm_route`.

### Stop types

`rail_stops` mixes several point types. Filter on `stop_type`:

| `stop_type`       | Description                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------------- |
| `station`         | Railway station                                                                               |
| `halt`            | Halt or minor stop                                                                            |
| `tram_stop`       | Tram stop                                                                                     |
| `subway_entrance` | Subway entrance                                                                               |
| `border`          | Point where the network crosses a border. Its `mode` is `heavy_rail`, so it toggles with heavy rail stops. |

### Route properties

The generator computes these properties for `rail_routes` and `rail_routes_display`:

| Property              | Description                                                                          |
| --------------------- | ------------------------------------------------------------------------------------ |
| `ref`                 | Route reference, for example `RE 11`                                                 |
| `name`                | Relation name                                                                        |
| `route`, `osm_route`  | Raw OSM route type: `train`, `tram`, `light_rail`, or `subway`                       |
| `mode`                | Normalized mode. `train` becomes `heavy_rail` and `subway` becomes `metro`.          |
| `operator`            | Operator                                                                             |
| `network`             | Network                                                                              |
| `from`                | Resolved origin station name                                                         |
| `to`                  | Resolved destination station name                                                    |
| `colour`              | OSM color normalized to uppercase 6-digit hex, or empty                              |
| `source_colour`       | Copy of `colour`, kept before the display fallback applies                          |
| `display_colour`      | Color used for rendering. Falls back to `#5B6675` when OSM has no color.             |
| `display_text_colour` | Label color with enough contrast: dark for light routes, the route color for dark ones |
| `route_offset_slot`   | Sideways offset slot for parallel routes. `0` is centered.                           |

`rail_routes_display` shifts each route by `route_offset_slot × 8` meters (Web Mercator) so parallel services stay readable. Use `rail_routes` when you need the true centerline.

### Platform labels

Platform references are tagged inconsistently in OSM, so the generator builds `rail_platform_labels` from both platform polygons and stop positions. This expression picks the best short label:

```javascript
["coalesce",
  ["get", "platform_ref_label"],
  ["get", "platform_label_short"],
  ["get", "local_ref"],
  ["get", "ref"]
]
```

| Property               | Description                                                                                 |
| ---------------------- | ------------------------------------------------------------------------------------------- |
| `platform_ref_label`   | Best short reference, from `local_ref`, `ref`, or text extracted from IFOPT or `description` |
| `platform_label_short` | Same value as `platform_ref_label`                                                          |
| `platform_name_label`  | Platform name extracted from the feature name, for example `Quai 1A`                       |
| `platform_label`       | `platform_name_label` if set, otherwise `platform_ref_label`                                 |
| `source_layer`         | Where the label came from: `rail_platforms` (polygon centroid) or `rail_stops` (stop position) |
| `source_id`            | OSM ID of the source feature                                                                |

## Filter the data

Tram, metro, and rail features share source layers. Filter on `mode`:

```javascript
// heavy rail only
filter: ["==", ["get", "mode"], "heavy_rail"]

// tram only
filter: ["==", ["get", "mode"], "tram"]
```

Both track layers expose `lifecycle_state`: `active`, `construction`, `proposed`, `disused`, `abandoned`, `preserved`, or `razed`. Active and preserved tracks are in `rail_tracks`. The other states are in `rail_tracks_lifecycle`.

## Build toggles from the style metadata

Every layer in `style.json` except `background` has a `metadata` object:

- `family`: the toggle family the layer belongs to
- `toggle`: the tokens that control the layer, such as `["tracks", "heavy_rail", "active"]`
- `group`, and for track layers `mode` and `state`: finer grouping you can use for legends

The top-level `metadata` lists the supported tokens:

- `toggleFamilies`: `tracks`, `routes`, `stops`, `crossings`, `platforms`, `infrastructure`, `areas`
- `toggleModes`: `heavy_rail`, `light_rail`, `tram`, `metro`, `narrow_gauge`, `monorail`, `funicular`, `miniature`
- `toggleStates`: `active`, `construction`, `proposed`, `disused`, `abandoned`, `razed`, `preserved`

This toggles every layer that carries a given token:

```javascript
function toggleToken(token, visible) {
  for (const layer of map.getStyle().layers) {
    if (layer.metadata?.toggle?.includes(token)) {
      map.setLayoutProperty(layer.id, "visibility", visible ? "visible" : "none");
    }
  }
}
```

The demo viewer in [`viewer/Pages/Home.razor`](../viewer/Pages/Home.razor) shows one layer only when every toggle group it belongs to (family, mode, state) has at least one matching toggle switched on.

## Default visibility

The style ships with some layers hidden, so a map without a toggle UI shows a readable subset.

Visible by default:

- Active tracks for heavy rail, light rail, metro, narrow gauge, funicular, monorail, and miniature railways
- Service tracks from zoom 13, and non-tram tunnels with tunnel entrance icons and labels
- Construction, proposed, disused, abandoned, and razed tracks, except tram and light rail
- Preserved tracks
- Stations, halts, border points, and their labels
- Platforms: fills from zoom 12, 3D extrusions from zoom 14, and reference labels
- Route lines and labels
- Railway areas

Hidden by default:

- All tram layers: lines, tunnels, lifecycle tracks, and stop icons
- Light rail lifecycle tracks
- Subway entrance icons
- Route casing
- Trackside infrastructure: switches, signals, buffer stops, milestones, turntables, derails, track crossings, owner changes
- Level crossings and tram crossings

## Style design

The style is original work under the MIT License. It does not derive from OpenRailwayMap or other GPL-licensed styles.

Each feature type differs from the others in at least two ways, such as color and dash pattern, color and shape, or color and contrast. This keeps the overlay readable for people with color vision deficiency and on light or dark basemaps.

## Glyphs when combining styles

MapLibre renders text from glyph PBFs that the style's `glyphs` URL points to. CSS `@font-face` web fonts have no effect on map labels. A map has one `glyphs` URL, so when you combine the railway style with a basemap, that endpoint has to serve every font stack used by either style.

The tile server hosts these stacks at `/fonts/{fontstack}/{range}.pbf`:

- `IBM Plex Sans Regular`
- `IBM Plex Sans Bold`
- `Noto Sans Regular`
- `Noto Sans Italic`
- `Noto Sans Bold`

The railway style uses the IBM Plex Sans stacks. The Noto Sans stacks cover many third-party basemaps. If your basemap uses other stacks, pick one of these:

1. Point both styles at one glyph endpoint that serves all the stacks you need.
2. Add the missing fonts to [`tiles/glyphs/generate-glyphs.sh`](../tiles/glyphs/generate-glyphs.sh) and rebuild the tile image.
3. If your map component supports a glyph override for composed styles, point it at a compatible shared glyph service. `Spillgebees.Blazor.Map` has `ComposedGlyphsUrl` for this.

## Migrate from the old layer names

Earlier versions used different source layer names. Infrastructure points are now one layer with an `infra_type` property.

| Old layer                                                                                                                                                                   | New layer                                    |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| `railway_lines`                                                                                                                                                             | `rail_tracks`                                |
| `railway_lines_lifecycle`                                                                                                                                                   | `rail_tracks_lifecycle`                      |
| `railway_stations`                                                                                                                                                          | `rail_stops`                                 |
| `railway_routes`                                                                                                                                                            | `rail_routes`                                |
| `railway_routes_display`                                                                                                                                                    | `rail_routes_display`                        |
| `railway_crossings`                                                                                                                                                         | `rail_crossings`                             |
| `railway_platforms`                                                                                                                                                         | `rail_platforms`                             |
| `railway_platform_refs`                                                                                                                                                     | `rail_platform_labels`                       |
| `railway_signals`, `railway_switches`, `railway_buffer_stops`, `railway_derails`, `railway_track_crossings`, `railway_milestones`, `railway_turntables`, `railway_owner_changes` | `rail_infrastructure_points` with `infra_type` |
| `railway_areas`                                                                                                                                                             | `rail_areas`                                 |
| `railway_tunnel_entrances`                                                                                                                                                  | `rail_tunnel_entrances`                      |

## Attribution

The data comes from [OpenStreetMap](https://www.openstreetmap.org/) under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/). Any public use must show:

**© OpenStreetMap contributors**

The TileJSON includes this attribution, so MapLibre's attribution control shows it when you add the source. Keep the control enabled, or show the text another way.
