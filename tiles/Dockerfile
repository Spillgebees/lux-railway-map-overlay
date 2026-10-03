FROM debian:trixie-slim@sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a AS glyphs

ARG FONT_MAKER_REF=c56771948c59a01b89d0498d47dc4abf56c25338

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    ca-certificates \
    clang \
    cmake \
    curl \
    fonts-noto-core \
    git \
    libboost-dev \
    libfreetype6-dev \
    pkg-config \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp

RUN git clone https://github.com/maplibre/font-maker.git /tmp/font-maker \
    && cd /tmp/font-maker \
    && git checkout "$FONT_MAKER_REF" \
    && git submodule update --init --recursive \
    && cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build --parallel

WORKDIR /glyphs

COPY tiles/glyphs/generate-glyphs.sh /glyphs/generate-glyphs.sh

RUN chmod +x /glyphs/generate-glyphs.sh \
    && /glyphs/generate-glyphs.sh /glyphs/output /tmp/font-maker/build/font-maker

# Martin's release musl builds are statically linked and include every feature
# this image uses (mbtiles, sprites, fonts, styles, metrics). Rendering is not
# part of the musl build and is not used here. The download runs on the build
# platform so cross-arch builds need no emulation.
FROM --platform=$BUILDPLATFORM nginxinc/nginx-unprivileged:1.30.5-alpine-slim@sha256:e28dcf0a161ddcbf228c7364b4a14f9bad4763ae8f5317c437b896afa3df4b84 AS martin

ARG TARGETARCH
# When bumping MARTIN_VERSION, update the checksums too:
#   gh release view martin-v<version> -R maplibre/martin --json assets \
#     -q '.assets[] | select(.name | test("linux-musl")) | .name + " " + .digest'
# renovate: datasource=github-releases depName=maplibre/martin extractVersion=^martin-v(?<version>.*)$
ARG MARTIN_VERSION=1.16.1
ARG MARTIN_SHA256_AMD64=831df5399bb573a8b6bc01dbb38be5938c0e95501e715403d9eacd9143b33348
ARG MARTIN_SHA256_ARM64=6802b55c378d6a38180d881d306f53c17ac4ebbb35893aa94204907b0f08fd1c

WORKDIR /tmp/martin

RUN case "${TARGETARCH}" in \
    amd64) arch=x86_64; sha256="${MARTIN_SHA256_AMD64}" ;; \
    arm64) arch=aarch64; sha256="${MARTIN_SHA256_ARM64}" ;; \
    *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && wget -q -O martin.tar.gz "https://github.com/maplibre/martin/releases/download/martin-v${MARTIN_VERSION}/martin-${arch}-unknown-linux-musl.tar.gz" \
    && printf '%s  %s\n' "${sha256}" martin.tar.gz > martin.tar.gz.sha256 \
    && sha256sum -c martin.tar.gz.sha256 \
    && tar -xzf martin.tar.gz martin

FROM nginxinc/nginx-unprivileged:1.30.5-alpine-slim@sha256:e28dcf0a161ddcbf228c7364b4a14f9bad4763ae8f5317c437b896afa3df4b84 AS base

USER 0

# hadolint ignore=DL3018
RUN apk add --no-cache bash \
    && rm -rf /etc/nginx/conf.d /usr/share/nginx/html /docker-entrypoint.sh /docker-entrypoint.d

COPY --from=martin /tmp/martin/martin /usr/local/bin/martin
COPY --chown=101:101 styles /styles
COPY --from=glyphs --chown=101:101 /glyphs/output /styles/fonts
COPY --chown=101:101 tiles/nginx.conf /etc/nginx/nginx.conf
COPY --chmod=755 --chown=101:101 tiles/entrypoint.sh /entrypoint.sh

USER 101:101

EXPOSE 8080

# The nginx base image uses SIGQUIT; entrypoint.sh handles SIGTERM/SIGINT.
STOPSIGNAL SIGTERM

ENTRYPOINT ["/entrypoint.sh"]

# Production image: MBTiles baked in (built by publish-image.yml).
FROM base AS bundle

COPY --chown=101:101 bundle/lux-railway-map-overlay.mbtiles /app/data/lux-railway-map-overlay.mbtiles

# Default target: no data baked in; mount MBTiles at runtime (docker-compose.yml).
FROM base AS runtime
