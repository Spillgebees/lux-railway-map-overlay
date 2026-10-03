# Self-hosting

This guide covers running the tile server: the container image, its configuration, the endpoints it serves, and its cache headers. For Kubernetes, see the [Helm chart README](../charts/lux-railway-map-overlay/README.md).

## What runs in the container

The tile server image runs two processes. Martin serves tiles, TileJSON, sprites, and health on `127.0.0.1:3001`. nginx listens on port `8080`, serves the style and glyphs itself, and proxies everything else to Martin. The container runs as the unprivileged user `101:101`. The image is based on `nginxinc/nginx-unprivileged` (Alpine) and adds Martin's statically linked musl release binary.

`tiles/Dockerfile` has two targets:

- `bundle` builds the published image, `ghcr.io/spillgebees/lux-railway-map-overlay`, with the generated MBTiles baked in.
- `runtime` is the image `docker compose up` builds. It contains no data. It reads the MBTiles from the `./data` mount.

Each publish run pushes three tags:

- a release version, `<year>.<month * 100 + day>.<run number>`, for example `2026.1003.76`. CI never overwrites it, so pin it for reproducible deployments.
- `latest`, the newest build from `main`.
- `sha-<commit>`, the commit the image was built from. A monthly data refresh rebuilds the same commit, so this tag can move to newer data.

The image also carries a BuildKit SBOM and provenance attestation, and GitHub stores a signed build provenance attestation for it. Check the attestation with `gh attestation verify oci://ghcr.io/spillgebees/lux-railway-map-overlay:<version> --owner Spillgebees`.

The Helm chart is published with the same version. See the [Helm chart README](../charts/lux-railway-map-overlay/README.md).

## Run the published image

```bash
docker run --rm -p 3000:8080 ghcr.io/spillgebees/lux-railway-map-overlay:latest
```

## Serve your own MBTiles

Mount a directory that contains `lux-railway-map-overlay.mbtiles`, or set `MBTILES_PATH` to the file. With the published image, set `MBTILES_PATH`, because the baked-in file takes precedence over a mounted `/data` directory.

```bash
docker run --rm -p 3000:8080 \
  -v "$PWD/data/out:/data:ro" \
  -e MBTILES_PATH=/data/lux-railway-map-overlay.mbtiles \
  ghcr.io/spillgebees/lux-railway-map-overlay:latest
```

If `MBTILES_PATH` is unset, the entrypoint uses the first file it finds:

1. `/app/data/lux-railway-map-overlay.mbtiles` (baked into the published image)
2. `/data/lux-railway-map-overlay.mbtiles` (Helm chart volume)
3. `/data/out/lux-railway-map-overlay.mbtiles` (Docker Compose, which mounts `./data` at `/data`)

The container exits with an error if none exists.

## Environment variables

| Variable       | Default                 | Description                                                                                                  |
| -------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------ |
| `PUBLIC_URL`   | `http://localhost:3000` | External base URL. The entrypoint replaces `http://localhost:3000` in `style.json` with this value at startup. |
| `MBTILES_PATH` | unset                   | Path to the MBTiles file. Overrides the lookup order above.                                                  |

Set `PUBLIC_URL` to the URL clients use to reach the server. Otherwise `style.json` points the source, sprite, and glyph URLs at `localhost`. The value must start with `http://` or `https://` and may include a path, but no query string, fragment, or whitespace. The entrypoint strips trailing slashes and exits with an error if the value is invalid.

With Docker Compose, pass it on the command line or put it in a `.env` file next to `docker-compose.yml`:

```bash
PUBLIC_URL=https://tiles.example.com docker compose up
```

## Endpoints

| Endpoint                               | Description                                          |
| -------------------------------------- | ---------------------------------------------------- |
| `/style.json`                          | MapLibre style with URLs rewritten to `PUBLIC_URL`   |
| `/lux-railway-map-overlay`             | TileJSON, the URL to use as a vector source          |
| `/lux-railway-map-overlay/{z}/{x}/{y}` | Vector tiles, up to zoom 14                          |
| `/fonts/{fontstack}/{range}.pbf`       | Glyph PBFs                                           |
| `/sprite/symbols`                      | Sprite built from `styles/symbols/`                  |
| `/catalog`                             | Martin tile catalog                                  |
| `/health`                              | Health check                                         |
| `/_/metrics`                           | Prometheus metrics from Martin                       |

## Caching

nginx sets these `Cache-Control` headers:

- Tiles, sprites, and glyphs: `public, max-age=3600`
- `/style.json`, TileJSON, `/catalog`, `/health`, `/_/metrics`, and anything else proxied to Martin: `no-store`

Tile URLs are not versioned, which is why the browser cache lifetime is one hour. nginx also keeps its own tile cache of up to 32 MB in `/tmp/nginx/proxy_cache` and reports hits in the `X-Cache-Status` response header.

A CDN such as Cloudflare can proxy the server as is. It will follow these headers.

nginx honors `X-Forwarded-Proto` and `X-Forwarded-Host` from a reverse proxy and passes them on to Martin, so TileJSON URLs match the public host.

## Glyphs

The image hosts these font stacks:

- `IBM Plex Sans Regular`
- `IBM Plex Sans Bold`
- `Noto Sans Regular`
- `Noto Sans Italic`
- `Noto Sans Bold`

The railway style uses only the IBM Plex Sans stacks. The Noto Sans stacks are there because many third-party basemaps reference them. To add more stacks, extend [`tiles/glyphs/generate-glyphs.sh`](../tiles/glyphs/generate-glyphs.sh) and rebuild the image. The [consumer integration guide](consumer-integration.md#glyphs-when-combining-styles) explains why combined styles need one shared glyph endpoint.

## Attribution

Maps and services that use these tiles must show "© OpenStreetMap contributors". See [Attribution and license](../README.md#attribution-and-license).
