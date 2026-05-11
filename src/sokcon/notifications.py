from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, Sequence

Runner = Callable[[list[str]], Dict[str, object]]
SUPPORTED_FOCUS_APPS = {
    "terminal": "Terminal",
    "terminal.app": "Terminal",
    "iterm": "iTerm",
    "iterm2": "iTerm",
    "visual studio code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",
}


@dataclass(frozen=True)
class NotificationConfig:
    focus_app: str = "Terminal"
    enabled: bool = True


def load_notification_config(env: Dict[str, str] | None = None) -> NotificationConfig:
    values = env if env is not None else os.environ
    return NotificationConfig(
        focus_app=normalize_focus_app(values.get("SOKCON_NOTIFICATION_FOCUS_APP", "Terminal")),
        enabled=values.get("SOKCON_DISABLE_MACOS_NOTIFICATIONS", "") != "1",
    )


def describe_notification_config(config: NotificationConfig) -> Dict[str, object]:
    return {
        **asdict(config),
        "supported_focus_apps": sorted(set(SUPPORTED_FOCUS_APPS.values())),
        "focus_command": build_focus_command(config.focus_app),
    }


def build_macos_notification_plan(
    *,
    project_name: str,
    questions: Sequence[Dict[str, object]],
    action_queue: Dict[str, object],
    config: NotificationConfig | None = None,
) -> Dict[str, object]:
    notification_config = config or load_notification_config()
    focus_app = notification_config.focus_app
    blocker_questions = [item for item in questions if item.get("category") == "blocker"]
    pending_actions = [
        action
        for action in action_queue.get("actions", [])
        if isinstance(action, dict)
        and action.get("requires_human_approval") is True
        and action.get("status") in {"pending_review", "pending_approval"}
    ]
    notifications: list[Dict[str, object]] = []
    for question in blocker_questions[:3]:
        notifications.append(
            build_notification(
                kind="blocker_question",
                title=f"{project_name}: blocker question",
                message=str(question["question"]),
                subtitle="Needs attention during the meeting",
                focus_app=focus_app,
            )
        )
    notifications.append(
        build_notification(
            kind="meeting_ended",
            title=f"{project_name}: artifacts ready",
            message="Transcript, summary, requirements, questions, issues, and plan are ready.",
            subtitle="Meeting completed",
            focus_app=focus_app,
        )
    )
    if pending_actions:
        notifications.append(
            build_notification(
                kind="approval_waiting",
                title=f"{project_name}: approvals waiting",
                message=f"{len(pending_actions)} action(s) require human approval.",
                subtitle="Review action_queue.json",
                focus_app=focus_app,
            )
        )
    return {
        "platform": "macos",
        "status": "draft",
        "enabled": notification_config.enabled,
        "requires_human_approval": False,
        "click_focus_route": {
            "focus_app": focus_app,
            "command": build_focus_command(focus_app),
            "supported_focus_apps": sorted(set(SUPPORTED_FOCUS_APPS.values())),
            "note": (
                "Run the focus command from notification handlers or approval tooling to "
                "return to the active terminal/app window."
            ),
        },
        "notifications": notifications,
    }


def build_notification(
    *,
    kind: str,
    title: str,
    message: str,
    subtitle: str,
    focus_app: str,
) -> Dict[str, object]:
    return {
        "kind": kind,
        "title": title,
        "message": message,
        "subtitle": subtitle,
        "command": build_display_notification_command(
            title=title,
            message=message,
            subtitle=subtitle,
        ),
        "focus_command": build_focus_command(focus_app),
    }


def build_display_notification_command(*, title: str, message: str, subtitle: str) -> list[str]:
    script = f'display notification {applescript_string(message)}'
    script += f' with title {applescript_string(title)}'
    if subtitle:
        script += f' subtitle {applescript_string(subtitle)}'
    return ["osascript", "-e", script]


def build_focus_command(app_name: str) -> list[str]:
    focus_app = normalize_focus_app(app_name)
    return ["osascript", "-e", f"tell application {applescript_string(focus_app)} to activate"]


def normalize_focus_app(app_name: str) -> str:
    normalized = app_name.strip()
    return SUPPORTED_FOCUS_APPS.get(normalized.lower(), normalized or "Terminal")


def send_macos_notifications(
    *,
    artifact_dir: Path,
    execute: bool = False,
    runner: Runner | None = None,
) -> Dict[str, object]:
    plan = json.loads((artifact_dir / "macos_notification_plan.json").read_text(encoding="utf-8"))
    notifications = [
        item for item in plan.get("notifications", []) if isinstance(item, dict)
    ]
    if not execute:
        return {
            "status": "dry_run",
            "notification_request_executed": False,
            "notification_count": len(notifications),
            "plan": redact_commands(plan),
        }
    run = runner or run_command
    results = [run(list(item["command"])) for item in notifications if "command" in item]
    return {
        "status": "sent",
        "notification_request_executed": True,
        "notification_count": len(results),
        "results": results,
    }


def run_command(command: list[str]) -> Dict[str, object]:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    return {
        "command": command[:2],
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def redact_commands(plan: Dict[str, object]) -> Dict[str, object]:
    redacted = dict(plan)
    redacted["notifications"] = [
        {
            key: value
            for key, value in notification.items()
            if key not in {"command", "focus_command"}
        }
        for notification in plan.get("notifications", [])
        if isinstance(notification, dict)
    ]
    return redacted


def applescript_string(value: str) -> str:
    return json.dumps(value)
