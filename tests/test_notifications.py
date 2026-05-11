from pathlib import Path

from sokcon.notifications import (
    build_focus_command,
    build_macos_notification_plan,
    describe_notification_config,
    load_notification_config,
    send_macos_notifications,
)


def test_build_macos_notification_plan_includes_blockers_and_focus_route() -> None:
    plan = build_macos_notification_plan(
        project_name="Dashboard MVP",
        questions=[
            {
                "id": "q_1",
                "category": "blocker",
                "question": "管理者権限は必要ですか？",
            }
        ],
        action_queue={
            "actions": [
                {
                    "id": "action_review_issue_candidates",
                    "requires_human_approval": True,
                    "status": "pending_review",
                }
            ]
        },
    )

    assert plan["platform"] == "macos"
    assert plan["click_focus_route"]["command"][0] == "osascript"
    assert [item["kind"] for item in plan["notifications"]] == [
        "blocker_question",
        "meeting_ended",
        "approval_waiting",
    ]
    assert all(item["command"][0] == "osascript" for item in plan["notifications"])


def test_notification_config_supports_terminal_iterm_and_vscode_focus_targets() -> None:
    iterm = load_notification_config({"SOKCON_NOTIFICATION_FOCUS_APP": "iterm2"})
    vscode = load_notification_config({"SOKCON_NOTIFICATION_FOCUS_APP": "vscode"})

    assert iterm.focus_app == "iTerm"
    assert vscode.focus_app == "Visual Studio Code"
    assert "iTerm" in describe_notification_config(iterm)["supported_focus_apps"]
    assert build_focus_command("VS Code") == [
        "osascript",
        "-e",
        'tell application "Visual Studio Code" to activate',
    ]


def test_send_macos_notifications_dry_run_does_not_execute(tmp_path: Path) -> None:
    (tmp_path / "macos_notification_plan.json").write_text(
        '{"notifications":[{"kind":"meeting_ended","command":["osascript","-e","display"]}]}',
        encoding="utf-8",
    )

    result = send_macos_notifications(artifact_dir=tmp_path)

    assert result["status"] == "dry_run"
    assert result["notification_request_executed"] is False
    assert result["notification_count"] == 1
    assert "command" not in str(result["plan"])


def test_send_macos_notifications_execute_uses_injected_runner(tmp_path: Path) -> None:
    (tmp_path / "macos_notification_plan.json").write_text(
        '{"notifications":[{"kind":"meeting_ended","command":["osascript","-e","display"]}]}',
        encoding="utf-8",
    )
    calls = []

    def fake_runner(command):
        calls.append(command)
        return {"returncode": 0}

    result = send_macos_notifications(
        artifact_dir=tmp_path,
        execute=True,
        runner=fake_runner,
    )

    assert result["status"] == "sent"
    assert result["notification_request_executed"] is True
    assert calls == [["osascript", "-e", "display"]]


def test_send_macos_notifications_execute_honors_disabled_plan(tmp_path: Path) -> None:
    (tmp_path / "macos_notification_plan.json").write_text(
        (
            '{"enabled":false,'
            '"notifications":[{"kind":"meeting_ended","command":["osascript","-e","display"]}]}'
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_runner(command):
        calls.append(command)
        return {"returncode": 0}

    result = send_macos_notifications(
        artifact_dir=tmp_path,
        execute=True,
        runner=fake_runner,
    )

    assert result["status"] == "disabled"
    assert result["notification_request_executed"] is False
    assert result["notification_count"] == 1
    assert calls == []
