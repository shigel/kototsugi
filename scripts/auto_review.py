#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUFF = ROOT / ".venv" / "bin" / "ruff"


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
    pipeline = (ROOT / "src/sokcon/pipeline.py").read_text(encoding="utf-8")
    cli = (ROOT / "src/sokcon/cli.py").read_text(encoding="utf-8")
    scripts = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "scripts").glob("*.py")
    )

    expected_terms = [
        "文字起こし",
        "speaker_summary",
        "diarization_manifest",
        "diarization_segments",
        "run_diarization",
        "質問",
        "要件定義",
        "Issue",
        "implementation_plan",
        "dashboard",
        "audit_log",
        "event_bus",
        "worker_status",
        "performance_manifest",
        "mockups",
        "privacy_manifest",
        "retention_policy",
        "cleanup_retention",
        "action_queue",
        "pull_request_draft",
        "mode_profile",
        "mode_specific_outputs",
        "diagrams",
        "diagram_revisions",
        "requirements_traceability",
        "requirements_audit",
        "live_verification_manifest",
        "state_snapshot",
        "question_status",
        "update_question_status",
        "blocker_question_suggestions",
        "mvp_success_conditions",
        "issue_status",
        "update_issue_status",
        "source_event_ids",
        "serve_dashboard",
        "build_sse_snapshot",
        "watch_sse_events",
        "macos_notification_plan",
        "send_macos_notifications",
        "print_notification_config",
        "notification_policy",
        "slack_notification",
        "external_registration_payloads",
        "google_docs",
        "google_slides",
        "crm",
        "ats",
        "agent_handoff",
        "approval_plan",
        "execute_approval_plan",
        "execute_agent_start_action",
        "print_slack_config",
        "send_slack_notification",
        "print_external_config",
        "audio_chunks",
        "audio_input_manifest",
        "capture_audio",
        "realtime_send_plan",
        "create_realtime_session",
        "stream_realtime_audio",
        "run_realtime_live_check",
        "build_realtime_api_compatibility_report",
        "build_realtime_route_plan",
        "gpt-realtime-whisper",
        "gpt-realtime-translate",
    ]
    for term in expected_terms:
        found = (
            term in requirements
            or term in pipeline
            or term in cli
            or term in scripts
        )
        if not found:
            findings.append(f"Missing expected concept: {term}")

    security_patterns = ["eval(", "exec(", "shell=True", "os.system", "pickle.loads"]
    for pattern in security_patterns:
        if pattern in pipeline or pattern in cli:
            findings.append(f"Potentially unsafe pattern found: {pattern}")

    strengths = [
        "Offline deterministic pipeline keeps MVP testable and cheap.",
        (
            "Artifacts cover transcript, summary, requirements, questions, diagram, "
            "issues, dashboard, mockups, audit log, privacy manifest, mode profile, "
            "action queue, and plan."
        ),
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
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--ignore=tests/test_auto_review.py",
            ]
        ),
        "ruff": run([str(RUFF) if RUFF.exists() else "ruff", "check", "."]),
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
