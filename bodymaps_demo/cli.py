from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import uvicorn

from .bundle_inference import run_bundle_inference
from .config import Settings
from .doctor import diagnose, format_report
from .suprem_inference import run_suprem_inference


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bodymaps")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Start local web application.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    doctor = subparsers.add_parser("doctor", help="Check demo prerequisites.")
    doctor.add_argument("--json", action="store_true")

    infer = subparsers.add_parser(
        "infer-bundle", help="Import provided BodyMaps CT and segmentation masks."
    )
    infer.add_argument("--input", type=Path, required=True)
    infer.add_argument("--output-dir", type=Path, required=True)

    suprem = subparsers.add_parser(
        "infer-suprem", help="Run linked SuPreM prototype through its official Docker image."
    )
    suprem.add_argument("--input", type=Path, required=True)
    suprem.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    settings = Settings.from_env()

    if args.command == "serve":
        uvicorn.run(
            "bodymaps_demo.app:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return

    if args.command == "doctor":
        report = diagnose(settings)
        print(json.dumps(report, indent=2) if args.json else format_report(report))
        if not report["passed"]:
            raise SystemExit(1)
        return

    if args.command == "infer-bundle":
        try:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            result = run_bundle_inference(args.input.resolve(), args.output_dir.resolve())
            print(json.dumps({"status": "completed", "summary": result["summary"]}))
        except Exception as error:
            print(f"Bundle inference failed: {error}", file=sys.stderr)
            raise SystemExit(1) from error

    if args.command == "infer-suprem":
        try:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            result = run_suprem_inference(args.input.resolve(), args.output_dir.resolve())
            print(json.dumps({"status": "completed", "summary": result["summary"]}))
        except Exception as error:
            print(f"SuPreM inference failed: {error}", file=sys.stderr)
            raise SystemExit(1) from error


if __name__ == "__main__":
    main()
