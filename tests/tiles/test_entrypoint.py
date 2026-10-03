"""Tests for the PUBLIC_URL handling in tiles/entrypoint.sh.

The tests source the entrypoint in bash and call its functions, so they run
without Martin or nginx.
"""

from __future__ import annotations

import json
import shutil
import subprocess
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
