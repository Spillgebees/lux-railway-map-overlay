from __future__ import annotations

from types import SimpleNamespace

from generator.config import Settings
from generator.pipeline_reporting import (
    log_pipeline_complete,
    log_pipeline_start,
    print_pipeline_summary,
    start_step,
)


class FakeConsole:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def step(self, message: str) -> None:
        self.messages.append(("step", message))

    def info(self, message: str) -> None:
        self.messages.append(("info", message))


def test_log_pipeline_start_reports_run_context(tmp_path) -> None:
    console = FakeConsole()
    settings = Settings(
        countries=("lu", "be"), output_dir=tmp_path, script_dir=tmp_path
    )

    log_pipeline_start(console, settings)

    assert console.messages == [
        ("step", "lux-railway-map-overlay data generation"),
        ("info", "Countries: lu be"),
        ("info", f"Output directory: {tmp_path}"),
    ]


def test_log_pipeline_complete_reports_elapsed_and_attribution(monkeypatch) -> None:
    console = FakeConsole()
    monkeypatch.setattr(
        "generator.pipeline_reporting.format_elapsed", lambda start: "1m 2s"
    )

    log_pipeline_complete(console, 123.0)

    assert console.messages == [
        ("info", "Total elapsed time: 1m 2s"),
        ("info", "Data attribution: (c) OpenStreetMap contributors (ODbL)"),
    ]


def test_start_step_logs_and_returns_current_time(monkeypatch) -> None:
    console = FakeConsole()
    monkeypatch.setattr("generator.pipeline_reporting.current_time", lambda: 42.5)

    assert start_step(console, "Extracting") == 42.5
    assert console.messages == [("step", "Extracting")]


def test_print_pipeline_summary_lists_outputs_and_layers(tmp_path, capsys) -> None:
    output_dir = tmp_path / "data"
    shapefile_dir = output_dir / "intermediate" / "shp"
    geojson_dir = output_dir / "intermediate" / "geojson"
    deliverables_dir = output_dir / "out"
    shapefile_dir.mkdir(parents=True)
    geojson_dir.mkdir(parents=True)
    deliverables_dir.mkdir(parents=True)

    (output_dir / "intermediate" / "railway-merged.osm.pbf").write_bytes(b"1234")
    (shapefile_dir / "railway_lines.shp").write_bytes(b"12")
    (geojson_dir / "railway_routes.geojson").write_bytes(b"123")
    (deliverables_dir / "railway-data.gpkg").write_bytes(b"12345")

    settings = Settings(countries=("lu",), output_dir=output_dir, script_dir=tmp_path)

    def fake_runner(*args, **kwargs):
        return SimpleNamespace(stdout="1: railway_lines\nfoo\n2: railway_points\n")

    print_pipeline_summary(
        settings,
        lambda size: f"{size}B",
        tool_lookup=lambda tool_name: (
            "/usr/bin/ogrinfo" if tool_name == "ogrinfo" else None
        ),
        command_runner=fake_runner,
    )

    captured = capsys.readouterr().out
    assert "Countries: Luxembourg" in captured
    assert "intermediate/railway-merged.osm.pbf" in captured
    assert "intermediate/shp/railway_lines.shp" in captured
    assert "intermediate/geojson/railway_routes.geojson" in captured
    assert "GeoPackage layers:" in captured
    assert "1: railway_lines" in captured
    assert "2: railway_points" in captured
