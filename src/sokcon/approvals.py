from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Dict, Sequence

from sokcon.integrations import ExternalRegistrationConfig, post_external_registration

VALID_QUESTION_STATUSES = {"open", "answered", "dismissed"}
VALID_ISSUE_STATUSES = {"candidate", "draft", "approved", "registered", "rejected"}


def build_approval_plan(
    *,
    artifact_dir: Path,
    approved_action_ids: Sequence[str],
) -> Dict[str, object]:
    queue = read_json(artifact_dir / "action_queue.json")
    actions = queue.get("actions", [])
    approved = set(approved_action_ids)
    plan_actions = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_id = str(action.get("id", ""))
        if action_id not in approved:
            continue
        plan_actions.append(approve_action(action, artifact_dir))
    known_ids = {str(action.get("id", "")) for action in actions if isinstance(action, dict)}
    missing_ids = sorted(approved - known_ids)
    return {
        "status": "ready" if plan_actions and not missing_ids else "needs_review",
        "approved_action_ids": sorted(approved),
        "missing_action_ids": missing_ids,
        "actions": plan_actions,
        "external_effects_executed": False,
    }


def approve_action(action: Dict[str, object], artifact_dir: Path) -> Dict[str, object]:
    status = str(action.get("status", ""))
    action_type = str(action.get("type", ""))
    approved_status = (
        "approved" if status in {"pending_approval", "pending_review"} else "not_executable"
    )
    return {
        **action,
        "approval_status": approved_status,
        "ready_to_execute": approved_status == "approved",
        "execution_payload": execution_payload_for(action_type, action, artifact_dir),
    }


def execution_payload_for(
    action_type: str,
    action: Dict[str, object],
    artifact_dir: Path,
) -> object:
    if action_type == "external_issue_registration":
        destination = str(action.get("destination", ""))
        payloads = read_json(artifact_dir / "external_registration_payloads.json")
        for payload in payloads.get("payloads", []):
            if isinstance(payload, dict) and payload.get("destination") == destination:
                return payload
        return {}
    if action_type == "implementation_agent_start":
        return read_json(artifact_dir / "agent_handoff.json")
    if action_type == "branch_creation":
        return read_json(artifact_dir / "branch_creation_draft.json")
    if action_type == "pull_request_creation":
        return read_json(artifact_dir / "pull_request_draft.json")
    if action_type == "external_email_sending":
        return read_json(artifact_dir / "external_email_draft.json")
    if action_type == "review_issue_candidates":
        return read_json(artifact_dir / "issue_candidates.json")
    if action_type == "confirm_blocker_questions":
        return read_text(artifact_dir / "open_questions.md")
    return {}


def write_approval_plan(
    *,
    artifact_dir: Path,
    approved_action_ids: Sequence[str],
) -> Path:
    plan = build_approval_plan(
        artifact_dir=artifact_dir,
        approved_action_ids=approved_action_ids,
    )
    output = artifact_dir / "approval_plan.json"
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def update_question_status(
    *,
    artifact_dir: Path,
    question_id: str,
    status: str,
) -> Path:
    if status not in VALID_QUESTION_STATUSES:
        raise ValueError(f"question status must be one of: {sorted(VALID_QUESTION_STATUSES)}")
    questions_path = artifact_dir / "questions.json"
    payload = read_json(questions_path)
    if not isinstance(payload, list):
        raise ValueError("questions.json must contain a list")
    updated = False
    for question in payload:
        if not isinstance(question, dict):
            continue
        if question.get("id") == question_id:
            question["status"] = status
            updated = True
    if not updated:
        raise ValueError(f"question id not found: {question_id}")
    questions_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    status_path = artifact_dir / "question_status.json"
    status_path.write_text(
        json.dumps(build_question_status_summary(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return status_path


def build_question_status_summary(questions: Sequence[object]) -> Dict[str, object]:
    counts = {status: 0 for status in sorted(VALID_QUESTION_STATUSES)}
    items = []
    for question in questions:
        if not isinstance(question, dict):
            continue
        status = str(question.get("status", "open"))
        counts.setdefault(status, 0)
        counts[status] += 1
        items.append(
            {
                "id": question.get("id", ""),
                "status": status,
                "category": question.get("category", ""),
                "question": question.get("question", ""),
            }
        )
    return {"counts": counts, "questions": items}


def update_issue_status(
    *,
    artifact_dir: Path,
    issue_id: str,
    status: str,
) -> Path:
    if status not in VALID_ISSUE_STATUSES:
        raise ValueError(f"issue status must be one of: {sorted(VALID_ISSUE_STATUSES)}")
    issues_path = artifact_dir / "issue_candidates.json"
    payload = read_json(issues_path)
    if not isinstance(payload, list):
        raise ValueError("issue_candidates.json must contain a list")
    updated = False
    for issue in payload:
        if not isinstance(issue, dict):
            continue
        if issue.get("id") == issue_id:
            issue["status"] = status
            updated = True
    if not updated:
        raise ValueError(f"issue id not found: {issue_id}")
    issues_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    status_path = artifact_dir / "issue_status.json"
    status_path.write_text(
        json.dumps(build_issue_status_summary(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return status_path


def build_issue_status_summary(issues: Sequence[object]) -> Dict[str, object]:
    counts = {status: 0 for status in sorted(VALID_ISSUE_STATUSES)}
    items = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        status = str(issue.get("status", "candidate"))
        counts.setdefault(status, 0)
        counts[status] += 1
        items.append(
            {
                "id": issue.get("id", ""),
                "status": status,
                "title": issue.get("title", ""),
                "external_registration_status": issue.get(
                    "external_registration_status",
                    "not_requested",
                ),
            }
        )
    return {"counts": counts, "issues": items}


def execute_approval_plan(
    *,
    artifact_dir: Path,
    config: ExternalRegistrationConfig,
    execute: bool = False,
    post_json: object | None = None,
) -> Dict[str, object]:
    plan = read_json(artifact_dir / "approval_plan.json")
    actions = plan.get("actions", [])
    results = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        if action.get("type") != "external_issue_registration":
            if action.get("type") == "implementation_agent_start":
                results.append(
                    execute_agent_start_action(
                        action=action,
                        artifact_dir=artifact_dir,
                        execute=execute,
                    )
                )
            elif action.get("type") == "external_email_sending":
                results.append(execute_external_email_action(action=action, execute=execute))
            elif action.get("type") == "branch_creation":
                results.append(execute_branch_creation_action(action=action, execute=execute))
            continue
        if not action.get("ready_to_execute"):
            results.append({"id": action.get("id", ""), "status": "skipped"})
            continue
        results.append(
            execute_external_registration_action(
                action=action,
                config=config,
                execute=execute,
                post_json=post_json,
            )
        )
    return {
        "status": "executed" if execute else "dry_run",
        "network_request_executed": execute,
        "results": results,
    }


def execute_external_email_action(
    *,
    action: Dict[str, object],
    execute: bool,
) -> Dict[str, object]:
    if not action.get("ready_to_execute"):
        return {"id": action.get("id", ""), "status": "skipped"}
    return {
        "id": action.get("id", ""),
        "status": "dry_run" if not execute else "manual_send_required",
        "external_email_request_executed": False,
        "message": "External email sending requires a human-operated mail client integration.",
    }


def execute_branch_creation_action(
    *,
    action: Dict[str, object],
    execute: bool,
) -> Dict[str, object]:
    if not action.get("ready_to_execute"):
        return {"id": action.get("id", ""), "status": "skipped"}
    payload = action.get("execution_payload", {})
    command = payload.get("command", []) if isinstance(payload, dict) else []
    if not execute:
        return {
            "id": action.get("id", ""),
            "status": "dry_run",
            "branch_creation_executed": False,
            "command": command,
        }
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    return {
        "id": action.get("id", ""),
        "status": "created" if completed.returncode == 0 else "failed",
        "branch_creation_executed": completed.returncode == 0,
        "command": command,
        "result": {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        },
    }


def execute_agent_start_action(
    *,
    action: Dict[str, object],
    artifact_dir: Path,
    execute: bool,
    runner: object | None = None,
) -> Dict[str, object]:
    if not action.get("ready_to_execute"):
        return {"id": action.get("id", ""), "status": "skipped"}
    payload = action.get("execution_payload", {})
    if not isinstance(payload, dict):
        payload = {}
    commands = payload.get("suggested_commands", [])
    if not isinstance(commands, list) or not commands:
        return {"id": action.get("id", ""), "status": "missing_command"}
    command = str(commands[0].get("command", "")) if isinstance(commands[0], dict) else ""
    if not execute:
        return {
            "id": action.get("id", ""),
            "status": "dry_run",
            "command": command,
        }
    run = runner if runner is not None else run_agent_command
    return {
        "id": action.get("id", ""),
        "status": "started",
        "result": run(command, artifact_dir),
    }


def run_agent_command(command: str, cwd: Path) -> Dict[str, object]:
    completed = subprocess.run(
        shlex.split(command),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def execute_external_registration_action(
    *,
    action: Dict[str, object],
    config: ExternalRegistrationConfig,
    execute: bool,
    post_json: object | None = None,
) -> Dict[str, object]:
    destination = str(action.get("destination", ""))
    payload = action.get("execution_payload", {})
    if not isinstance(payload, dict):
        payload = {}
    items = payload.get("items", [])
    if not execute:
        return {
            "id": action.get("id", ""),
            "destination": destination,
            "status": "dry_run",
            "item_count": len(items) if isinstance(items, list) else 0,
        }
    sender = post_json if post_json is not None else post_external_registration
    responses = [
        sender(destination, item, config)
        for item in items
        if isinstance(item, dict)
    ]
    return {
        "id": action.get("id", ""),
        "destination": destination,
        "status": "sent",
        "responses": responses,
    }


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
