import json
from pathlib import Path

from sokcon.approvals import (
    build_approval_plan,
    build_issue_status_summary,
    build_question_status_summary,
    execute_agent_start_action,
    execute_approval_plan,
    update_issue_status,
    update_question_status,
    write_approval_plan,
)
from sokcon.integrations import load_external_registration_config


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_approval_plan_promotes_only_selected_actions(tmp_path: Path) -> None:
    write_json(
        tmp_path / "action_queue.json",
        {
            "actions": [
                {
                    "id": "action_register_issues_github",
                    "type": "external_issue_registration",
                    "destination": "github",
                    "status": "pending_approval",
                    "requires_human_approval": True,
                },
                {
                    "id": "action_start_implementation_agent",
                    "type": "implementation_agent_start",
                    "status": "blocked",
                    "requires_human_approval": True,
                },
            ]
        },
    )
    write_json(
        tmp_path / "external_registration_payloads.json",
        {"payloads": [{"destination": "github", "items": [{"title": "Do work"}]}]},
    )

    plan = build_approval_plan(
        artifact_dir=tmp_path,
        approved_action_ids=["action_register_issues_github"],
    )

    assert plan["status"] == "ready"
    assert plan["external_effects_executed"] is False
    assert len(plan["actions"]) == 1
    assert plan["actions"][0]["approval_status"] == "approved"
    assert plan["actions"][0]["ready_to_execute"] is True
    assert plan["actions"][0]["execution_payload"]["destination"] == "github"


def test_build_approval_plan_marks_blocked_action_not_executable(tmp_path: Path) -> None:
    write_json(
        tmp_path / "action_queue.json",
        {
            "actions": [
                {
                    "id": "action_start_implementation_agent",
                    "type": "implementation_agent_start",
                    "status": "blocked",
                    "requires_human_approval": True,
                }
            ]
        },
    )
    write_json(tmp_path / "agent_handoff.json", {"status": "blocked"})

    plan = build_approval_plan(
        artifact_dir=tmp_path,
        approved_action_ids=["action_start_implementation_agent"],
    )

    assert plan["actions"][0]["approval_status"] == "not_executable"
    assert plan["actions"][0]["ready_to_execute"] is False


def test_build_approval_plan_includes_pull_request_payload(tmp_path: Path) -> None:
    write_json(
        tmp_path / "action_queue.json",
        {
            "actions": [
                {
                    "id": "action_create_pull_request",
                    "type": "pull_request_creation",
                    "status": "pending_approval",
                    "requires_human_approval": True,
                }
            ]
        },
    )
    write_json(tmp_path / "pull_request_draft.json", {"title": "Draft PR"})

    plan = build_approval_plan(
        artifact_dir=tmp_path,
        approved_action_ids=["action_create_pull_request"],
    )

    assert plan["actions"][0]["execution_payload"]["title"] == "Draft PR"


def test_build_approval_plan_includes_external_email_payload(tmp_path: Path) -> None:
    write_json(
        tmp_path / "action_queue.json",
        {
            "actions": [
                {
                    "id": "action_send_external_email",
                    "type": "external_email_sending",
                    "status": "pending_approval",
                    "requires_human_approval": True,
                }
            ]
        },
    )
    write_json(tmp_path / "external_email_draft.json", {"subject": "Follow up"})

    plan = build_approval_plan(
        artifact_dir=tmp_path,
        approved_action_ids=["action_send_external_email"],
    )

    assert plan["actions"][0]["execution_payload"]["subject"] == "Follow up"


def test_build_approval_plan_includes_branch_creation_payload(tmp_path: Path) -> None:
    write_json(
        tmp_path / "action_queue.json",
        {
            "actions": [
                {
                    "id": "action_create_branch",
                    "type": "branch_creation",
                    "status": "pending_approval",
                    "requires_human_approval": True,
                }
            ]
        },
    )
    write_json(
        tmp_path / "branch_creation_draft.json",
        {"branch_name": "meeting/work", "command": ["git", "switch", "-c", "meeting/work"]},
    )

    plan = build_approval_plan(
        artifact_dir=tmp_path,
        approved_action_ids=["action_create_branch"],
    )

    assert plan["actions"][0]["execution_payload"]["branch_name"] == "meeting/work"


def test_write_approval_plan_writes_artifact(tmp_path: Path) -> None:
    write_json(tmp_path / "action_queue.json", {"actions": []})

    output = write_approval_plan(artifact_dir=tmp_path, approved_action_ids=["missing"])

    assert output.name == "approval_plan.json"
    plan = json.loads(output.read_text(encoding="utf-8"))
    assert plan["missing_action_ids"] == ["missing"]


def test_update_question_status_persists_question_state(tmp_path: Path) -> None:
    write_json(
        tmp_path / "questions.json",
        [
            {
                "id": "q_1",
                "question": "管理者権限は必要ですか？",
                "category": "blocker",
                "status": "open",
            }
        ],
    )

    output = update_question_status(
        artifact_dir=tmp_path,
        question_id="q_1",
        status="answered",
    )

    summary = json.loads(output.read_text(encoding="utf-8"))
    questions = json.loads((tmp_path / "questions.json").read_text(encoding="utf-8"))
    assert summary["counts"]["answered"] == 1
    assert questions[0]["status"] == "answered"


def test_build_question_status_summary_counts_statuses() -> None:
    summary = build_question_status_summary([
        {"id": "q_1", "question": "Q1", "category": "blocker", "status": "answered"},
        {"id": "q_2", "question": "Q2", "category": "later", "status": "open"},
    ])

    assert summary["counts"]["answered"] == 1
    assert summary["counts"]["open"] == 1


def test_update_issue_status_persists_issue_state(tmp_path: Path) -> None:
    write_json(
        tmp_path / "issue_candidates.json",
        [
            {
                "id": "issue_1",
                "title": "Do work",
                "status": "candidate",
                "external_registration_status": "not_requested",
            }
        ],
    )

    output = update_issue_status(
        artifact_dir=tmp_path,
        issue_id="issue_1",
        status="approved",
    )

    summary = json.loads(output.read_text(encoding="utf-8"))
    issues = json.loads((tmp_path / "issue_candidates.json").read_text(encoding="utf-8"))
    assert summary["counts"]["approved"] == 1
    assert issues[0]["status"] == "approved"


def test_build_issue_status_summary_counts_statuses() -> None:
    summary = build_issue_status_summary([
        {"id": "issue_1", "title": "One", "status": "registered"},
        {"id": "issue_2", "title": "Two", "status": "rejected"},
    ])

    assert summary["counts"]["registered"] == 1
    assert summary["counts"]["rejected"] == 1


def test_execute_approval_plan_dry_run_does_not_send(tmp_path: Path) -> None:
    write_json(
        tmp_path / "approval_plan.json",
        {
            "actions": [
                {
                    "id": "action_register_issues_github",
                    "type": "external_issue_registration",
                    "destination": "github",
                    "ready_to_execute": True,
                    "execution_payload": {"items": [{"title": "Do work"}]},
                }
            ]
        },
    )

    result = execute_approval_plan(
        artifact_dir=tmp_path,
        config=load_external_registration_config({}),
    )

    assert result["status"] == "dry_run"
    assert result["network_request_executed"] is False
    assert result["results"][0]["item_count"] == 1


def test_execute_approval_plan_external_email_requires_manual_send(tmp_path: Path) -> None:
    write_json(
        tmp_path / "approval_plan.json",
        {
            "actions": [
                {
                    "id": "action_send_external_email",
                    "type": "external_email_sending",
                    "ready_to_execute": True,
                    "execution_payload": {"subject": "Follow up"},
                }
            ]
        },
    )

    result = execute_approval_plan(
        artifact_dir=tmp_path,
        config=load_external_registration_config({}),
        execute=True,
    )

    assert result["results"][0]["status"] == "manual_send_required"
    assert result["results"][0]["external_email_request_executed"] is False


def test_execute_approval_plan_branch_creation_dry_run(tmp_path: Path) -> None:
    write_json(
        tmp_path / "approval_plan.json",
        {
            "actions": [
                {
                    "id": "action_create_branch",
                    "type": "branch_creation",
                    "ready_to_execute": True,
                    "execution_payload": {
                        "branch_name": "meeting/work",
                        "command": ["git", "switch", "-c", "meeting/work"],
                    },
                }
            ]
        },
    )

    result = execute_approval_plan(
        artifact_dir=tmp_path,
        config=load_external_registration_config({}),
    )

    assert result["results"][0]["status"] == "dry_run"
    assert result["results"][0]["branch_creation_executed"] is False


def test_execute_approval_plan_execute_uses_injected_sender(tmp_path: Path) -> None:
    write_json(
        tmp_path / "approval_plan.json",
        {
            "actions": [
                {
                    "id": "action_register_issues_github",
                    "type": "external_issue_registration",
                    "destination": "github",
                    "ready_to_execute": True,
                    "execution_payload": {"items": [{"title": "Do work"}]},
                }
            ]
        },
    )
    config = load_external_registration_config(
        {"GITHUB_TOKEN": "ghp-secret", "SOKCON_GITHUB_REPOSITORY": "owner/repo"}
    )
    calls = []

    def fake_sender(destination, item, sender_config):
        calls.append((destination, item, sender_config.github_repository))
        return {"id": "created"}

    result = execute_approval_plan(
        artifact_dir=tmp_path,
        config=config,
        execute=True,
        post_json=fake_sender,
    )

    assert result["status"] == "executed"
    assert result["network_request_executed"] is True
    assert calls == [("github", {"title": "Do work"}, "owner/repo")]
    assert result["results"][0]["responses"] == [{"id": "created"}]


def test_execute_agent_start_action_dry_run_does_not_start_process(tmp_path: Path) -> None:
    action = {
        "id": "action_start_implementation_agent",
        "ready_to_execute": True,
        "execution_payload": {
            "suggested_commands": [{"command": "codex run 'Implement approved issues'"}]
        },
    }

    result = execute_agent_start_action(action=action, artifact_dir=tmp_path, execute=False)

    assert result["status"] == "dry_run"
    assert result["command"] == "codex run 'Implement approved issues'"


def test_execute_agent_start_action_execute_uses_runner(tmp_path: Path) -> None:
    action = {
        "id": "action_start_implementation_agent",
        "ready_to_execute": True,
        "execution_payload": {"suggested_commands": [{"command": "codex run task"}]},
    }
    calls = []

    def fake_runner(command, cwd):
        calls.append((command, cwd))
        return {"returncode": 0}

    result = execute_agent_start_action(
        action=action,
        artifact_dir=tmp_path,
        execute=True,
        runner=fake_runner,
    )

    assert result["status"] == "started"
    assert result["result"] == {"returncode": 0}
    assert calls == [("codex run task", tmp_path)]
