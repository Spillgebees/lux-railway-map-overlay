#!/bin/sh
set -eu

MARTIN_PID=""
NGINX_PID=""
MBTILES_PATH="${MBTILES_PATH:-}"

cleanup() {
    if [ -n "${NGINX_PID}" ]; then
        kill "${NGINX_PID}" 2>/dev/null || true
    fi

    if [ -n "${MARTIN_PID}" ]; then
        kill "${MARTIN_PID}" 2>/dev/null || true
    fi
}

trap 'cleanup; exit 0' INT TERM
trap cleanup EXIT

echo "=== lux-railway-map-overlay tile server ==="

mkdir -p \
    /tmp/nginx/client_temp \
    /tmp/nginx/proxy_temp \
    /tmp/nginx/fastcgi_temp \
    /tmp/nginx/uwsgi_temp \
    /tmp/nginx/scgi_temp

# Validate required files
if [ -n "${MBTILES_PATH:-}" ]; then
    if [ ! -f "${MBTILES_PATH}" ]; then
        echo "ERROR: MBTILES_PATH is set but does not exist: ${MBTILES_PATH}"
        exit 1
    fi
elif [ -f /app/data/lux-railway-map-overlay.mbtiles ]; then
    MBTILES_PATH="/app/data/lux-railway-map-overlay.mbtiles"
elif [ -f /data/out/lux-railway-map-overlay.mbtiles ]; then
    MBTILES_PATH="/data/out/lux-railway-map-overlay.mbtiles"
else
    echo "ERROR: No MBTiles found. Checked:"
    echo ""
    echo "  MBTILES_PATH env var"
    echo "  /app/data/lux-railway-map-overlay.mbtiles"
    echo "  /data/out/lux-railway-map-overlay.mbtiles"
    echo ""
    echo "For local development, generate data first:"
    echo "  docker compose --profile generate run --rm generate"
    echo ""
    echo "For production, use the baked image published by CI."
    exit 1
fi

echo "Using MBTiles: ${MBTILES_PATH}"

if [ ! -f /styles/style.json ]; then
    echo "ERROR: No style.json found at /styles/style.json"
    exit 1
fi

# Rewrite URLs in style.json for the target environment
PUBLIC_URL="${PUBLIC_URL:-http://localhost:3000}"
# Strip trailing slash to avoid double slashes
PUBLIC_URL="${PUBLIC_URL%/}"

echo "Public URL: ${PUBLIC_URL}"

cp /styles/style.json /tmp/style.json
sed -i "s|http://localhost:3000|${PUBLIC_URL}|g" /tmp/style.json

# Start Martin in the background on port 3001
echo "Starting Martin tile server..."
martin \
    --listen-addresses 127.0.0.1:3001 \
    --base-url "${PUBLIC_URL}" \
    --sprite /styles/symbols \
    "${MBTILES_PATH}" &

MARTIN_PID=$!

# Wait for Martin to be ready
echo "Waiting for Martin..."
for i in $(seq 1 30); do
    if wget -q --spider http://127.0.0.1:3001/health 2>/dev/null; then
        echo "Martin is ready"
        break
    fi
    if ! kill -0 "${MARTIN_PID}" 2>/dev/null; then
        echo "ERROR: Martin crashed during startup"
        exit 1
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Martin failed to start"
        exit 1
    fi
    sleep 1
done

# Start nginx and keep both processes under PID 1 supervision
echo "Starting nginx on port 8080..."
nginx -g "daemon off;" &
NGINX_PID=$!

while :; do
    if ! kill -0 "${MARTIN_PID}" 2>/dev/null; then
        echo "ERROR: Martin exited unexpectedly"
        exit 1
    fi

    if ! kill -0 "${NGINX_PID}" 2>/dev/null; then
        echo "ERROR: nginx exited unexpectedly"
        exit 1
    fi

    sleep 5
done
