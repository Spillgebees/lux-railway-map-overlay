import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# 1 MB buffer for streaming large file downloads
_COPY_BUFFER_SIZE = 1 << 20

USER_AGENT = (
    "lux-railway-map-overlay (+https://github.com/Spillgebees/lux-railway-map-overlay)"
)

# socket timeout per blocking operation (connect or read), not for the whole body
DOWNLOAD_TIMEOUT_SECONDS = 120
DOWNLOAD_MAX_ATTEMPTS = 4
RETRY_BASE_DELAY_SECONDS = 5.0
RETRY_MAX_DELAY_SECONDS = 60.0
OVERPASS_TIMEOUT_SECONDS = 180
# each mirror is tried this many times before giving up
OVERPASS_ROUNDS = 2

_MD5_PATTERN = re.compile(r"^[0-9a-f]{32}$")

type Logger = Callable[[str], None]
type Downloader = Callable[[str, Path], None]
type CommandRunner = Callable[[list[str]], None]
type Sleeper = Callable[[float], None]
type UrlOpener = Callable[..., Any]


class PipelineError(RuntimeError):
    pass


class DownloadVerificationError(PipelineError):
    """A download finished but its size or checksum does not match."""


class OverpassError(PipelineError):
    """Every Overpass attempt failed or returned an unusable response."""


def _ignore(_message: str) -> None:
    return None


def check_required_tools(tool_names: Iterable[str]) -> None:
    missing_tools = [
        tool_name for tool_name in tool_names if shutil.which(tool_name) is None
    ]
    if missing_tools:
        raise PipelineError(f"Missing required tool(s): {', '.join(missing_tools)}")


def load_geojson(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(path.read_text(encoding="utf-8"))


def backoff_delay(attempt: int) -> float:
    """Delay before retry number ``attempt`` (1-based): 5s, 10s, 20s, ... capped."""
    return min(RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)), RETRY_MAX_DELAY_SECONDS)


def is_transient_error(error: BaseException) -> bool:
    """Whether retrying the same request could plausibly succeed."""
    if isinstance(error, urllib.error.HTTPError):
        return error.code == 429 or error.code >= 500
    if isinstance(error, DownloadVerificationError):
        # truncated or corrupted transfer
        return True
    # TimeoutError and ConnectionError are OSError subclasses, as is URLError;
    # a connection dropped mid-body surfaces as http.client.IncompleteRead
    return isinstance(error, (OSError, http.client.HTTPException))


def describe_error(error: BaseException) -> str:
    if isinstance(error, urllib.error.HTTPError):
        return f"HTTP {error.code} {error.reason}"
    if isinstance(error, urllib.error.URLError):
        return str(error.reason)
    return str(error) or type(error).__name__


def retry_transient[T](
    operation: Callable[[], T],
    *,
    description: str,
    max_attempts: int,
    sleep: Sleeper = time.sleep,
    warn: Logger = _ignore,
) -> T:
    """Run ``operation``, retrying transient failures with exponential backoff."""
    attempt = 1
    while True:
        try:
            return operation()
        except Exception as error:
            if attempt >= max_attempts or not is_transient_error(error):
                raise
            delay = backoff_delay(attempt)
            warn(
                f"{description} failed ({describe_error(error)}); "
                f"retrying in {delay:.0f}s (attempt {attempt + 1}/{max_attempts})"
            )
            sleep(delay)
            attempt += 1


def part_path_for(path: Path) -> Path:
    return path.with_name(f"{path.name}.part")


def download_record_path(path: Path) -> Path:
    """Sidecar written next to a verified download."""
    return path.with_name(f"{path.name}.download.json")


def write_bytes_atomic(path: Path, data: bytes) -> None:
    part_path = part_path_for(path)
    try:
        part_path.write_bytes(data)
        os.replace(part_path, path)
    except BaseException:
        part_path.unlink(missing_ok=True)
        raise


def is_verified_download(path: Path) -> bool:
    """Cheap reuse check for a cached download.

    A file counts as verified only if its sidecar exists and records the same
    size. The MD5 was checked when the file was downloaded; re-hashing several
    GB on every run is not worth it, and truncation is caught by the size check.
    """
    record_path = download_record_path(path)
    if not path.is_file() or not record_path.is_file():
        return False
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return False
    return (
        isinstance(record, dict)
        and record.get("size") == path.stat().st_size
        and isinstance(record.get("md5"), str)
    )


def parse_md5_file(text: str) -> str:
    """Parse an md5sum-style line (``<hash>  <filename>``) and return the hash."""
    fields = text.split()
    checksum = fields[0].lower() if fields else ""
    if not _MD5_PATTERN.match(checksum):
        raise DownloadVerificationError(f"Malformed checksum file: {text[:80]!r}")
    return checksum


def _content_length(response: Any) -> int | None:
    value = response.headers.get("Content-Length")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def fetch_md5(url: str, *, opener: UrlOpener | None = None) -> str:
    urlopen = opener or urllib.request.urlopen
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        return parse_md5_file(response.read(4096).decode("utf-8", errors="replace"))


def _download_once(url: str, output_path: Path, opener: UrlOpener) -> None:
    part_path = part_path_for(output_path)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            # Geofabrik redirects *-latest to a dated file; checking the dated
            # .md5 avoids a mismatch when the daily extract rolls over mid-run.
            final_url = response.geturl() or url
            expected_md5 = fetch_md5(f"{final_url}.md5", opener=opener)
            expected_size = _content_length(response)

            digest = hashlib.md5()
            size = 0
            with open(part_path, "wb") as out:
                while chunk := response.read(_COPY_BUFFER_SIZE):
                    out.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)

        if expected_size is not None and size != expected_size:
            raise DownloadVerificationError(
                f"Incomplete download: got {size} of {expected_size} bytes"
            )
        actual_md5 = digest.hexdigest()
        if actual_md5 != expected_md5:
            raise DownloadVerificationError(
                f"MD5 mismatch: expected {expected_md5}, got {actual_md5}"
            )

        # sidecar first: a crash before the rename leaves a record that does
        # not match whatever file is (or is not) in place, so it is not reused
        record = {"url": final_url, "size": size, "md5": actual_md5}
        write_bytes_atomic(
            download_record_path(output_path),
            (json.dumps(record) + "\n").encode("utf-8"),
        )
        os.replace(part_path, output_path)
    except BaseException:
        part_path.unlink(missing_ok=True)
        raise


def download_file(
    url: str,
    output_path: Path,
    *,
    opener: UrlOpener | None = None,
    sleep: Sleeper = time.sleep,
    warn: Logger = _ignore,
    max_attempts: int = DOWNLOAD_MAX_ATTEMPTS,
) -> None:
    """Download ``url`` to ``output_path`` and verify it before it appears there.

    The body is streamed to ``<name>.part``, checked against Content-Length and
    the published ``<url>.md5``, then renamed into place. A sidecar
    ``<name>.download.json`` records the verified size and checksum.
    """
    urlopen = opener or urllib.request.urlopen
    retry_transient(
        lambda: _download_once(url, output_path, urlopen),
        description=f"Download of {output_path.name}",
        max_attempts=max_attempts,
        sleep=sleep,
        warn=warn,
    )


def validate_overpass_payload(body: bytes) -> dict[str, Any]:
    """Parse an Overpass JSON response and reject failed or partial results.

    Overpass can answer HTTP 200 with partial data and a ``remark`` such as
    ``runtime error: Query timed out ...`` or ``runtime error: Query run out
    of memory ...``. Any remark is treated as a failure so an incomplete
    route set is never cached or published.
    """
    try:
        payload = json.loads(body)
    except ValueError as error:
        raise OverpassError(f"response is not valid JSON ({error})") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise OverpassError("response has no 'elements' list")
    remark = payload.get("remark")
    if remark:
        raise OverpassError(f"response carries remark: {str(remark).strip()}")
    return payload


def download_overpass(
    query: str,
    output_path: Path,
    api_urls: tuple[str, ...],
    *,
    opener: UrlOpener | None = None,
    sleep: Sleeper = time.sleep,
    warn: Logger = _ignore,
    rounds: int = OVERPASS_ROUNDS,
) -> None:
    """Query Overpass mirrors in turn and cache the first valid response.

    Each mirror is tried ``rounds`` times, with exponential backoff between
    attempts. ``output_path`` is written atomically, and only after the
    response passes ``validate_overpass_payload``. Raises ``OverpassError``
    when every attempt fails.
    """
    urlopen = opener or urllib.request.urlopen
    request_body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    attempts = [api_url for _ in range(rounds) for api_url in api_urls]
    failures: list[str] = []

    for attempt, api_url in enumerate(attempts, start=1):
        if attempt > 1:
            delay = backoff_delay(attempt - 1)
            warn(f"Retrying Overpass via {api_url} in {delay:.0f}s")
            sleep(delay)

        request = urllib.request.Request(
            api_url,
            data=request_body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urlopen(request, timeout=OVERPASS_TIMEOUT_SECONDS) as response:
                body = response.read()
            validate_overpass_payload(body)
        except (OverpassError, OSError, http.client.HTTPException) as error:
            # URLError, TimeoutError and ConnectionError are OSError subclasses;
            # IncompleteRead (dropped connection) is an HTTPException
            failure = f"{api_url}: {describe_error(error)}"
            failures.append(failure)
            warn(f"Overpass query failed ({failure})")
            continue

        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(output_path, body)
        return

    if not failures:
        raise OverpassError("no Overpass API URLs configured")
    raise OverpassError(
        f"all {len(failures)} attempt(s) failed: " + "; ".join(failures)
    )


def ogr2ogr(
    output_path: Path,
    source_path: Path,
    output_format: str,
    sql: str,
    *,
    extra_args: list[str],
    target_srs: str,
    osmconf_path: Path,
) -> None:
    args = [
        "ogr2ogr",
        "-f",
        output_format,
        str(output_path),
        str(source_path),
        "--config",
        "OSM_CONFIG_FILE",
        str(osmconf_path),
        # disable custom indexing; filtered extracts stream without GDAL temp indexes.
        "--config",
        "OSM_USE_CUSTOM_INDEXING",
        "NO",
        "-t_srs",
        target_srs,
        "-sql",
        sql,
        *extra_args,
    ]
    run_command(args)


def run_command(args: list[str]) -> None:
    try:
        subprocess.run(args, check=True)
    except subprocess.CalledProcessError as error:
        command = " ".join(args)
        raise PipelineError(
            f"Command failed with exit code {error.returncode}: {command}"
        ) from error


def require_existing_file(path: Path, description: str) -> Path:
    if not path.exists():
        raise PipelineError(f"{description} not found at: {path}")
    return path


def tippecanoe_layer_arg(
    geojson_dir: Path, file_stem: str, layer_name: str, minzoom: int
) -> str:
    return (
        f'-L{{"file":"{geojson_dir / f"{file_stem}.geojson"}", '
        f'"layer":"{layer_name}", "minzoom":{minzoom}}}'
    )


def print_summary_file(path: Path, label: str, size_formatter) -> None:
    if path.exists():
        print(f"  {label:<40} {size_formatter(path.stat().st_size)}")


def write_empty_geojson(output_path: Path) -> None:
    output_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )


def run_commands_parallel(
    commands: list[list[str]],
    *,
    max_workers: int | None = None,
) -> None:
    """Run multiple subprocess commands in parallel, raising on first failure."""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_command, cmd): cmd for cmd in commands}
        for future in as_completed(futures):
            future.result()
