from __future__ import annotations

from pathlib import Path

import pytest

from generator import __main__
from generator.pipeline import PipelineError


def test_parse_countries_trims_and_preserves_order() -> None:
    assert __main__.parse_countries(" lu, be ,de ") == ("lu", "be", "de")


def test_parse_countries_rejects_unknown_codes() -> None:
    with pytest.raises(PipelineError, match=r"Unsupported country code\(s\): xx"):
        __main__.parse_countries("lu,xx")


def test_main_returns_zero_and_passes_settings(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class FakePipeline:
        def __init__(self, settings, console) -> None:
            captured["settings"] = settings
            captured["console"] = console

        def run(self) -> None:
            captured["ran"] = True

    fake_console = object()

    monkeypatch.setattr(
        __main__.Console, "create", classmethod(lambda cls: fake_console)
    )
    monkeypatch.setattr(__main__, "GeneratorPipeline", FakePipeline)

    exit_code = __main__.main(["--countries", "lu,be", "--output-dir", str(tmp_path)])

    assert exit_code == 0
    assert captured["ran"] is True
    settings = captured["settings"]
    assert settings.countries == ("lu", "be")
    assert settings.output_dir == tmp_path
    assert settings.script_dir == Path(__main__.__file__).resolve().parents[1]
    assert settings.allow_missing_routes is False
    assert captured["console"] is fake_console


def test_main_passes_allow_missing_routes_flag(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class FakePipeline:
        def __init__(self, settings, console) -> None:
            captured["settings"] = settings

        def run(self) -> None:
            return None

    monkeypatch.setattr(__main__.Console, "create", classmethod(lambda cls: object()))
    monkeypatch.setattr(__main__, "GeneratorPipeline", FakePipeline)

    exit_code = __main__.main(
        [
            "--countries",
            "lu",
            "--output-dir",
            str(tmp_path),
            "--allow-missing-routes",
        ]
    )

    assert exit_code == 0
    assert captured["settings"].allow_missing_routes is True


def test_main_reports_pipeline_errors(monkeypatch) -> None:
    messages: list[str] = []

    class FakeConsole:
        def error(self, message: str) -> None:
            messages.append(message)

    class FakePipeline:
        def __init__(self, settings, console) -> None:
            self.console = console

        def run(self) -> None:
            raise PipelineError("boom")

    monkeypatch.setattr(
        __main__.Console, "create", classmethod(lambda cls: FakeConsole())
    )
    monkeypatch.setattr(__main__, "GeneratorPipeline", FakePipeline)

    exit_code = __main__.main(["--countries", "lu"])

    assert exit_code == 1
    assert messages == ["boom"]


def test_parser_defaults_to_all_supported_countries(monkeypatch) -> None:
    # arrange
    monkeypatch.delenv("OUTPUT_DIR", raising=False)
    parser = __main__.build_parser()

    # act
    args = parser.parse_args([])

    # assert
    assert __main__.parse_countries(args.countries) == ("lu", "be", "de", "fr")


def test_parser_defaults_output_dir_to_relative_data_without_env(monkeypatch) -> None:
    # arrange
    monkeypatch.delenv("OUTPUT_DIR", raising=False)
    parser = __main__.build_parser()

    # act
    args = parser.parse_args(["--countries", "lu"])

    # assert
    assert args.output_dir == "./data"


def test_parser_defaults_output_dir_to_env_var(monkeypatch) -> None:
    # arrange
    monkeypatch.setenv("OUTPUT_DIR", "/data")
    parser = __main__.build_parser()

    # act
    args = parser.parse_args(["--countries", "lu"])

    # assert
    assert args.output_dir == "/data"


def test_parser_ignores_empty_output_dir_env_var(monkeypatch) -> None:
    # arrange
    monkeypatch.setenv("OUTPUT_DIR", "")
    parser = __main__.build_parser()

    # act
    args = parser.parse_args([])

    # assert
    assert args.output_dir == "./data"


def test_parser_output_dir_flag_overrides_env_var(monkeypatch, tmp_path) -> None:
    # arrange
    monkeypatch.setenv("OUTPUT_DIR", "/data")
    parser = __main__.build_parser()

    # act
    args = parser.parse_args(["--output-dir", str(tmp_path)])

    # assert
    assert args.output_dir == str(tmp_path)


def test_parse_countries_rejects_empty_value() -> None:
    # arrange
    raw_value = " , "

    # act / assert
    with pytest.raises(PipelineError, match="at least one country code"):
        __main__.parse_countries(raw_value)


def test_main_keeps_env_output_dir_when_only_countries_are_passed(
    monkeypatch, tmp_path
) -> None:
    # arrange
    captured: dict[str, object] = {}

    class FakePipeline:
        def __init__(self, settings, console) -> None:
            captured["settings"] = settings

        def run(self) -> None:
            return None

    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(__main__.Console, "create", classmethod(lambda cls: object()))
    monkeypatch.setattr(__main__, "GeneratorPipeline", FakePipeline)

    # act
    exit_code = __main__.main(["--countries", "lu"])

    # assert
    assert exit_code == 0
    assert captured["settings"].countries == ("lu",)
    assert captured["settings"].output_dir == tmp_path
