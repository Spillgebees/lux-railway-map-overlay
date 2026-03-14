FROM debian:bookworm-slim AS glyphs

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

FROM ghcr.io/maplibre/martin:v0.15.0 AS martin

FROM nginxinc/nginx-unprivileged:stable-alpine-slim

COPY --from=martin /usr/local/bin/martin /usr/local/bin/martin

COPY --chown=101:101 styles /styles
COPY --from=glyphs --chown=101:101 /glyphs/output /styles/fonts
COPY --chown=101:101 tiles/nginx.conf /etc/nginx/nginx.conf
COPY --chmod=755 --chown=101:101 tiles/entrypoint.sh /entrypoint.sh

USER 101:101

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
