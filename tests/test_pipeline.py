import json
from pathlib import Path

from sokcon.pipeline import TranscriptEvent, process_transcript, process_transcript_events

SAMPLE_TRANSCRIPT = """
[00:00] PM: 今日はログイン後のダッシュボードMVPを決めたいです。
[00:30] Eng: 管理者と一般ユーザーで表示内容を変える必要がありますか？
[01:00] PM: MVPでは一般ユーザーだけでよいです。CSVエクスポートは後回しです。
[01:40] Eng: データ更新頻度は日次で十分ですか？
[02:00] PM: はい、日次更新でお願いします。GitHub Issueにもしておいてください。
""".strip()


def test_process_transcript_generates_core_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    result = process_transcript(
        transcript=SAMPLE_TRANSCRIPT,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="Dashboard MVP",
    )

    assert result.metrics["transcript_lines"] == 5
    assert result.metrics["speaker_count"] == 2
    assert result.metrics["question_count"] >= 2
    assert result.metrics["requirement_count"] >= 2
    assert result.metrics["issue_candidate_count"] >= 1
    assert result.metrics["final_transcript_event_count"] == 5
    assert result.metrics["partial_transcript_event_count"] == 0
    assert result.metrics["quality_score"] >= 0.5

    expected_files = {
        "transcript.md",
        "transcript_events.json",
        "partial_transcript.md",
        "speaker_summary.md",
        "diarization_manifest.json",
        "diarization_segments.json",
        "summary.md",
        "rolling_summary.md",
        "decisions.md",
        "requirements.md",
        "requirements_items.json",
        "open_questions.md",
        "questions.json",
        "question_status.json",
        "blocker_question_suggestions.json",
        "architecture.md",
        "diagrams.md",
        "diagram_revisions.json",
        "issue_candidates.json",
        "issue_status.json",
        "implementation_plan.md",
        "mode_profile.json",
        "evaluation.json",
        "audit_log.json",
        "event_bus.json",
        "worker_status.json",
        "privacy_manifest.json",
        "retention_policy.json",
        "performance_manifest.json",
        "mvp_success_conditions.json",
        "action_queue.json",
        "branch_creation_draft.json",
        "pull_request_draft.json",
        "external_email_draft.json",
        "macos_notification_plan.json",
        "notification_policy.json",
        "slack_notification.json",
        "external_registration_payloads.json",
        "agent_handoff.json",
        "requirements_traceability.json",
        "state_snapshot.json",
        "dashboard.html",
        "dashboard_mockup.html",
    }
    assert expected_files.issubset({path.name for path in result.artifacts})

    requirements = (output_dir / "requirements.md").read_text(encoding="utf-8")
    requirements_items = json.loads(
        (output_dir / "requirements_items.json").read_text(encoding="utf-8")
    )
    assert "Dashboard MVP" in requirements
    assert "ダッシュボード" in requirements
    assert "日次" in requirements
    assert requirements_items
    assert all(item["meeting_id"] == "mtg_local" for item in requirements_items)
    assert all(item["updated_at"] for item in requirements_items)
    assert all(item["source_event_ids"] for item in requirements_items)
    requirement_items = [
        line for line in requirements.splitlines() if line.startswith("- [")
    ]
    allowed_requirement_categories = {
        "functional",
        "non_functional",
        "ui",
        "data",
        "integration",
        "security",
    }
    assert requirement_items
    assert all(
        line.split("(", 1)[1].split(")", 1)[0] in allowed_requirement_categories
        for line in requirement_items
    )
    for heading in (
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
    ):
        assert heading in requirements

    speaker_summary = (output_dir / "speaker_summary.md").read_text(encoding="utf-8")
    assert "PM: 3 utterances" in speaker_summary
    assert "Eng: 2 utterances" in speaker_summary
    assert "external_provider_ready" in speaker_summary

    diarization_manifest = json.loads(
        (output_dir / "diarization_manifest.json").read_text(encoding="utf-8")
    )
    assert diarization_manifest["quality_target"] == "high"
    assert diarization_manifest["segment_count"] == 5
    diarization_segments = json.loads(
        (output_dir / "diarization_segments.json").read_text(encoding="utf-8")
    )
    assert diarization_segments[0]["method"] == "transcript_metadata"

    rolling_summary = (output_dir / "rolling_summary.md").read_text(encoding="utf-8")
    assert "Window 1" in rolling_summary
    assert "Window 2" in rolling_summary
    assert result.metrics["rolling_summary_window_count"] >= 2

    diagrams = (output_dir / "diagrams.md").read_text(encoding="utf-8")
    assert "## Architecture" in diagrams
    assert "## Data Flow" in diagrams
    assert "## Screen Flow" in diagrams
    diagram_revisions = json.loads(
        (output_dir / "diagram_revisions.json").read_text(encoding="utf-8")
    )
    assert diagram_revisions["diff_update_supported"] is True
    assert diagram_revisions["revision_count"] >= 3
    assert all(revision["updatable"] for revision in diagram_revisions["revisions"])

    decisions = (output_dir / "decisions.md").read_text(encoding="utf-8")
    assert "一般ユーザーだけでよい" in decisions

    dashboard = (output_dir / "dashboard.html").read_text(encoding="utf-8")
    assert "Dashboard MVP" in dashboard
    assert "Top Questions" in dashboard
    assert "Issue Candidates" in dashboard
    assert "Current Transcript" in dashboard
    assert "Rolling Summary" in dashboard
    assert "Live Diagram" in dashboard
    assert "Mode Score / Progress" in dashboard
    assert "Quality score" in dashboard
    assert "EventSource('/stream')" in dashboard

    mockup = (output_dir / "mockups" / "dashboard_mockup.html").read_text(encoding="utf-8")
    assert "Dashboard MVP" in mockup
    assert "Grounded requirements" in mockup

    audit_log = json.loads((output_dir / "audit_log.json").read_text(encoding="utf-8"))
    assert audit_log["external_registration_enabled"] is False
    assert audit_log["external_destinations"] == []
    assert "github_issue_registration" in audit_log["approval_required_actions"]
    assert any(event["kind"] == "issue.candidate.created" for event in audit_log["events"])
    assert all(event["human_approved"] is False for event in audit_log["events"])
    assert all(event["external_sent"] is False for event in audit_log["events"])

    event_bus = json.loads((output_dir / "event_bus.json").read_text(encoding="utf-8"))
    assert event_bus["fanout_supported"] is True
    assert "question_worker" in event_bus["subscriber_groups"]
    assert "meeting.ended" in event_bus["topics"]

    worker_status = json.loads((output_dir / "worker_status.json").read_text(encoding="utf-8"))
    assert worker_status["failure_isolation"] is True
    assert worker_status["retry_policy"]["max_attempts"] == 3
    assert any(worker["name"] == "issue_worker" for worker in worker_status["workers"])

    privacy = json.loads((output_dir / "privacy_manifest.json").read_text(encoding="utf-8"))
    assert privacy["storage_scope"] == "local"
    assert privacy["recording_and_transcription_consent_required"] is True
    assert privacy["api_keys_stored_in_code"] is False
    retention_policy = json.loads(
        (output_dir / "retention_policy.json").read_text(encoding="utf-8")
    )
    assert retention_policy["delete_after_days"] == 30
    assert retention_policy["cleanup_command"] == "--cleanup-retention"

    performance = json.loads((output_dir / "performance_manifest.json").read_text(encoding="utf-8"))
    assert performance["targets"]["ui_update_seconds"] == 3
    assert performance["targets"]["post_meeting_generation_seconds"] == 300
    assert performance["passes_targets"]["post_meeting_generation"] is True
    assert performance["background_worker_contract"]["failure_isolation"] is True

    mvp_success = json.loads(
        (output_dir / "mvp_success_conditions.json").read_text(encoding="utf-8")
    )
    assert mvp_success["blocker_questions"]["passes"] is True
    assert mvp_success["issue_adoption_proxy"]["passes"] is True

    mode_profile = json.loads((output_dir / "mode_profile.json").read_text(encoding="utf-8"))
    assert mode_profile["name"] == "development"
    assert "requirements.md" in mode_profile["primary_outputs"]

    action_queue = json.loads((output_dir / "action_queue.json").read_text(encoding="utf-8"))
    assert any(action["type"] == "confirm_blocker_questions" for action in action_queue["actions"])
    assert any(action["type"] == "review_issue_candidates" for action in action_queue["actions"])
    assert any(action["type"] == "implementation_agent_start" for action in action_queue["actions"])
    assert any(action["type"] == "branch_creation" for action in action_queue["actions"])
    assert any(action["type"] == "pull_request_creation" for action in action_queue["actions"])
    assert any(action["type"] == "external_email_sending" for action in action_queue["actions"])
    assert all(action["requires_human_approval"] for action in action_queue["actions"])

    pr_draft = json.loads((output_dir / "pull_request_draft.json").read_text(encoding="utf-8"))
    branch_draft = json.loads(
        (output_dir / "branch_creation_draft.json").read_text(encoding="utf-8")
    )
    assert branch_draft["requires_human_approval"] is True
    assert branch_draft["branch_name"].startswith("meeting/")
    assert branch_draft["command"][:3] == ["git", "switch", "-c"]
    assert pr_draft["requires_human_approval"] is True
    assert pr_draft["branch_name"] == branch_draft["branch_name"]
    assert "implementation_plan.md" in pr_draft["source_files"]
    email_draft = json.loads((output_dir / "external_email_draft.json").read_text(encoding="utf-8"))
    assert email_draft["requires_human_approval"] is True
    assert email_draft["status"] == "draft"

    question_status = json.loads((output_dir / "question_status.json").read_text(encoding="utf-8"))
    assert question_status["counts"]["open"] >= 2
    assert all(question["status"] == "open" for question in question_status["questions"])
    questions = json.loads((output_dir / "questions.json").read_text(encoding="utf-8"))
    assert all(question["source_event_ids"] for question in questions)
    assert all(question["meeting_id"] == "mtg_local" for question in questions)
    assert all(question["created_at"] for question in questions)
    blocker_suggestions = json.loads(
        (output_dir / "blocker_question_suggestions.json").read_text(encoding="utf-8")
    )
    assert len(blocker_suggestions) >= 3
    assert all(question["category"] == "blocker" for question in blocker_suggestions)

    macos_notifications = json.loads(
        (output_dir / "macos_notification_plan.json").read_text(encoding="utf-8")
    )
    assert macos_notifications["platform"] == "macos"
    assert any(
        notification["kind"] == "blocker_question"
        for notification in macos_notifications["notifications"]
    )
    assert any(
        notification["kind"] == "meeting_ended"
        for notification in macos_notifications["notifications"]
    )
    assert macos_notifications["click_focus_route"]["focus_app"] == "Terminal"
    assert "iTerm" in macos_notifications["click_focus_route"]["supported_focus_apps"]
    assert (
        "Visual Studio Code"
        in macos_notifications["click_focus_route"]["supported_focus_apps"]
    )

    notification_policy = json.loads(
        (output_dir / "notification_policy.json").read_text(encoding="utf-8")
    )
    assert notification_policy["top_question_limit"] == 3
    assert notification_policy["highlight_categories"] == ["blocker"]
    assert (
        notification_policy["macos_notifications"]["rate_limit"][
            "max_blocker_questions_per_meeting"
        ]
        == 3
    )
    assert (
        notification_policy["macos_notifications"]["rate_limit"][
            "clarification_and_later"
        ]
        == "file_only"
    )
    assert notification_policy["slack_notifications"]["mvp_default"] == "draft_only"

    slack = json.loads((output_dir / "slack_notification.json").read_text(encoding="utf-8"))
    assert slack["status"] == "draft"
    assert slack["requires_human_approval"] is True
    assert slack["payload"]["text"].startswith("Dashboard MVP:")

    handoff = json.loads((output_dir / "agent_handoff.json").read_text(encoding="utf-8"))
    assert handoff["requires_human_approval"] is True
    assert handoff["status"] == "blocked"
    assert "implementation_plan.md" in handoff["context_files"]

    traceability = json.loads(
        (output_dir / "requirements_traceability.json").read_text(encoding="utf-8")
    )
    implemented = {item["requirement"] for item in traceability["implemented"]}
    not_implemented = {item["requirement"] for item in traceability["not_implemented"]}
    verification_required = {
        item["requirement"] for item in traceability["verification_required"]
    }
    assert "text_stream_input" in implemented
    assert "openai_realtime_session_creation" in implemented
    assert "openai_realtime_audio_streaming" in implemented
    assert "live_audio_capture" in implemented
    assert "macos_notifications" in implemented
    assert "notification_focus_route" in implemented
    assert "high_accuracy_speaker_diarization_adapter" in implemented
    assert "openai_realtime_api_live_execution" in verification_required
    assert "high_accuracy_speaker_diarization" not in not_implemented

    state_snapshot = json.loads((output_dir / "state_snapshot.json").read_text(encoding="utf-8"))
    assert state_snapshot["project_name"] == "Dashboard MVP"
    assert state_snapshot["transcript"]["line_count"] == 5
    assert state_snapshot["state"]["requirement_ids"]
    assert state_snapshot["state"]["question_ids"]
    assert "requirements.md" in state_snapshot["artifacts"]

    issues = json.loads((output_dir / "issue_candidates.json").read_text(encoding="utf-8"))
    issue_status = json.loads((output_dir / "issue_status.json").read_text(encoding="utf-8"))
    assert issue_status["counts"]["candidate"] >= 1
    assert any("ダッシュボード" in issue["title"] for issue in issues)
    assert all(issue["meeting_id"] == "mtg_local" for issue in issues)
    assert all("external_url" in issue for issue in issues)
    assert all(issue["status"] == "candidate" for issue in issues)
    assert all(issue["approval_required"] for issue in issues)
    assert all(issue["external_registration_status"] == "not_requested" for issue in issues)
    assert all(issue["source_range"] for issue in issues)
    assert all(issue["source_event_ids"] for issue in issues)
    assert all(issue["acceptance_criteria"] for issue in issues)
    assert all(issue["granularity"] for issue in issues)
    assert all(issue["granularity_reason"] for issue in issues)

    transcript_events = json.loads(
        (output_dir / "transcript_events.json").read_text(encoding="utf-8")
    )
    assert all(event["meeting_id"] == "mtg_local" for event in transcript_events)
    assert all(event["type"] == "final" for event in transcript_events)
    assert transcript_events[1]["start_ms"] == 30000
    assert all(event["created_at"] for event in transcript_events)


def test_dashboard_limits_top_questions_to_three(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    transcript = "\n".join(
        f"[00:0{index}] Eng: 確認事項その{index}ですか？" for index in range(1, 6)
    )

    process_transcript(
        transcript=transcript,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="Question Limit",
    )

    dashboard = (output_dir / "dashboard.html").read_text(encoding="utf-8")
    top_questions = dashboard.split("Top Questions", 1)[1].split(
        "Issue Candidates", 1
    )[0]
    assert "確認事項その1" in top_questions
    assert "確認事項その2" in top_questions
    assert "確認事項その3" in top_questions
    assert "確認事項その4" not in top_questions
    assert "確認事項その5" not in top_questions


def test_confidential_mode_disables_external_registration(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    process_transcript(
        transcript=SAMPLE_TRANSCRIPT,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="Confidential MVP",
        confidential=True,
        retention_days=7,
        external_destinations=["github", "notion"],
        external_registration_enabled=True,
    )

    audit_log = json.loads((output_dir / "audit_log.json").read_text(encoding="utf-8"))
    privacy = json.loads((output_dir / "privacy_manifest.json").read_text(encoding="utf-8"))

    assert audit_log["external_registration_enabled"] is False
    assert audit_log["external_destinations"] == []
    assert privacy["confidential"] is True
    assert privacy["retention_days"] == 7
    assert privacy["external_destinations"] == []
    assert privacy["external_registration_enabled"] is False

    action_queue = json.loads((output_dir / "action_queue.json").read_text(encoding="utf-8"))
    assert not any(
        action["type"] == "external_issue_registration" for action in action_queue["actions"]
    )


def test_external_registration_actions_require_approval_when_enabled(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    process_transcript(
        transcript=SAMPLE_TRANSCRIPT,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="External Registration MVP",
        external_destinations=["github"],
        external_registration_enabled=True,
    )

    action_queue = json.loads((output_dir / "action_queue.json").read_text(encoding="utf-8"))
    registration_actions = [
        action
        for action in action_queue["actions"]
        if action["type"] == "external_issue_registration"
    ]

    assert len(registration_actions) == 1
    assert registration_actions[0]["destination"] == "github"
    assert registration_actions[0]["status"] == "pending_approval"
    assert registration_actions[0]["requires_human_approval"] is True

    payloads = json.loads(
        (output_dir / "external_registration_payloads.json").read_text(encoding="utf-8")
    )
    assert payloads["external_registration_enabled"] is True
    assert payloads["payloads"][0]["destination"] == "github"
    assert payloads["payloads"][0]["status"] == "pending_approval"
    assert payloads["payloads"][0]["requires_human_approval"] is True
    assert payloads["payloads"][0]["items"][0]["title"]


def test_external_registration_payloads_cover_named_destinations(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    process_transcript(
        transcript=SAMPLE_TRANSCRIPT,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="External Destinations MVP",
        external_destinations=[
            "github",
            "linear",
            "notion",
            "google-docs",
            "google-slides",
            "crm",
            "ats",
        ],
        external_registration_enabled=True,
    )

    payloads = json.loads(
        (output_dir / "external_registration_payloads.json").read_text(encoding="utf-8")
    )
    destinations = {payload["destination"] for payload in payloads["payloads"]}
    assert {
        "github",
        "linear",
        "notion",
        "google_docs",
        "google_slides",
        "crm",
        "ats",
    }.issubset(destinations)
    by_destination = {payload["destination"]: payload for payload in payloads["payloads"]}
    assert "document_body" in by_destination["google_docs"]["items"][0]
    assert "slides" in by_destination["google_slides"]["items"][0]
    assert "stage" in by_destination["crm"]["items"][0]
    assert "stage" in by_destination["ats"]["items"][0]


def test_process_transcript_prioritizes_blocker_questions(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    result = process_transcript(
        transcript=SAMPLE_TRANSCRIPT,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="Dashboard MVP",
    )

    questions = (output_dir / "open_questions.md").read_text(encoding="utf-8")
    assert "## Blocker" in questions
    assert "権限" in questions or "管理者" in questions
    assert result.metrics["blocker_question_count"] >= 1
    suggestions = json.loads(
        (output_dir / "blocker_question_suggestions.json").read_text(encoding="utf-8")
    )
    assert len(suggestions) >= 3


def test_question_classification_covers_required_categories(tmp_path: Path) -> None:
    transcript = "\n".join(
        [
            "[00:00] Eng: 管理者権限は必要ですか？",
            "[00:10] Sales: 予算と決裁者は誰ですか？",
            "[00:20] PM: ラベル名は何ですか？",
            "[00:30] PM: この確認は後で非同期でよいですか？",
        ]
    )
    output_dir = tmp_path / "out"

    process_transcript(
        transcript=transcript,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="Question Categories",
    )

    questions = json.loads((output_dir / "questions.json").read_text(encoding="utf-8"))
    categories = {question["category"] for question in questions}

    assert {"blocker", "high_impact", "clarification", "later"}.issubset(categories)


def test_plain_mvp_mentions_do_not_become_confirmed_decisions(tmp_path: Path) -> None:
    transcript = "[00:00] PM: MVPではログイン後のダッシュボードが必要です。"
    output_dir = tmp_path / "out"

    result = process_transcript(
        transcript=transcript,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="False Positive Guard",
    )

    assert result.metrics["decision_count"] == 0
    requirements = (output_dir / "requirements.md").read_text(encoding="utf-8")
    assert "[confirmed]" not in requirements


def test_plain_requirement_mentions_do_not_become_questions(tmp_path: Path) -> None:
    transcript = "[00:00] PM: MVPではログイン後のダッシュボードが必要です。"
    output_dir = tmp_path / "out"

    result = process_transcript(
        transcript=transcript,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="False Positive Guard",
    )

    assert result.metrics["question_count"] == 0
    suggestions = json.loads(
        (output_dir / "blocker_question_suggestions.json").read_text(encoding="utf-8")
    )
    assert len(suggestions) == 3


def test_prioritized_questions_keep_transcript_order_within_same_priority(
    tmp_path: Path,
) -> None:
    transcript = "\n".join(
        f"[00:{index:02d}] Eng: 確認事項その{index}ですか？" for index in range(1, 12)
    )
    output_dir = tmp_path / "out"

    process_transcript(
        transcript=transcript,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="Question Ordering",
    )

    questions = (output_dir / "open_questions.md").read_text(encoding="utf-8")
    assert questions.index("確認事項その2") < questions.index("確認事項その10")


def test_issue_candidates_merge_duplicate_titles(tmp_path: Path) -> None:
    transcript = "\n".join(
        [
            "[00:00] PM: ログイン後のダッシュボードを表示します。",
            "[00:10] PM: ダッシュボードには日次更新データを表示します。",
            "[00:20] Eng: GitHub Issueにもしてください。",
        ]
    )
    output_dir = tmp_path / "out"

    process_transcript(
        transcript=transcript,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="Issue Merge",
    )

    issues = json.loads((output_dir / "issue_candidates.json").read_text(encoding="utf-8"))
    dashboard_issues = [
        issue for issue in issues if issue["title"] == "ダッシュボードMVPを実装する"
    ]

    assert len(dashboard_issues) == 1
    assert dashboard_issues[0]["merged_candidate_count"] >= 2
    assert dashboard_issues[0]["granularity"] in {"implementable", "review_needed", "too_large"}
    assert len(dashboard_issues[0]["source_event_ids"]) >= 2


def test_process_transcript_evaluation_contains_quantitative_and_qualitative_sections(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"

    process_transcript(
        transcript=SAMPLE_TRANSCRIPT,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="Dashboard MVP",
    )

    evaluation = json.loads((output_dir / "evaluation.json").read_text(encoding="utf-8"))
    assert "quantitative" in evaluation
    assert "qualitative" in evaluation
    assert "quality_score" in evaluation["quantitative"]
    assert "strengths" in evaluation["qualitative"]
    assert "risks" in evaluation["qualitative"]


def test_process_transcript_generates_mode_specific_outputs(tmp_path: Path) -> None:
    sales_dir = tmp_path / "sales"
    hiring_dir = tmp_path / "hiring"
    presentation_dir = tmp_path / "presentation"

    process_transcript(
        transcript=SAMPLE_TRANSCRIPT,
        output_dir=sales_dir,
        meeting_mode="sales",
        project_name="Sales Call",
    )
    process_transcript(
        transcript=SAMPLE_TRANSCRIPT,
        output_dir=hiring_dir,
        meeting_mode="hiring",
        project_name="Hiring Interview",
    )
    process_transcript(
        transcript=SAMPLE_TRANSCRIPT,
        output_dir=presentation_dir,
        meeting_mode="presentation",
        project_name="Talk Prep",
    )

    assert (sales_dir / "account_summary.md").exists()
    assert (sales_dir / "crm_update.json").exists()
    sales_diagrams = (sales_dir / "diagrams.md").read_text(encoding="utf-8")
    assert "## Sales Problem Structure" in sales_diagrams
    assert "## Sales Proposal Story" in sales_diagrams
    assert "## Sales Adoption Steps" in sales_diagrams
    assert (hiring_dir / "interview_transcript.md").exists()
    assert (hiring_dir / "candidate_scorecard.md").exists()
    assert (presentation_dir / "talk_brief.md").exists()
    assert (presentation_dir / "speaker_notes_draft.md").exists()
    presentation_diagrams = (presentation_dir / "diagrams.md").read_text(encoding="utf-8")
    assert "## Talk Structure" in presentation_diagrams
    assert "## Talk Storyline" in presentation_diagrams


def test_process_transcript_events_uses_only_final_events_for_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    result = process_transcript_events(
        events=[
            TranscriptEvent(
                kind="partial",
                timestamp="00:00",
                speaker="PM",
                text="ログイン後のダッシュボードと管理者権限が必要かもしれません",
                source_event_id="evt_partial_1",
            ),
            TranscriptEvent(
                kind="final",
                timestamp="00:02",
                speaker="PM",
                text="ログイン後のダッシュボードをMVPで作ります。",
                source_event_id="evt_final_1",
            ),
            TranscriptEvent(
                kind="final",
                timestamp="00:20",
                speaker="Eng",
                text="管理者権限は必要ですか？",
                source_event_id="evt_final_2",
            ),
        ],
        output_dir=output_dir,
        meeting_mode="development",
        project_name="Realtime MVP",
    )

    assert result.metrics["partial_transcript_event_count"] == 1
    assert result.metrics["final_transcript_event_count"] == 2
    assert result.metrics["transcript_lines"] == 2
    assert (output_dir / "transcript_events.json").exists()
    assert (output_dir / "partial_transcript.md").exists()
    evaluation = json.loads((output_dir / "evaluation.json").read_text(encoding="utf-8"))
    state_snapshot = json.loads((output_dir / "state_snapshot.json").read_text(encoding="utf-8"))
    performance = json.loads((output_dir / "performance_manifest.json").read_text(encoding="utf-8"))
    success_conditions = json.loads(
        (output_dir / "mvp_success_conditions.json").read_text(encoding="utf-8")
    )
    assert evaluation["quantitative"]["partial_transcript_event_count"] == 1
    assert state_snapshot["metrics"]["transcript_event_count"] == 3
    assert performance["metrics"]["partial_transcript_event_count"] == 1
    assert success_conditions["metrics"]["final_transcript_event_count"] == 2

    transcript = (output_dir / "transcript.md").read_text(encoding="utf-8")
    partial_transcript = (output_dir / "partial_transcript.md").read_text(encoding="utf-8")
    assert "かもしれません" not in transcript
    assert "かもしれません" in partial_transcript
    requirements = json.loads((output_dir / "requirements_items.json").read_text(encoding="utf-8"))
    questions = json.loads((output_dir / "questions.json").read_text(encoding="utf-8"))
    issues = json.loads((output_dir / "issue_candidates.json").read_text(encoding="utf-8"))
    assert all("line_" not in item["source_event_ids"] for item in requirements)
    requirement_event_ids = {
        event_id for item in requirements for event_id in item["source_event_ids"]
    }
    assert "evt_final_1" in requirement_event_ids
    assert "evt_final_2" in requirement_event_ids
    assert "evt_partial_1" not in requirement_event_ids
    assert questions[0]["source_event_ids"] == ["evt_final_2"]
    assert "evt_final_1" in issues[0]["source_event_ids"]


def test_transcript_events_without_source_id_get_fallback_ids(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    process_transcript_events(
        events=[
            TranscriptEvent(kind="partial", timestamp="00:00", speaker="PM", text="仮説です"),
            TranscriptEvent(kind="final", timestamp="00:02", speaker="PM", text="確定です。"),
        ],
        output_dir=output_dir,
        meeting_mode="development",
        project_name="Fallback Events",
    )

    events = json.loads((output_dir / "transcript_events.json").read_text(encoding="utf-8"))
    assert [event["id"] for event in events] == ["evt_1", "evt_2"]
    assert [event["source_event_id"] for event in events] == ["evt_1", "evt_2"]
