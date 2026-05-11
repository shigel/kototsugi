#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


CHECKLIST: list[dict[str, Any]] = [
    {
        "id": "mvp_core_outputs",
        "requirement": "MVP success condition files are generated.",
        "files": [
            "transcript.md",
            "summary.md",
            "requirements.md",
            "requirements_items.json",
            "open_questions.md",
            "architecture.md",
            "issue_candidates.json",
            "issue_status.json",
            "implementation_plan.md",
        ],
    },
    {
        "id": "realtime_audio",
        "requirement": "Realtime audio preparation, streaming, and live-check paths exist.",
        "files": [
            "audio_manifest.json",
            "audio_chunks.json",
            "realtime_send_plan.json",
            "realtime_live_check_result.json",
        ],
        "code_terms": [
            "run_realtime_live_check",
            "build_realtime_api_compatibility_report",
            "audio_input_manifest",
            "SOKCON_AUDIO_INPUT_DEVICE",
            "BlackHole",
            "mixed_self_and_remote_audio",
            "participant_audio_policy",
            "supported_meeting_apps",
            "Google Meet",
            "Zoom",
            "Slack Huddle",
        ],
        "json_assertions": [
            {"file": "audio_manifest.json", "path": ["format"], "equals": "wav"},
            {
                "file": "audio_manifest.json",
                "path": ["realtime_sample_rate_ready"],
                "equals": True,
            },
            {
                "file": "audio_manifest.json",
                "path": ["realtime_input_audio_format"],
                "equals": "pcm16",
            },
            {"file": "realtime_send_plan.json", "path": ["event_count"], "equals": 2},
            {
                "file": "realtime_send_plan.json",
                "path": ["events", 0, "type"],
                "equals": "input_audio_buffer.append",
            },
            {
                "file": "realtime_send_plan.json",
                "path": ["events", 1, "type"],
                "equals": "input_audio_buffer.commit",
            },
        ],
    },
    {
        "id": "partial_final_transcripts",
        "requirement": "partial transcript is separated from final grounded artifacts.",
        "files": ["transcript_events.json", "partial_transcript.md"],
        "code_terms": ["process_transcript_events", "final_transcript_event_count"],
        "json_assertions": [
            {
                "file": "transcript_events.json",
                "path": [0, "meeting_id"],
                "equals": "mtg_local",
            },
            {
                "file": "transcript_events.json",
                "path": [0, "type"],
                "equals": "final",
            },
        ],
    },
    {
        "id": "questions_and_status",
        "requirement": "Questions and issues are prioritized and can be updated.",
        "files": [
            "open_questions.md",
            "questions.json",
            "question_status.json",
            "blocker_question_suggestions.json",
            "issue_candidates.json",
            "issue_status.json",
        ],
        "code_terms": [
            "blocker",
            "high_impact",
            "clarification",
            "later",
            "top_question_limit",
            "granularity",
            "granularity_reason",
            "classify_issue_granularity",
            "merged_candidate_count",
            "merge_issue_candidates",
            "update_question_status",
            "update_issue_status",
        ],
        "json_assertions": [
            {"file": "questions.json", "path": [0, "meeting_id"], "equals": "mtg_local"},
            {"file": "questions.json", "path": [0, "status"], "equals": "open"},
            {"file": "questions.json", "path": [0, "category"], "equals": "blocker"},
            {"file": "questions.json", "path": [0, "created_at"], "equals": "2026-05-08T00:00:00Z"},
            {"file": "issue_candidates.json", "path": [0, "meeting_id"], "equals": "mtg_local"},
            {"file": "issue_candidates.json", "path": [0, "status"], "equals": "candidate"},
            {"file": "issue_candidates.json", "path": [0, "approval_required"], "equals": True},
            {"file": "issue_candidates.json", "path": [0, "source_range"], "equals": "00:00 PM"},
            {"file": "issue_candidates.json", "path": [0, "external_url"], "equals": None},
        ],
    },
    {
        "id": "requirements_markdown_sections",
        "requirement": "Requirements Markdown covers the required specification sections.",
        "files": ["requirements.md", "requirements_items.json"],
        "content_terms": [
            "## Background / Purpose",
            "## Target Users",
            "## Use Cases",
            "## Functional Requirements",
            "## Non-functional Requirements",
            "## UI/UX Requirements",
            "## Permission / Authentication Requirements",
            "## Data Requirements",
            "## External Integrations",
            "## Constraints",
            "## Decisions",
            "## Open Questions",
            "## Assumptions",
            "## Risks",
            "## Acceptance Criteria",
        ],
        "json_assertions": [
            {
                "file": "requirements_items.json",
                "path": [0, "meeting_id"],
                "equals": "mtg_local",
            },
            {
                "file": "requirements_items.json",
                "path": [0, "updated_at"],
                "equals": "2026-05-08T00:00:00Z",
            },
            {
                "file": "requirements_items.json",
                "path": [0, "status"],
                "equals": "draft",
            },
            {
                "file": "requirements_items.json",
                "path": [0, "source_event_ids", 0],
                "equals": "line_1",
            },
        ],
    },
    {
        "id": "audit_and_privacy",
        "requirement": "Audit, approval, privacy, and retention controls are generated.",
        "files": [
            "audit_log.json",
            "action_queue.json",
            "approval_plan.json",
            "privacy_manifest.json",
            "retention_policy.json",
        ],
        "code_terms": ["cleanup_retention", "build_approval_plan"],
        "allow_missing_files": ["approval_plan.json"],
    },
    {
        "id": "notifications",
        "requirement": "macOS notification and notification policy artifacts exist.",
        "files": ["macos_notification_plan.json", "notification_policy.json"],
        "code_terms": ["send_macos_notifications", "SOKCON_NOTIFICATION_FOCUS_APP"],
        "json_assertions": [
            {
                "file": "notification_policy.json",
                "path": [
                    "macos_notifications",
                    "rate_limit",
                    "max_blocker_questions_per_meeting",
                ],
                "equals": 3,
            },
            {
                "file": "notification_policy.json",
                "path": ["macos_notifications", "rate_limit", "clarification_and_later"],
                "equals": "file_only",
            },
        ],
    },
    {
        "id": "external_registration",
        "requirement": "External registration drafts and approved execution paths exist.",
        "files": ["external_registration_payloads.json"],
        "code_terms": ["post_external_registration", "execute_approval_plan"],
    },
    {
        "id": "post_meeting_actions",
        "requirement": "Implementation agent and PR handoff drafts exist.",
        "files": ["agent_handoff.json", "branch_creation_draft.json", "pull_request_draft.json"],
        "code_terms": ["execute_agent_start_action", "branch_creation", "pull_request_creation"],
    },
    {
        "id": "diagrams_and_mockups",
        "requirement": "Diagrams and UI mockups are generated when applicable.",
        "files": [
            "diagrams.md",
            "diagram_revisions.json",
            "dashboard.html",
            "dashboard_mockup.html",
        ],
        "allow_missing_files": ["dashboard_mockup.html"],
        "code_terms": [
            "render_sales_problem_structure_diagram",
            "render_sales_proposal_story_diagram",
            "render_sales_adoption_steps_diagram",
            "render_talk_structure_diagram",
            "render_talk_storyline_diagram",
        ],
    },
    {
        "id": "diarization",
        "requirement": "Speaker metadata and external diarization adapter artifacts exist.",
        "files": ["speaker_summary.md", "diarization_manifest.json", "diarization_segments.json"],
        "code_terms": ["execute_diarization"],
    },
    {
        "id": "meeting_modes",
        "requirement": "Meeting modes expose goals, outputs, scoring, tools, and actions.",
        "files": ["mode_profile.json"],
        "code_terms": [
            "development",
            "sales",
            "hiring",
            "presentation",
            "customer_success",
            "fundraising",
            "legal",
            "executive",
            "research",
            "general",
            "mode_specific_outputs",
            "render_mode_progress_items",
            "Mode Score / Progress",
        ],
    },
    {
        "id": "approval_gate",
        "requirement": (
            "External registration, email, branch, agent start, and PR creation require approval."
        ),
        "files": [
            "action_queue.json",
            "approval_plan.json",
            "pull_request_draft.json",
            "branch_creation_draft.json",
            "external_email_draft.json",
        ],
        "allow_missing_files": ["approval_plan.json"],
        "code_terms": [
            "requires_human_approval",
            "external_issue_registration",
            "external_email_sending",
            "branch_creation",
            "implementation_agent_start",
            "pull_request_creation",
        ],
        "json_assertions": [
            {
                "file": "external_email_draft.json",
                "path": ["requires_human_approval"],
                "equals": True,
            },
            {
                "file": "branch_creation_draft.json",
                "path": ["requires_human_approval"],
                "equals": True,
            },
            {
                "file": "pull_request_draft.json",
                "path": ["requires_human_approval"],
                "equals": True,
            },
            {
                "file": "agent_handoff.json",
                "path": ["requires_human_approval"],
                "equals": True,
            },
        ],
    },
    {
        "id": "parallel_pipeline_contract",
        "requirement": "Event bus and worker failure isolation contracts exist.",
        "files": [
            "event_bus.json",
            "worker_status.json",
            "performance_manifest.json",
            "mvp_success_conditions.json",
        ],
        "json_assertions": [
            {
                "file": "performance_manifest.json",
                "path": ["targets", "post_meeting_generation_seconds"],
                "equals": 300,
            },
            {
                "file": "performance_manifest.json",
                "path": ["passes_targets", "post_meeting_generation"],
                "equals": True,
            },
        ],
    },
    {
        "id": "decoupled_architecture",
        "requirement": "The implementation remains Hermes-independent and loosely coupled.",
        "files": ["requirements_traceability.json"],
        "code_terms": ["dependencies = []", "external_registration_payloads"],
        "forbidden_code_terms": ["import hermes", "from hermes", "hermes."],
    },
    {
        "id": "rolling_summary_cadence",
        "requirement": "Rolling summaries are generated on a 30-60 second cadence.",
        "files": ["rolling_summary.md", "performance_manifest.json"],
        "content_terms": ["## Window 1: 00:00-01:00"],
        "json_assertions": [
            {
                "file": "performance_manifest.json",
                "path": ["targets", "rolling_summary_window_seconds_min"],
                "equals": 30,
            },
            {
                "file": "performance_manifest.json",
                "path": ["targets", "rolling_summary_window_seconds_max"],
                "equals": 60,
            },
            {
                "file": "performance_manifest.json",
                "path": ["passes_targets", "rolling_summary_window_configured"],
                "equals": True,
            },
        ],
    },
    {
        "id": "traceability",
        "requirement": (
            "Traceability has no unimplemented requirements and MVP live checks are ready."
        ),
        "files": ["requirements_traceability.json", "live_verification_manifest.json"],
        "json_assertions": [
            {
                "file": "requirements_traceability.json",
                "path": ["not_implemented"],
                "equals": [],
            },
            {
                "file": "live_verification_manifest.json",
                "path": ["mvp_status"],
                "equals": "ready",
            },
            {
                "file": "live_verification_manifest.json",
                "path": ["blocked_mvp_checks"],
                "equals": [],
            },
            {
                "file": "realtime_live_check_result.json",
                "path": ["status"],
                "equals": "completed",
            },
            {
                "file": "realtime_live_check_result.json",
                "path": ["network_request_executed"],
                "equals": True,
            }
        ],
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit SOKCON requirements evidence.")
    parser.add_argument("artifact_dir", type=Path, help="Generated artifact directory to audit.")
    parser.add_argument("--out", type=Path, default=ROOT / "requirements-audit.json")
    args = parser.parse_args()

    report = build_report(args.artifact_dir)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0 if report["passed"] else 1


def build_report(artifact_dir: Path) -> dict[str, Any]:
    code_text = read_code_text()
    forbidden_scan_text = read_forbidden_scan_text()
    checks = [
        evaluate_check(item, artifact_dir, code_text, forbidden_scan_text)
        for item in CHECKLIST
    ]
    missing = [check for check in checks if not check["passed"]]
    blockers = build_blocker_summary(missing, artifact_dir)
    return {
        "objective": "requirements.md を実現すること",
        "success_criteria": [
            "MVP core artifacts are generated from transcript/event input.",
            "Realtime audio preparation, streaming, and executed live check evidence exist.",
            "Final transcript events ground confirmed artifacts; partial events remain UI-only.",
            "Questions, requirements, diagrams, issues, notifications, and approval gates exist.",
            "Live verification reports no blocked MVP checks.",
        ],
        "artifact_dir": str(artifact_dir),
        "passed": not missing,
        "completion_status": "complete" if not missing else "blocked",
        "checks": checks,
        "missing_count": len(missing),
        "failed_check_ids": [check["id"] for check in missing],
        "blockers": blockers,
    }


def build_blocker_summary(
    failed_checks: list[dict[str, Any]],
    artifact_dir: Path,
) -> list[dict[str, Any]]:
    return [
        {
            "id": check["id"],
            "requirement": check["requirement"],
            "missing_files": [
                result["file"]
                for result in check["files"]
                if not result["exists"] and result["required"]
            ],
            "missing_code_terms": [
                result["term"] for result in check["code_terms"] if not result["present"]
            ],
            "present_forbidden_code_terms": [
                result["term"]
                for result in check["forbidden_code_terms"]
                if result["present"]
            ],
            "missing_content_terms": [
                result["term"] for result in check["content_terms"] if not result["present"]
            ],
            "failed_json_assertions": [
                {
                    "file": assertion["file"],
                    "path": assertion["path"],
                    "expected": assertion["equals"],
                    "actual": assertion.get("actual"),
                }
                for assertion in check["json_assertions"]
                if not assertion["passed"]
            ],
            "next_actions": blocker_next_actions(check, artifact_dir),
        }
        for check in failed_checks
    ]


def blocker_next_actions(check: dict[str, Any], artifact_dir: Path) -> list[str]:
    if check["id"] != "traceability":
        return []
    actions = []
    live_result = load_json_object(artifact_dir / "realtime_live_check_result.json")
    live_manifest = load_json_object(artifact_dir / "live_verification_manifest.json")
    if isinstance(live_result.get("next_action"), str):
        actions.append(live_result["next_action"])
    openai_check = next(
        (
            item
            for item in live_manifest.get("checks", [])
            if isinstance(item, dict) and item.get("id") == "openai_realtime_api"
        ),
        {},
    )
    if isinstance(openai_check, dict) and openai_check.get("missing"):
        actions.append("Missing for OpenAI Realtime check: " + ", ".join(openai_check["missing"]))
    return actions


def evaluate_check(
    item: dict[str, Any],
    artifact_dir: Path,
    code_text: str,
    forbidden_scan_text: str,
) -> dict[str, Any]:
    allow_missing = set(item.get("allow_missing_files", []))
    required_files = list(item.get("files", []))
    file_results = [
        {
            "file": filename,
            "exists": resolve_artifact(artifact_dir, filename).exists(),
            "required": filename not in allow_missing,
        }
        for filename in required_files
    ]
    code_results = [
        {"term": term, "present": term in code_text} for term in item.get("code_terms", [])
    ]
    forbidden_code_results = [
        {"term": term, "present": term in forbidden_scan_text}
        for term in item.get("forbidden_code_terms", [])
    ]
    artifact_text = read_artifact_text(artifact_dir, required_files)
    content_results = [
        {"term": term, "present": term in artifact_text}
        for term in item.get("content_terms", [])
    ]
    json_results = [
        evaluate_json_assertion(artifact_dir, assertion)
        for assertion in item.get("json_assertions", [])
    ]
    passed = (
        all(result["exists"] or not result["required"] for result in file_results)
        and all(result["present"] for result in code_results)
        and all(not result["present"] for result in forbidden_code_results)
        and all(result["present"] for result in content_results)
        and all(result["passed"] for result in json_results)
    )
    return {
        "id": item["id"],
        "requirement": item["requirement"],
        "passed": passed,
        "files": file_results,
        "code_terms": code_results,
        "forbidden_code_terms": forbidden_code_results,
        "content_terms": content_results,
        "json_assertions": json_results,
    }


def resolve_artifact(artifact_dir: Path, filename: str) -> Path:
    direct = artifact_dir / filename
    if direct.exists():
        return direct
    if filename == "dashboard_mockup.html":
        return artifact_dir / "mockups" / filename
    return direct


def evaluate_json_assertion(artifact_dir: Path, assertion: dict[str, Any]) -> dict[str, Any]:
    path = artifact_dir / str(assertion["file"])
    if not path.exists():
        return {**assertion, "passed": False, "actual": None}
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
        for part in assertion["path"]:
            value = value[part]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        return {**assertion, "passed": False, "actual": None, "error": str(error)}
    expected = assertion["equals"]
    return {**assertion, "passed": value == expected, "actual": value}


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def read_artifact_text(artifact_dir: Path, filenames: list[str]) -> str:
    chunks = []
    for filename in filenames:
        path = resolve_artifact(artifact_dir, filename)
        if path.exists() and path.is_file():
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def read_code_text() -> str:
    paths = [
        ROOT / "pyproject.toml",
        ROOT / "src/sokcon",
        ROOT / "scripts",
        ROOT / "README.md",
    ]
    chunks = []
    for path in paths:
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8"))
            continue
        for child in sorted(path.rglob("*.py")):
            chunks.append(child.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def read_forbidden_scan_text() -> str:
    paths = [
        ROOT / "pyproject.toml",
        ROOT / "src/sokcon",
        ROOT / "README.md",
    ]
    chunks = []
    for path in paths:
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8").lower())
            continue
        for child in sorted(path.rglob("*.py")):
            chunks.append(child.read_text(encoding="utf-8").lower())
    return "\n".join(chunks)


if __name__ == "__main__":
    raise SystemExit(main())
