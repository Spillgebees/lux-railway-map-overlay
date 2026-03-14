from __future__ import annotations

import io
import json
import urllib.error

import pytest

from generator.pipeline_support import (
    PipelineError,
    check_required_tools,
    download_overpass,
    load_geojson,
    require_existing_file,
    tippecanoe_layer_arg,
    write_empty_geojson,
)


def test_check_required_tools_raises_for_missing_tool(monkeypatch) -> None:
    monkeypatch.setattr(
        "generator.pipeline_support.shutil.which",
        lambda tool_name: (
            None if tool_name == "tippecanoe" else f"/usr/bin/{tool_name}"
        ),
    )

    with pytest.raises(PipelineError, match=r"Missing required tool\(s\): tippecanoe"):
        check_required_tools(["osmium", "tippecanoe"])


def test_load_geojson_returns_empty_collection_when_file_is_missing(tmp_path) -> None:
    assert load_geojson(tmp_path / "missing.geojson") == {
        "type": "FeatureCollection",
        "features": [],
    }


def test_write_empty_geojson_creates_empty_feature_collection(tmp_path) -> None:
    output_path = tmp_path / "empty.geojson"

    write_empty_geojson(output_path)

    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "type": "FeatureCollection",
        "features": [],
    }


def test_require_existing_file_raises_pipeline_error_for_missing_path(tmp_path) -> None:
    with pytest.raises(PipelineError, match=r"osmconf.ini not found"):
        require_existing_file(tmp_path / "osmconf.ini", "osmconf.ini")


def test_download_overpass_uses_fallback_endpoint(monkeypatch, tmp_path) -> None:
    output_path = tmp_path / "routes.json"

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._stream = io.BytesIO(body)

        def read(self, size: int = -1) -> bytes:
            return self._stream.read(size)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_urlopen(request, timeout=180):
        if request.full_url == "https://first.example/api":
            raise urllib.error.URLError("primary down")
        return FakeResponse(b'{"elements": []}')

    monkeypatch.setattr(
        "generator.pipeline_support.urllib.request.urlopen", fake_urlopen
    )

    download_overpass(
        "[out:json];relation[route=train];out;",
        output_path,
        ("https://first.example/api", "https://second.example/api"),
    )

    assert json.loads(output_path.read_text(encoding="utf-8")) == {"elements": []}


def test_run_commands_parallel_executes_all_commands(monkeypatch) -> None:
    """Verify all commands are executed."""
    executed = []
    monkeypatch.setattr(
        "generator.pipeline_support.run_command",
        lambda cmd: executed.append(cmd),
    )
    from generator.pipeline_support import run_commands_parallel

    run_commands_parallel([["echo", "a"], ["echo", "b"], ["echo", "c"]])
    assert sorted(executed) == sorted([["echo", "a"], ["echo", "b"], ["echo", "c"]])


def test_run_commands_parallel_propagates_first_failure(monkeypatch) -> None:
    """Verify that a PipelineError from a worker thread is re-raised."""
    from generator.pipeline_support import run_commands_parallel

    def fake_run(cmd):
        if cmd == ["fail"]:
            raise PipelineError("boom")

    monkeypatch.setattr("generator.pipeline_support.run_command", fake_run)
    with pytest.raises(PipelineError, match="boom"):
        run_commands_parallel([["ok"], ["fail"]])


def test_run_commands_parallel_handles_empty_list(monkeypatch) -> None:
    """Empty command list should be a no-op."""
    from generator.pipeline_support import run_commands_parallel

    monkeypatch.setattr("generator.pipeline_support.run_command", lambda cmd: None)
    run_commands_parallel([])  # should not raise


def test_run_command_wraps_subprocess_error(monkeypatch) -> None:
    import subprocess

    from generator.pipeline_support import run_command

    def fake_subprocess_run(args, check):
        raise subprocess.CalledProcessError(42, args)

    monkeypatch.setattr(
        "generator.pipeline_support.subprocess.run", fake_subprocess_run
    )
    with pytest.raises(PipelineError, match="exit code 42"):
        run_command(["some", "command"])


def test_tippecanoe_layer_arg_uses_geojson_dir_and_metadata(tmp_path) -> None:
    assert tippecanoe_layer_arg(tmp_path, "railway_routes", "railway_routes", 5) == (
        f'-L{{"file":"{tmp_path / "railway_routes.geojson"}", '
        '"layer":"railway_routes", "minzoom":5}'
    )
