# lux-railway-map-overlay

A railway overlay for Luxembourg and its cross-border lines into Belgium, Germany, and France. A Python pipeline turns OpenStreetMap data into vector tiles. Martin serves them behind nginx, and `styles/style.json` draws them over any basemap.

Read `README.md` for usage and `docs/` for depth. This file covers what to keep in mind when changing the code.

## Layout

| Path | Contents |
| --- | --- |
| `scripts/generator/` | The pipeline: Geofabrik extracts, Overpass route relations, GeoJSON, tippecanoe, GeoPackage |
| `scripts/Dockerfile` | Generator image. Builds from the repo root and uses `scripts/Dockerfile.dockerignore` |
| `tests/` | pytest for the generator, the style contract, and `tiles/entrypoint.sh` |
| `styles/` | `style.json` and the SVG sprite icons in `symbols/` |
| `tiles/` | Tile server image (`runtime` and `bundle` targets), `entrypoint.sh`, `nginx.conf`, glyph build |
| `charts/lux-railway-map-overlay/` | Helm chart, published to `oci://ghcr.io/spillgebees/charts` |
| `viewer/` | Blazor WebAssembly demo on `Spillgebees.Blazor.Map` |
| `data/` | Ignored by git. `cache/` survives reruns, `intermediate/` is scratch, `out/` holds the deliverables |

## Checks

CI runs these in `.github/workflows/validate.yml`. Run the ones for the area you touched:

```bash
uv sync --locked
uv run ruff format --check && uv run ruff check && uv run basedpyright && uv run pytest
dotnet csharpier check viewer && dotnet build viewer/RailwayViewer.slnx -c Release -warnaserror
spec="$(sed -n 's/^  STYLE_SPEC_VERSION: //p' .github/workflows/validate.yml)"
npx --yes --package "@maplibre/maplibre-gl-style-spec@$spec" gl-style-validate styles/style.json
helm lint --strict charts/lux-railway-map-overlay --set image.tag=ci
```

The style check reads the style-spec version from `validate.yml`, so it matches CI. `helm lint` is the quick local check. CI's Helm job also renders every `ci/*-values.yaml` scenario, validates the output with kubeconform, and checks that the chart refuses the `0.0.0` placeholder tag and that the cert-manager scenario gets TLS.

`uv run pre-commit install` adds ruff, basedpyright, CSharpier, Biome, ShellCheck, and actionlint as git hooks.

## Rules

### Licensing

- The project ships under MIT. Everything we distribute must be MIT-compatible: code, styles, icons, tiles, images.
- GPL tools may run during the build if we only call their CLI and don't ship them in the tile server image. osmium-tool (GPL-3.0) in the generator image is the one case today.
- Write styles and icons from scratch. Don't copy from OpenRailwayMap (GPL-3.0) or other GPL projects.
- Every map, export, and doc screenshot shows "© OpenStreetMap contributors". OSM data is ODbL.
- New third-party components go in `THIRD_PARTY_NOTICES.md`.

### Style

- Each overlay layer carries `metadata.toggle` tokens: a family (`tracks`, `routes`, `stops`, `platforms`, `infrastructure`, `crossings`, `areas`), plus a mode and a lifecycle state where they apply. The viewer builds its toggles from these tokens, and `tests/generator/test_style_contract.py` checks them. Add the tokens to any new layer.
- `layout.visibility` sets the default. Tram, trackside infrastructure, and level crossings start hidden. Everything else starts visible. `docs/consumer-integration.md` lists the defaults, so update it when you change one.
- Spillgebees.Blazor.Map 0.23 can't show a layer the style hides. The viewer greys those toggles out. When the library gains that ability, flip `CanRevealStyleHiddenLayers` in `viewer/Overlay/OverlayVisibility.cs`.

### Pipeline

- Never cache a partial input. Geofabrik downloads go to a `.part` file and must match `Content-Length` and Geofabrik's MD5 before they replace the cached file. Overpass responses with a `remark`, or without an `elements` list, count as failures and move on to the next mirror.
- Route extraction is strict. A run fails without routes unless someone passes `--allow-missing-routes`. The publish workflow also rejects empty route GeoJSON.
- Defaults live in the CLI, not the Dockerfile: `--countries lu,be,de,fr`, and `--output-dir` from `OUTPUT_DIR` (`/data` in the image).
- The generator image runs as 1000:1000 with WORKDIR `/tmp`. ogr2ogr writes node-cache files to the working directory, so keep it writable.

### Images and releases

- The tile server is Alpine `nginx-unprivileged` plus Martin's static musl binary. The build checks the binary against the SHA256 digest GitHub publishes for the release asset. It runs as 101:101 and must work with a read-only root filesystem and a `/tmp` tmpfs.
- nginx serves the public API on 8080. Martin metrics are on 9090 at `/metrics` and must stay off 8080.
- `publish-image.yml` tags each build `<year>.<month*100+day>.<run>` (for example `2026.1003.76`), plus `latest` and `sha-<commit>`. It pushes the chart with the same version. `Chart.yaml` keeps the placeholder `0.0.0`, and the chart refuses to render with it.

### Dependencies

- Pin everything: images by digest, actions by SHA with a `# vN` comment, tool versions in Dockerfile `ARG`s and workflow `env:` with a `# renovate:` comment. The shared preset (`local>Spillgebees/admin`) picks those comments up.
- Python dependencies live in `pyproject.toml` and `uv.lock`. The .NET SDK is pinned in `global.json`, packages in `viewer/Directory.Packages.props`.

### Code style

- Python 3.14, formatted and linted by ruff, type-checked by basedpyright in standard mode.
- C#: .NET 10, file-scoped namespaces, `var` everywhere, Allman braces, CSharpier with a 120-column width.
- Shell: bash with `set -euo pipefail`, clean under ShellCheck.
- Commits use gitmoji (`:bug:`, `:sparkles:`, `:memo:`, ...).
