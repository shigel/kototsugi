from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kototsugi.pipeline import process_transcript


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kototsugi",
        description=(
            "Turn meeting transcripts into MDD artifacts: specs, questions, "
            "diagrams, issues, and plans."
        ),
    )
    parser.add_argument("input", type=Path, help="Transcript text file. Use '-' to read stdin.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("kototsugi-output"),
        help="Output directory",
    )
    parser.add_argument("--mode", default="development", help="Meeting mode")
    parser.add_argument("--project", default="KOTOTSUGI Project", help="Project name")
    parser.add_argument(
        "--min-quality-score",
        type=float,
        default=0.5,
        help="Fail if quantitative quality_score is below this threshold.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    transcript = (
        sys.stdin.read()
        if str(args.input) == "-"
        else args.input.read_text(encoding="utf-8")
    )
    result = process_transcript(
        transcript=transcript,
        output_dir=args.out,
        meeting_mode=args.mode,
        project_name=args.project,
    )
    quality_score = result.metrics["quality_score"]
    print(f"KOTOTSUGI generated {len(result.artifacts)} artifacts in {args.out}")
    print(f"quality_score={quality_score:g}")
    if quality_score < args.min_quality_score:
        print(
            f"quality_score below threshold: {quality_score:g} < {args.min_quality_score:g}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
