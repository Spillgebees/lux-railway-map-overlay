FROM python:3.14-slim-trixie@sha256:0741d101873c12ab927e6f8653feb8862b9bd58771177acb1b885b95141f91b4 AS tippecanoe-builder

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

FROM python:3.14-slim-trixie@sha256:0741d101873c12ab927e6f8653feb8862b9bd58771177acb1b885b95141f91b4

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

COPY requirements.txt /scripts/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /scripts/requirements.txt

COPY --from=tippecanoe-builder /usr/local/bin/tippecanoe /usr/local/bin/tippecanoe
COPY --from=tippecanoe-builder /usr/local/bin/tile-join /usr/local/bin/tile-join

COPY generator /scripts/generator
COPY osmconf.ini /scripts/osmconf.ini

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
ENV PYTHONPATH=/scripts \
    OUTPUT_DIR=/data
ENTRYPOINT ["python3", "-m", "generator"]
