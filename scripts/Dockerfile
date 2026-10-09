FROM python:3.14-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS tippecanoe-builder

# renovate: datasource=github-releases depName=felt/tippecanoe
ARG TIPPECANOE_VERSION=2.79.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    g++ \
    git \
    make \
    libsqlite3-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${TIPPECANOE_VERSION}" https://github.com/felt/tippecanoe.git /tmp/tippecanoe \
    && cd /tmp/tippecanoe \
    && make -j"$(nproc)" \
    && make install \
    && rm -rf /tmp/tippecanoe

# Build context is the repository root (see scripts/Dockerfile.dockerignore),
# so the image installs the exact versions pinned in uv.lock.
FROM ghcr.io/astral-sh/uv:0.12.22@sha256:f513a91fc62fe7c17567eee97230dd198e43edb8a9fbecca843714a4358fe1bc AS uv

FROM python:3.14-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS python-deps

# Use the base image's interpreter so the venv also works in the final stage.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3

WORKDIR /build

RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-dev --no-install-project

FROM python:3.14-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170

LABEL org.opencontainers.image.source="https://github.com/Spillgebees/lux-railway-map-overlay" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.description="Generates railway vector tiles and a GeoPackage for Luxembourg from OpenStreetMap data"

WORKDIR /scripts

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    ca-certificates \
    gdal-bin \
    libsqlite3-0 \
    osmium-tool \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY --from=python-deps /opt/venv /opt/venv

COPY --from=tippecanoe-builder /usr/local/bin/tippecanoe /usr/local/bin/tippecanoe
COPY --from=tippecanoe-builder /usr/local/bin/tile-join /usr/local/bin/tile-join

COPY scripts/generator /scripts/generator
COPY scripts/osmconf.ini /scripts/osmconf.ini

# uid/gid match docker-compose.yml's LOCAL_UID/LOCAL_GID defaults; compose
# can still run as any other uid. /data is pre-created so a fresh named
# volume is writable by this user.
RUN groupadd --gid 1000 generator \
    && useradd --uid 1000 --gid 1000 --no-create-home --home-dir /tmp \
    --shell /usr/sbin/nologin generator \
    && mkdir /data \
    && chown 1000:1000 /data

# ogr2ogr's OSM driver writes temp node-cache files to the current
# working directory; /tmp is world-writable, so any uid can write there
WORKDIR /tmp
USER 1000:1000

# the generator defaults --output-dir to $OUTPUT_DIR, so custom arguments
# such as `--countries lu` still write to the mounted volume
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/scripts \
    OUTPUT_DIR=/data
ENTRYPOINT ["python3", "-m", "generator"]
