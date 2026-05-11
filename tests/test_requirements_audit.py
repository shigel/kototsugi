import json
from pathlib import Path

from scripts.requirements_audit import build_report


def write(path: Path, content: str = "ok") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_notification_policy(path: Path) -> None:
    write(
        path,
        json.dumps(
            {
                "macos_notifications": {
                    "rate_limit": {
                        "max_blocker_questions_per_meeting": 3,
                        "clarification_and_later": "file_only",
                    }
                }
            }
        ),
    )


def write_approval_gate_files(root: Path) -> None:
    for filename in (
        "external_email_draft.json",
        "branch_creation_draft.json",
        "pull_request_draft.json",
        "agent_handoff.json",
    ):
        write(root / filename, json.dumps({"requires_human_approval": True}))


def write_data_model_files(root: Path) -> None:
    write(
        root / "questions.json",
        json.dumps(
            [
                {
                    "meeting_id": "mtg_local",
                    "status": "open",
                    "category": "blocker",
                    "created_at": "2026-05-08T00:00:00Z",
                }
            ]
        ),
    )
    write(
        root / "issue_candidates.json",
        json.dumps(
            [
                {
                    "meeting_id": "mtg_local",
                    "status": "candidate",
                    "approval_required": True,
                    "source_range": "00:00 PM",
                    "external_url": None,
                }
            ]
        ),
    )


def write_realtime_audio_files(root: Path) -> None:
    write(
        root / "audio_manifest.json",
        json.dumps(
            {
                "format": "wav",
                "realtime_sample_rate_ready": True,
                "realtime_input_audio_format": "pcm16",
            }
        ),
    )
    write(
        root / "realtime_send_plan.json",
        json.dumps(
            {
                "event_count": 2,
                "events": [
                    {"type": "input_audio_buffer.append"},
                    {"type": "input_audio_buffer.commit"},
                ],
            }
        ),
    )


def test_requirements_audit_detects_complete_artifact_set(tmp_path: Path) -> None:
    required_files = [
        "transcript.md",
        "summary.md",
        "requirements.md",
        "requirements_items.json",
        "open_questions.md",
        "architecture.md",
        "issue_candidates.json",
        "issue_status.json",
        "implementation_plan.md",
        "mode_profile.json",
        "audio_manifest.json",
        "audio_chunks.json",
        "realtime_send_plan.json",
        "realtime_live_check_result.json",
        "transcript_events.json",
        "partial_transcript.md",
        "questions.json",
        "question_status.json",
        "blocker_question_suggestions.json",
        "audit_log.json",
        "action_queue.json",
        "privacy_manifest.json",
        "retention_policy.json",
        "macos_notification_plan.json",
        "notification_policy.json",
        "external_registration_payloads.json",
        "agent_handoff.json",
        "branch_creation_draft.json",
        "pull_request_draft.json",
        "external_email_draft.json",
        "diagrams.md",
        "diagram_revisions.json",
        "dashboard.html",
        "mockups/dashboard_mockup.html",
        "speaker_summary.md",
        "diarization_manifest.json",
        "diarization_segments.json",
        "event_bus.json",
        "worker_status.json",
        "performance_manifest.json",
        "mvp_success_conditions.json",
        "live_verification_manifest.json",
        "rolling_summary.md",
    ]
    for filename in required_files:
        write(tmp_path / filename)
    write(
        tmp_path / "live_verification_manifest.json",
        json.dumps({"mvp_status": "ready", "blocked_mvp_checks": []}),
    )
    write(
        tmp_path / "realtime_live_check_result.json",
        json.dumps({"status": "completed", "network_request_executed": True}),
    )
    write(
        tmp_path / "transcript_events.json",
        json.dumps([{"meeting_id": "mtg_local", "type": "final"}]),
    )
    write(
        tmp_path / "requirements.md",
        "\n".join(
            [
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
            ]
        ),
    )
    write(
        tmp_path / "requirements_traceability.json",
        json.dumps({"implemented": [], "not_implemented": []}),
    )
    write(
        tmp_path / "requirements_items.json",
        json.dumps(
            [
                {
                    "meeting_id": "mtg_local",
                    "updated_at": "2026-05-08T00:00:00Z",
                    "status": "draft",
                    "source_event_ids": ["line_1"],
                }
            ]
        ),
    )
    write_notification_policy(tmp_path / "notification_policy.json")
    write_approval_gate_files(tmp_path)
    write_data_model_files(tmp_path)
    write_realtime_audio_files(tmp_path)
    write(tmp_path / "rolling_summary.md", "## Window 1: 00:00-01:00")
    write(
        tmp_path / "performance_manifest.json",
        json.dumps(
                {
                    "targets": {
                        "post_meeting_generation_seconds": 300,
                        "rolling_summary_window_seconds_min": 30,
                        "rolling_summary_window_seconds_max": 60,
                    },
                    "passes_targets": {
                        "post_meeting_generation": True,
                        "rolling_summary_window_configured": True,
                    },
                }
            ),
        )

    report = build_report(tmp_path)

    assert report["passed"] is True
    assert report["completion_status"] == "complete"
    assert report["missing_count"] == 0
    assert report["failed_check_ids"] == []
    assert report["blockers"] == []


def test_requirements_audit_reports_missing_required_artifact(tmp_path: Path) -> None:
    write(
        tmp_path / "requirements_traceability.json",
        json.dumps({"implemented": [], "not_implemented": [{"requirement": "x"}]}),
    )

    report = build_report(tmp_path)

    assert report["passed"] is False
    assert report["completion_status"] == "blocked"
    assert report["missing_count"] > 0
    assert report["failed_check_ids"]
    assert report["blockers"]


def test_requirements_audit_reports_blocked_live_mvp_check(tmp_path: Path) -> None:
    required_files = [
        "transcript.md",
        "summary.md",
        "requirements.md",
        "requirements_items.json",
        "open_questions.md",
        "architecture.md",
        "issue_candidates.json",
        "issue_status.json",
        "implementation_plan.md",
        "mode_profile.json",
        "audio_manifest.json",
        "audio_chunks.json",
        "realtime_send_plan.json",
        "realtime_live_check_result.json",
        "transcript_events.json",
        "partial_transcript.md",
        "questions.json",
        "question_status.json",
        "blocker_question_suggestions.json",
        "audit_log.json",
        "action_queue.json",
        "privacy_manifest.json",
        "retention_policy.json",
        "macos_notification_plan.json",
        "notification_policy.json",
        "external_registration_payloads.json",
        "agent_handoff.json",
        "branch_creation_draft.json",
        "pull_request_draft.json",
        "external_email_draft.json",
        "diagrams.md",
        "diagram_revisions.json",
        "dashboard.html",
        "mockups/dashboard_mockup.html",
        "speaker_summary.md",
        "diarization_manifest.json",
        "diarization_segments.json",
        "event_bus.json",
        "worker_status.json",
        "performance_manifest.json",
        "mvp_success_conditions.json",
        "rolling_summary.md",
    ]
    for filename in required_files:
        write(tmp_path / filename)
    write(
        tmp_path / "requirements.md",
        "\n".join(
            [
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
            ]
        ),
    )
    write(
        tmp_path / "requirements_traceability.json",
        json.dumps({"implemented": [], "not_implemented": []}),
    )
    write(
        tmp_path / "requirements_items.json",
        json.dumps(
            [
                {
                    "meeting_id": "mtg_local",
                    "updated_at": "2026-05-08T00:00:00Z",
                    "status": "draft",
                    "source_event_ids": ["line_1"],
                }
            ]
        ),
    )
    write(
        tmp_path / "live_verification_manifest.json",
        json.dumps(
            {
                "mvp_status": "blocked",
                "blocked_mvp_checks": ["openai_realtime_api"],
                "checks": [
                    {
                        "id": "openai_realtime_api",
                        "missing": ["OPENAI_API_KEY"],
                    }
                ],
            }
        ),
    )
    write(
        tmp_path / "realtime_live_check_result.json",
        json.dumps(
            {
                "status": "dry_run",
                "network_request_executed": False,
                "next_action": "Provide OPENAI_API_KEY.",
            }
        ),
    )
    write(
        tmp_path / "transcript_events.json",
        json.dumps([{"meeting_id": "mtg_local", "type": "final"}]),
    )
    write_notification_policy(tmp_path / "notification_policy.json")
    write_approval_gate_files(tmp_path)
    write_data_model_files(tmp_path)
    write_realtime_audio_files(tmp_path)
    write(tmp_path / "rolling_summary.md", "## Window 1: 00:00-01:00")
    write(
        tmp_path / "performance_manifest.json",
        json.dumps(
                {
                    "targets": {
                        "post_meeting_generation_seconds": 300,
                        "rolling_summary_window_seconds_min": 30,
                        "rolling_summary_window_seconds_max": 60,
                    },
                    "passes_targets": {
                        "post_meeting_generation": True,
                        "rolling_summary_window_configured": True,
                    },
                }
            ),
        )

    report = build_report(tmp_path)

    traceability = next(check for check in report["checks"] if check["id"] == "traceability")
    assert report["passed"] is False
    assert report["completion_status"] == "blocked"
    assert report["failed_check_ids"] == ["traceability"]
    assert traceability["passed"] is False
    assert report["blockers"][0]["failed_json_assertions"]
    assert "Provide OPENAI_API_KEY." in report["blockers"][0]["next_actions"]
    assert any("OPENAI_API_KEY" in item for item in report["blockers"][0]["next_actions"])
