FROM debian:bookworm-slim@sha256:96e378d7e6531ac9a15ad505478fcc2e69f371b10f5cdf87857c4b8188404716 AS glyphs

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

FROM ghcr.io/maplibre/martin:v0.15.0@sha256:9bf94e0c214563bf34ffc35e7e3cdb1520b090f9516d86fcf01eff4ffe369c45 AS martin

FROM nginxinc/nginx-unprivileged:stable-alpine-slim@sha256:bcb4860e2d7877cf140e4c945f5f9cb304ccb5efbe1dd4fa606a2206142241bf

COPY --from=martin /usr/local/bin/martin /usr/local/bin/martin

COPY --chown=101:101 styles /styles
COPY --from=glyphs --chown=101:101 /glyphs/output /styles/fonts
COPY --chown=101:101 tiles/nginx.conf /etc/nginx/nginx.conf
COPY --chmod=755 --chown=101:101 tiles/entrypoint.sh /entrypoint.sh

USER 101:101

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
