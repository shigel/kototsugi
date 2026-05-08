#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def qualitative_review() -> dict[str, Any]:
    findings: list[str] = []
    requirements = (ROOT / "requirements.md").read_text(encoding="utf-8")
    pipeline = (ROOT / "src/kototsugi/pipeline.py").read_text(encoding="utf-8")
    cli = (ROOT / "src/kototsugi/cli.py").read_text(encoding="utf-8")

    expected_terms = [
        "文字起こし",
        "質問",
        "要件定義",
        "Issue",
        "implementation_plan",
    ]
    for term in expected_terms:
        if term not in requirements and term not in pipeline and term not in cli:
            findings.append(f"Missing expected concept: {term}")

    security_patterns = ["eval(", "exec(", "shell=True", "os.system", "pickle.loads"]
    for pattern in security_patterns:
        if pattern in pipeline or pattern in cli:
            findings.append(f"Potentially unsafe pattern found: {pattern}")

    strengths = [
        "Offline deterministic pipeline keeps MVP testable and cheap.",
        "Artifacts cover transcript, summary, requirements, questions, diagram, issues, and plan.",
        "Quality gate combines quantitative metrics with qualitative review prompts.",
    ]
    return {
        "passed": not findings,
        "findings": findings,
        "strengths": strengths,
    }


def main() -> int:
    checks = {
        "pytest": run(
            [
                "uv",
                "run",
                "--active",
                "pytest",
                "-q",
                "--ignore=tests/test_auto_review.py",
            ]
        ),
        "ruff": run(["uv", "run", "--active", "ruff", "check", "."]),
        "qualitative": qualitative_review(),
    }
    quantitative = {
        "tests_passed": checks["pytest"]["returncode"] == 0,
        "lint_passed": checks["ruff"]["returncode"] == 0,
        "qualitative_passed": checks["qualitative"]["passed"],
    }
    quantitative["overall_score"] = sum(1 for value in quantitative.values() if value) / len(
        quantitative
    )
    report = {
        "quantitative": quantitative,
        "qualitative": checks["qualitative"],
        "raw_checks": checks,
    }
    output = ROOT / "review-report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    return 0 if all(quantitative.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
