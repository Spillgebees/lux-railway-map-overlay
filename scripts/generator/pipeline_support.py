from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# 1 MB buffer for streaming large file downloads
_COPY_BUFFER_SIZE = 1 << 20


class PipelineError(RuntimeError):
    pass


def check_required_tools(tool_names: list[str]) -> None:
    missing_tools = [
        tool_name for tool_name in tool_names if shutil.which(tool_name) is None
    ]
    if missing_tools:
        raise PipelineError(f"Missing required tool(s): {', '.join(missing_tools)}")


def load_geojson(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(path.read_text(encoding="utf-8"))


def download_file(url: str, output_path: Path) -> None:
    with urllib.request.urlopen(url, timeout=600) as response:
        with open(output_path, "wb") as out:
            shutil.copyfileobj(response, out, length=_COPY_BUFFER_SIZE)


def download_overpass(query: str, output_path: Path, api_urls: tuple[str, ...]) -> None:
    request_body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    last_error: urllib.error.URLError | None = None

    for api_url in api_urls:
        request = urllib.request.Request(
            api_url,
            data=request_body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "lux-railway-map-overlay/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                with open(output_path, "wb") as out:
                    shutil.copyfileobj(response, out)
                return
        except urllib.error.URLError as error:
            last_error = error

    if last_error is not None:
        raise last_error
    raise PipelineError("Overpass download failed without a reported error")


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
