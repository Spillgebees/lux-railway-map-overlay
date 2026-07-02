FROM debian:bookworm-slim@sha256:60eac759739651111db372c07be67863818726f754804b8707c90979bda511df AS glyphs

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

FROM ghcr.io/maplibre/martin:1.11.0@sha256:0650e9025f5fcffdc686358114679421b5e6b0ca37b374ad8a66f14709d59d2b

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    nginx \
    wget \
    && if getent group 101 >/dev/null; then :; elif getent group app >/dev/null; then groupmod --gid 101 app; else groupadd --system --gid 101 app; fi \
    && if getent passwd 101 >/dev/null; then :; elif getent passwd app >/dev/null; then usermod --uid 101 --gid 101 --home-dir /nonexistent --shell /usr/sbin/nologin app; else useradd --system --uid 101 --gid 101 --home-dir /nonexistent --shell /usr/sbin/nologin app; fi \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /etc/nginx/sites-enabled /etc/nginx/conf.d /var/www/html

COPY --chown=101:101 styles /styles
COPY --from=glyphs --chown=101:101 /glyphs/output /styles/fonts
COPY --chown=101:101 tiles/nginx.conf /etc/nginx/nginx.conf
COPY --chmod=755 --chown=101:101 tiles/entrypoint.sh /entrypoint.sh

USER 101:101

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
