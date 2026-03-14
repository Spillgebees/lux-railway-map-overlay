from __future__ import annotations

import argparse
import sys
from pathlib import Path

from generator.config import GEOFABRIK_URLS, SUPPORTED_COUNTRIES_TEXT, Settings
from generator.console import Console
from generator.pipeline import GeneratorPipeline, PipelineError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate",
        description="Generate railway infrastructure data relevant to Luxembourg, including cross-border context.",
    )
    parser.add_argument(
        "--countries",
        required=True,
        help=f"Comma-separated country codes. Supported: {SUPPORTED_COUNTRIES_TEXT}",
    )
    parser.add_argument(
        "--output-dir",
        default="./data",
        help="Output directory (default: ./data)",
    )
    parser.add_argument(
        "--allow-missing-routes",
        action="store_true",
        help=(
            "Allow generation to continue with empty route layers when Overpass is "
            "unavailable. Intended for local/manual runs, not publishing."
        ),
    )
    return parser


def parse_countries(raw_value: str) -> tuple[str, ...]:
    countries = tuple(code.strip() for code in raw_value.split(",") if code.strip())
    if not countries:
        raise PipelineError("--countries is required")

    invalid = [code for code in countries if code not in GEOFABRIK_URLS]
    if invalid:
        raise PipelineError(
            f"Unsupported country code(s): {', '.join(invalid)}. Supported codes: {SUPPORTED_COUNTRIES_TEXT}"
        )

    return countries


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    script_dir = Path(__file__).resolve().parents[1]
    settings = Settings(
        countries=parse_countries(args.countries),
        output_dir=Path(args.output_dir),
        script_dir=script_dir,
        allow_missing_routes=args.allow_missing_routes,
    )

    console = Console.create()

    try:
        GeneratorPipeline(settings, console).run()
    except PipelineError as error:
        console.error(str(error))
        return 1
    except KeyboardInterrupt:
        console.error("Interrupted")
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
