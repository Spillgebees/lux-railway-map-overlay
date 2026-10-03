from __future__ import annotations

import hashlib
import io
import json
import urllib.error
import urllib.request

import pytest

from generator.pipeline_support import (
    DownloadVerificationError,
    PipelineError,
    backoff_delay,
    check_required_tools,
    download_file,
    download_overpass,
    download_record_path,
    is_verified_download,
    part_path_for,
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


PBF_URL = "https://download.example/europe/luxembourg-latest.osm.pbf"
DATED_PBF_URL = "https://download.example/europe/luxembourg-261002.osm.pbf"
PBF_BODY = b"pbf-bytes" * 100
PBF_MD5 = hashlib.md5(PBF_BODY).hexdigest()


class FakeHttpResponse:
    """Minimal stand-in for the object returned by urllib.request.urlopen."""

    def __init__(
        self,
        body: bytes,
        *,
        url: str = "",
        content_length: int | None = None,
        fail_after: int | None = None,
        error: BaseException | None = None,
    ) -> None:
        self._stream = io.BytesIO(body)
        self._url = url
        self._fail_after = fail_after
        self._error = error or ConnectionResetError("connection reset by peer")
        self.headers = (
            {} if content_length is None else {"Content-Length": str(content_length)}
        )

    def geturl(self) -> str:
        return self._url

    def read(self, size: int = -1) -> bytes:
        if self._fail_after is not None and self._stream.tell() >= self._fail_after:
            raise self._error
        if self._fail_after is not None:
            size = self._fail_after - self._stream.tell()
        return self._stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeOpener:
    """Serves queued responses (or exceptions) per URL and records requests."""

    def __init__(self, responses: dict[str, list]) -> None:
        self._responses = responses
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        queue = self._responses[request.full_url]
        outcome = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome()

    def urls(self) -> list[str]:
        return [request.full_url for request in self.requests]


def pbf_response(body: bytes = PBF_BODY, **kwargs):
    kwargs.setdefault("url", DATED_PBF_URL)
    kwargs.setdefault("content_length", len(PBF_BODY))
    return lambda: FakeHttpResponse(body, **kwargs)


def md5_response(checksum: str = PBF_MD5):
    return lambda: FakeHttpResponse(
        f"{checksum}  luxembourg-261002.osm.pbf\n".encode("utf-8")
    )


def assert_no_download_artifacts(output_path) -> None:
    assert not output_path.exists()
    assert not part_path_for(output_path).exists()
    assert not download_record_path(output_path).exists()


def test_download_file_verifies_and_moves_into_place(tmp_path) -> None:
    # arrange
    output_path = tmp_path / "luxembourg-latest.osm.pbf"
    opener = FakeOpener(
        {PBF_URL: [pbf_response()], f"{DATED_PBF_URL}.md5": [md5_response()]}
    )

    # act
    download_file(PBF_URL, output_path, opener=opener, sleep=lambda delay: None)

    # assert
    assert output_path.read_bytes() == PBF_BODY
    assert not part_path_for(output_path).exists()
    assert json.loads(download_record_path(output_path).read_text("utf-8")) == {
        "url": DATED_PBF_URL,
        "size": len(PBF_BODY),
        "md5": PBF_MD5,
    }
    assert is_verified_download(output_path)
    assert opener.urls() == [PBF_URL, f"{DATED_PBF_URL}.md5"]
    assert all(
        "github.com/Spillgebees/lux-railway-map-overlay"
        in request.get_header("User-agent")
        for request in opener.requests
    )


def test_download_file_cleans_up_interrupted_download(tmp_path) -> None:
    # arrange
    output_path = tmp_path / "luxembourg-latest.osm.pbf"
    opener = FakeOpener(
        {
            PBF_URL: [pbf_response(fail_after=100)],
            f"{DATED_PBF_URL}.md5": [md5_response()],
        }
    )
    sleeps: list[float] = []

    # act
    with pytest.raises(ConnectionResetError):
        download_file(
            PBF_URL, output_path, opener=opener, sleep=sleeps.append, max_attempts=2
        )

    # assert
    assert_no_download_artifacts(output_path)
    assert sleeps == [5.0]


def test_download_file_rejects_size_mismatch(tmp_path) -> None:
    # arrange
    output_path = tmp_path / "luxembourg-latest.osm.pbf"
    opener = FakeOpener(
        {
            PBF_URL: [pbf_response(content_length=len(PBF_BODY) + 10)],
            f"{DATED_PBF_URL}.md5": [md5_response()],
        }
    )

    # act
    with pytest.raises(DownloadVerificationError, match=r"Incomplete download"):
        download_file(PBF_URL, output_path, opener=opener, max_attempts=1)

    # assert
    assert_no_download_artifacts(output_path)


def test_download_file_rejects_md5_mismatch(tmp_path) -> None:
    # arrange
    output_path = tmp_path / "luxembourg-latest.osm.pbf"
    opener = FakeOpener(
        {
            PBF_URL: [pbf_response()],
            f"{DATED_PBF_URL}.md5": [md5_response("0" * 32)],
        }
    )

    # act
    with pytest.raises(DownloadVerificationError, match=r"MD5 mismatch"):
        download_file(PBF_URL, output_path, opener=opener, max_attempts=1)

    # assert
    assert_no_download_artifacts(output_path)


def test_download_file_rejects_malformed_checksum_file(tmp_path) -> None:
    # arrange
    output_path = tmp_path / "luxembourg-latest.osm.pbf"
    opener = FakeOpener(
        {
            PBF_URL: [pbf_response()],
            f"{DATED_PBF_URL}.md5": [lambda: FakeHttpResponse(b"<html>oops</html>")],
        }
    )

    # act
    with pytest.raises(DownloadVerificationError, match=r"Malformed checksum"):
        download_file(PBF_URL, output_path, opener=opener, max_attempts=1)

    # assert
    assert_no_download_artifacts(output_path)


def test_download_file_retries_transient_errors_then_succeeds(tmp_path) -> None:
    # arrange
    output_path = tmp_path / "luxembourg-latest.osm.pbf"
    opener = FakeOpener(
        {
            PBF_URL: [
                urllib.error.HTTPError(PBF_URL, 503, "Service Unavailable", {}, None),
                TimeoutError("timed out"),
                pbf_response(fail_after=10),
                pbf_response(),
            ],
            f"{DATED_PBF_URL}.md5": [md5_response()],
        }
    )
    sleeps: list[float] = []
    warnings: list[str] = []

    # act
    download_file(
        PBF_URL, output_path, opener=opener, sleep=sleeps.append, warn=warnings.append
    )

    # assert
    assert output_path.read_bytes() == PBF_BODY
    assert not part_path_for(output_path).exists()
    assert sleeps == [5.0, 10.0, 20.0]
    assert warnings[0] == (
        "Download of luxembourg-latest.osm.pbf failed (HTTP 503 Service Unavailable); "
        "retrying in 5s (attempt 2/4)"
    )


def test_download_file_does_not_retry_client_errors(tmp_path) -> None:
    # arrange
    output_path = tmp_path / "luxembourg-latest.osm.pbf"
    opener = FakeOpener(
        {PBF_URL: [urllib.error.HTTPError(PBF_URL, 404, "Not Found", {}, None)]}
    )
    sleeps: list[float] = []

    # act
    with pytest.raises(urllib.error.HTTPError):
        download_file(PBF_URL, output_path, opener=opener, sleep=sleeps.append)

    # assert
    assert sleeps == []
    assert len(opener.requests) == 1
    assert_no_download_artifacts(output_path)


def test_backoff_delay_doubles_and_is_capped() -> None:
    assert [backoff_delay(attempt) for attempt in range(1, 7)] == [
        5.0,
        10.0,
        20.0,
        40.0,
        60.0,
        60.0,
    ]


def test_is_verified_download_requires_matching_record(tmp_path) -> None:
    # arrange
    path = tmp_path / "luxembourg-latest.osm.pbf"
    path.write_bytes(b"data")

    # act / assert
    assert not is_verified_download(path)
    download_record_path(path).write_text(
        json.dumps({"size": 4, "md5": hashlib.md5(b"data").hexdigest()}),
        encoding="utf-8",
    )
    assert is_verified_download(path)
    path.write_bytes(b"da")
    assert not is_verified_download(path)
    download_record_path(path).write_text("not json", encoding="utf-8")
    assert not is_verified_download(path)


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
    assert tippecanoe_layer_arg(tmp_path, "rail_routes", "rail_routes", 5) == (
        f'-L{{"file":"{tmp_path / "rail_routes.geojson"}", '
        '"layer":"rail_routes", "minzoom":5}'
    )
