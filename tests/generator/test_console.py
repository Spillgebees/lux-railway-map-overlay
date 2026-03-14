from __future__ import annotations

from generator.console import Console, format_bytes, format_elapsed


def test_format_elapsed_shows_minutes_and_seconds() -> None:
    import time

    start = time.time() - 125  # 2m 5s ago
    result = format_elapsed(start)
    assert result == "2m 5s"


def test_format_elapsed_zero_seconds() -> None:
    import time

    result = format_elapsed(time.time())
    assert result == "0m 0s"


def test_format_bytes_units() -> None:
    assert format_bytes(0) == "0B"
    assert format_bytes(512) == "512B"
    assert format_bytes(1024) == "1.0KB"
    assert format_bytes(1024 * 1024) == "1.0MB"
    assert format_bytes(1024 * 1024 * 1024) == "1.0GB"
    assert format_bytes(1536) == "1.5KB"


def test_console_info_prints_tag(capsys) -> None:
    console = Console(use_color=False)
    console.info("hello")
    captured = capsys.readouterr()
    assert "[INFO]" in captured.out
    assert "hello" in captured.out


def test_console_warn_prints_tag(capsys) -> None:
    console = Console(use_color=False)
    console.warn("careful")
    captured = capsys.readouterr()
    assert "[WARN]" in captured.out
    assert "careful" in captured.out


def test_console_error_prints_to_stderr(capsys) -> None:
    console = Console(use_color=False)
    console.error("bad")
    captured = capsys.readouterr()
    assert "[ERROR]" in captured.err
    assert "bad" in captured.err


def test_console_step_prints_bold_header(capsys) -> None:
    console = Console(use_color=False)
    console.step("Downloading")
    captured = capsys.readouterr()
    assert "==> Downloading" in captured.out


def test_console_create_detects_tty() -> None:
    console = Console.create()
    # in a test environment, stdout is not a tty
    assert console.use_color is False
