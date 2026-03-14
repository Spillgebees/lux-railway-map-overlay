ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim AS tippecanoe-builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    g++ \
    git \
    make \
    libsqlite3-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/felt/tippecanoe.git /tmp/tippecanoe \
    && cd /tmp/tippecanoe \
    && make -j"$(nproc)" \
    && make install \
    && rm -rf /tmp/tippecanoe

FROM python:${PYTHON_VERSION}-slim

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

# ogr2ogr's OSM driver writes temp node-cache files to the current
# working directory; /tmp is world-writable so non-root users can write
WORKDIR /tmp

ENV PYTHONPATH=/scripts
ENTRYPOINT ["python3", "-m", "generator"]
CMD ["--countries", "lu,be,de,fr", "--output-dir", "/data"]
