from __future__ import annotations

import hashlib
import http.client
import io
import json
import urllib.error
import urllib.request

import pytest

from generator.pipeline_support import (
    DownloadVerificationError,
    OverpassError,
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
    validate_overpass_payload,
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
        sleep=lambda delay: None,
    )

    assert json.loads(output_path.read_text(encoding="utf-8")) == {"elements": []}


OVERPASS_URLS = ("https://first.example/api", "https://second.example/api")
OVERPASS_QUERY = "[out:json];relation[route=train];out;"


def overpass_response(payload: dict):
    return lambda: FakeHttpResponse(json.dumps(payload).encode("utf-8"))


@pytest.mark.parametrize(
    "remark",
    [
        'runtime error: Query timed out in "recurse" at line 1 after 121 seconds.',
        "runtime error: Query run out of memory using about 2048 MB of RAM.",
    ],
)
def test_download_overpass_rejects_runtime_error_remark(tmp_path, remark) -> None:
    # arrange
    output_path = tmp_path / "routes.json"
    partial = {"elements": [{"type": "node", "id": 1}], "remark": remark}
    opener = FakeOpener({url: [overpass_response(partial)] for url in OVERPASS_URLS})
    warnings: list[str] = []

    # act
    with pytest.raises(OverpassError, match=r"remark: runtime error"):
        download_overpass(
            OVERPASS_QUERY,
            output_path,
            OVERPASS_URLS,
            opener=opener,
            sleep=lambda delay: None,
            warn=warnings.append,
        )

    # assert
    assert not output_path.exists()
    assert not part_path_for(output_path).exists()
    assert len(opener.requests) == 4
    assert all(
        "runtime error" in warning for warning in warnings if "failed" in warning
    )


def test_download_overpass_falls_through_on_remark_to_next_mirror(tmp_path) -> None:
    # arrange
    output_path = tmp_path / "routes.json"
    good = {"elements": [{"type": "relation", "id": 7}]}
    opener = FakeOpener(
        {
            OVERPASS_URLS[0]: [
                overpass_response({"elements": [], "remark": "runtime error: x"})
            ],
            OVERPASS_URLS[1]: [overpass_response(good)],
        }
    )

    # act
    download_overpass(
        OVERPASS_QUERY,
        output_path,
        OVERPASS_URLS,
        opener=opener,
        sleep=lambda delay: None,
    )

    # assert
    assert json.loads(output_path.read_text(encoding="utf-8")) == good


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("The read operation timed out"),
        ConnectionResetError("connection reset by peer"),
        http.client.IncompleteRead(b"{", 100),
        urllib.error.HTTPError(OVERPASS_URLS[0], 504, "Gateway Timeout", {}, None),
    ],
)
def test_download_overpass_moves_to_next_mirror_after_error(tmp_path, error) -> None:
    # arrange
    output_path = tmp_path / "routes.json"
    opener = FakeOpener(
        {
            OVERPASS_URLS[0]: [error],
            OVERPASS_URLS[1]: [overpass_response({"elements": []})],
        }
    )
    sleeps: list[float] = []

    # act
    download_overpass(
        OVERPASS_QUERY, output_path, OVERPASS_URLS, opener=opener, sleep=sleeps.append
    )

    # assert
    assert opener.urls() == list(OVERPASS_URLS)
    assert sleeps == [5.0]
    assert json.loads(output_path.read_text(encoding="utf-8")) == {"elements": []}


def test_download_overpass_retries_mirrors_with_backoff_and_keeps_cache_on_failure(
    tmp_path,
) -> None:
    # arrange
    output_path = tmp_path / "routes.json"
    output_path.write_text('{"elements": ["previous"]}', encoding="utf-8")
    opener = FakeOpener(
        {
            OVERPASS_URLS[0]: [TimeoutError("timed out")],
            OVERPASS_URLS[1]: [lambda: FakeHttpResponse(b"<html>busy</html>")],
        }
    )
    sleeps: list[float] = []

    # act
    with pytest.raises(OverpassError, match=r"all 4 attempt\(s\) failed"):
        download_overpass(
            OVERPASS_QUERY,
            output_path,
            OVERPASS_URLS,
            opener=opener,
            sleep=sleeps.append,
        )

    # assert
    assert opener.urls() == list(OVERPASS_URLS) * 2
    assert sleeps == [5.0, 10.0, 20.0]
    assert output_path.read_text(encoding="utf-8") == '{"elements": ["previous"]}'
    assert not part_path_for(output_path).exists()


def test_download_overpass_sends_descriptive_user_agent(tmp_path) -> None:
    # arrange
    opener = FakeOpener({OVERPASS_URLS[0]: [overpass_response({"elements": []})]})

    # act
    download_overpass(
        OVERPASS_QUERY, tmp_path / "routes.json", OVERPASS_URLS[:1], opener=opener
    )

    # assert
    assert opener.requests[0].get_header("User-agent") == (
        "lux-railway-map-overlay "
        "(+https://github.com/Spillgebees/lux-railway-map-overlay)"
    )


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b'{"remark": "runtime error: x"}', b'{"elements": {}}'],
)
def test_validate_overpass_payload_rejects_unusable_responses(body) -> None:
    with pytest.raises(OverpassError):
        validate_overpass_payload(body)


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
