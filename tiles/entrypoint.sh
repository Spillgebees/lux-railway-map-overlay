#!/usr/bin/env bash
set -euo pipefail

# The base URL that styles/style.json uses. The entrypoint replaces it with
# PUBLIC_URL in the runtime copy of the style.
readonly STYLE_BASE_URL="http://localhost:3000"
readonly DEFAULT_PUBLIC_URL="http://localhost:3000"

MARTIN_PID=""
NGINX_PID=""
MBTILES_PATH="${MBTILES_PATH:-}"

# Prints the URL without trailing slashes. Fails unless it is an http(s) URL
# without whitespace, control characters, query string, or fragment, because
# the style appends paths to it.
normalize_public_url() {
    local url="$1"

    while [[ "${url}" == */ ]]; do
        url="${url%/}"
    done

    if [[ ! "${url}" =~ ^https?://[^/?#]+(/[^?#]*)?$ ]] || [[ "${url}" =~ [[:space:][:cntrl:]] ]]; then
        echo "ERROR: PUBLIC_URL must be an http:// or https:// URL without a query string or fragment, got: $1" >&2
        return 1
    fi

    printf '%s' "${url}"
}

# Escapes a value for use inside a JSON string.
json_escape() {
    local value="$1"
    local backslash="\\"
    local quote='"'

    # Quoted replacements are literal, even with bash 5.2's patsub_replacement,
    # which otherwise expands & to the matched text.
    value="${value//"${backslash}"/"${backslash}${backslash}"}"
    value="${value//"${quote}"/"${backslash}${quote}"}"
    printf '%s' "${value}"
}

# Copies the style from $1 to $2 and replaces STYLE_BASE_URL with $3. Plain
# string replacement, so characters such as |, & and \ in the URL stay as they
# are.
rewrite_style_urls() {
    local source="$1"
    local target="$2"
    local url
    local style

    url="$(json_escape "$3")"
    style="$(<"${source}")"
    printf '%s\n' "${style//"${STYLE_BASE_URL}"/"${url}"}" >"${target}"
}

# Sends signal $1 to the children that have started.
signal_children() {
    local pid

    for pid in "${NGINX_PID}" "${MARTIN_PID}"; do
        if [ -n "${pid}" ]; then
            kill "-$1" "${pid}" 2>/dev/null || true
        fi
    done
}

# Waits until every started child has exited, whatever its status.
wait_for_children() {
    local pid

    for pid in "${NGINX_PID}" "${MARTIN_PID}"; do
        if [ -n "${pid}" ]; then
            wait "${pid}" 2>/dev/null || true
        fi
    done
}

# INT/TERM handler. Both signals are passed on as SIGTERM, because bash starts
# background jobs with SIGINT ignored. A stop request is a clean exit, so this
# exits 0 once both children are gone.
shutdown() {
    trap '' INT TERM

    echo "Received SIG$1, stopping nginx and Martin..."
    signal_children TERM
    wait_for_children
    exit 0
}

# Blocks until nginx or Martin exits, then stops the other one and exits with
# the status of the one that exited, or 1 if that status was 0. A server that
# exits without a stop request has failed either way.
supervise() {
    local exited_pid=""
    local status=0
    local name

    wait -n -p exited_pid "${MARTIN_PID}" "${NGINX_PID}" || status=$?

    case "${exited_pid}" in
    "${MARTIN_PID}") name="Martin" ;;
    "${NGINX_PID}") name="nginx" ;;
    *) name="A child process" ;;
    esac

    echo "ERROR: ${name} exited unexpectedly with status ${status}"

    if [ "${status}" -eq 0 ]; then
        status=1
    fi

    signal_children TERM
    wait_for_children
    exit "${status}"
}

main() {
    trap 'shutdown INT' INT
    trap 'shutdown TERM' TERM
    trap 'signal_children TERM' EXIT

    echo "=== lux-railway-map-overlay tile server ==="

    mkdir -p \
        /tmp/nginx/client_temp \
        /tmp/nginx/proxy_cache \
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
    elif [ -f /data/lux-railway-map-overlay.mbtiles ]; then
        MBTILES_PATH="/data/lux-railway-map-overlay.mbtiles"
    elif [ -f /data/out/lux-railway-map-overlay.mbtiles ]; then
        MBTILES_PATH="/data/out/lux-railway-map-overlay.mbtiles"
    else
        echo "ERROR: No MBTiles found. Checked:"
        echo ""
        echo "  MBTILES_PATH env var"
        echo "  /app/data/lux-railway-map-overlay.mbtiles"
        echo "  /data/lux-railway-map-overlay.mbtiles"
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
    local public_url
    public_url="$(normalize_public_url "${PUBLIC_URL:-${DEFAULT_PUBLIC_URL}}")"

    echo "Public URL: ${public_url}"

    rewrite_style_urls /styles/style.json /tmp/style.json "${public_url}"

    # Start Martin in the background on port 3001
    echo "Starting Martin tile server..."
    martin \
        --listen-addresses 127.0.0.1:3001 \
        --sprite /styles/symbols \
        "${MBTILES_PATH}" &

    MARTIN_PID=$!

    # Wait for Martin to be ready
    echo "Waiting for Martin..."
    local i
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

    # Start nginx, then supervise both processes as PID 1
    echo "Starting nginx on ports 8080 (tiles) and 9090 (metrics)..."
    nginx -g "daemon off;" &
    NGINX_PID=$!

    supervise
}

# Tests source this file to call the functions above without starting the server.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
