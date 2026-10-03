"""Tests for tiles/entrypoint.sh: PUBLIC_URL handling and process supervision.

The tests source the entrypoint in bash and call its functions, so they run
without Martin or nginx. The supervision tests use sh and sleep as stand-ins.
"""

import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = REPO_ROOT / "tiles" / "entrypoint.sh"
STYLE = REPO_ROOT / "styles" / "style.json"
STYLE_BASE_URL = "http://localhost:3000"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def run_function(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", 'source "$1"; shift; "$@"', "bash", str(ENTRYPOINT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://tiles.example.com", "https://tiles.example.com"),
        ("https://tiles.example.com/", "https://tiles.example.com"),
        ("https://tiles.example.com//", "https://tiles.example.com"),
        ("http://localhost:3000", "http://localhost:3000"),
        ("https://example.com/tiles/", "https://example.com/tiles"),
        ("https://tiles.example.com/a|b&c", "https://tiles.example.com/a|b&c"),
        ("https://example.com/a\\b", "https://example.com/a\\b"),
    ],
)
def test_normalize_public_url_accepts_http_urls(value: str, expected: str) -> None:
    result = run_function("normalize_public_url", value)

    assert result.returncode == 0, result.stderr
    assert result.stdout == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "/",
        "tiles.example.com",
        "ftp://tiles.example.com",
        "https://",
        "https:///path",
        "https://tiles.example.com/?v=1",
        "https://tiles.example.com/#top",
        "https://tiles.example.com/a b",
        "https://tiles.example.com/a\nb",
        "https://tiles.example.com/a\tb",
    ],
)
def test_normalize_public_url_rejects_invalid_values(value: str) -> None:
    result = run_function("normalize_public_url", value)

    assert result.returncode != 0
    assert "PUBLIC_URL" in result.stderr


@pytest.mark.parametrize(
    "public_url",
    [
        "https://tiles.example.com",
        "https://tiles.example.com/a|b&c",
        "https://tiles.example.com/a\\b",
        'https://tiles.example.com/a"b',
        "https://tiles.example.com/$HOME/`id`",
    ],
)
def test_rewrite_style_urls_inserts_url_verbatim(
    tmp_path: Path, public_url: str
) -> None:
    target = tmp_path / "style.json"

    result = run_function("rewrite_style_urls", str(STYLE), str(target), public_url)

    assert result.returncode == 0, result.stderr
    original = json.loads(STYLE.read_text())
    rewritten = json.loads(target.read_text())
    assert STYLE_BASE_URL not in target.read_text()
    assert rewritten["glyphs"] == original["glyphs"].replace(STYLE_BASE_URL, public_url)
    assert rewritten["sprite"] == original["sprite"].replace(STYLE_BASE_URL, public_url)
    for name, source in original["sources"].items():
        if "url" in source:
            assert rewritten["sources"][name]["url"] == source["url"].replace(
                STYLE_BASE_URL, public_url
            )
    assert rewritten["layers"] == original["layers"]


def test_sourcing_the_entrypoint_does_not_start_the_server() -> None:
    result = run_function("true")

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


SUPERVISE = """
source "$1"
trap 'shutdown INT' INT
trap 'shutdown TERM' TERM
trap 'signal_children TERM' EXIT
PIDS_FILE="$2"
sh -c "$3" &
MARTIN_PID=$!
sh -c "$4" &
NGINX_PID=$!
echo "${MARTIN_PID} ${NGINX_PID}" >"${PIDS_FILE}"
supervise
"""


def start_supervisor(
    tmp_path: Path, martin: str, nginx: str
) -> tuple[subprocess.Popen[str], Path]:
    pids = tmp_path / "pids"
    process = subprocess.Popen(
        ["bash", "-c", SUPERVISE, "bash", str(ENTRYPOINT), str(pids), martin, nginx],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return process, pids


def wait_for_pids(pids: Path) -> list[int]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if pids.exists() and pids.read_text().strip():
            return [int(pid) for pid in pids.read_text().split()]
        time.sleep(0.05)
    raise AssertionError("supervisor did not start its children")


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.parametrize(
    ("martin", "nginx", "expected_status", "expected_name"),
    [
        ("exit 3", "exec sleep 30", 3, "Martin"),
        ("exec sleep 30", "exit 0", 1, "nginx"),
        ("kill -KILL $$", "exec sleep 30", 137, "Martin"),
    ],
)
def test_supervise_exits_when_either_child_exits(
    tmp_path: Path, martin: str, nginx: str, expected_status: int, expected_name: str
) -> None:
    process, pids = start_supervisor(tmp_path, martin, nginx)

    output, _ = process.communicate(timeout=10)

    assert process.returncode == expected_status, output
    assert f"{expected_name} exited unexpectedly" in output
    assert not any(is_running(pid) for pid in wait_for_pids(pids))


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
def test_shutdown_forwards_signal_to_both_children(
    tmp_path: Path, sig: signal.Signals
) -> None:
    process, pids = start_supervisor(tmp_path, "exec sleep 30", "exec sleep 30")
    children = wait_for_pids(pids)

    process.send_signal(sig)
    output, _ = process.communicate(timeout=10)

    assert process.returncode == 0, output
    assert f"Received {sig.name}" in output
    assert not any(is_running(pid) for pid in children)
