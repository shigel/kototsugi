import json
import wave
from pathlib import Path
from unittest.mock import patch

from sokcon.cli import main

SAMPLE = """[00:00] PM: ログイン後のダッシュボードをMVPで作ります。
[00:20] Eng: 管理者権限は必要ですか？
[00:50] PM: MVPでは一般ユーザーだけでよいです。Issue化してください。
"""


def test_cli_generates_artifacts_and_returns_success(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.txt"
    transcript.write_text(SAMPLE, encoding="utf-8")
    output_dir = tmp_path / "artifacts"

    exit_code = main([str(transcript), "--out", str(output_dir), "--project", "CLI MVP"])

    assert exit_code == 0
    assert (output_dir / "requirements.md").exists()
    assert (output_dir / "evaluation.json").exists()


def test_cli_fails_when_quality_gate_is_too_high(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("[00:00] A: 雑談です。", encoding="utf-8")
    output_dir = tmp_path / "artifacts"

    exit_code = main([
        str(transcript),
        "--out",
        str(output_dir),
        "--min-quality-score",
        "1.1",
    ])

    assert exit_code == 2


def test_cli_accepts_transcript_event_jsonl(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join(
            [
                (
                    '{"type":"conversation.item.input_audio_transcription.delta",'
                    '"event_id":"evt_1","timestamp":"00:00","speaker":"PM",'
                    '"delta":"ログイン後のダッシュボードが必要かもしれません"}'
                ),
                (
                    '{"type":"conversation.item.input_audio_transcription.completed",'
                    '"event_id":"evt_2","timestamp":"00:03","speaker":"PM",'
                    '"transcript":"ログイン後のダッシュボードをMVPで作ります。"}'
                ),
                (
                    '{"kind":"final","timestamp":"00:20","speaker":"Eng",'
                    '"text":"管理者権限は必要ですか？"}'
                ),
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "artifacts"

    exit_code = main([
        str(events),
        "--input-format",
        "events",
        "--out",
        str(output_dir),
        "--project",
        "Realtime CLI MVP",
    ])

    assert exit_code == 0
    assert (output_dir / "transcript_events.json").exists()
    assert (output_dir / "partial_transcript.md").exists()
    transcript = (output_dir / "transcript.md").read_text(encoding="utf-8")
    partial = (output_dir / "partial_transcript.md").read_text(encoding="utf-8")
    assert "かもしれません" not in transcript
    assert "かもしれません" in partial


def test_cli_prints_realtime_config_without_input(capsys) -> None:
    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-secret"}, clear=True):
        exit_code = main(["--print-realtime-config"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "gpt-realtime-2" in captured.out
    assert "has_openai_api_key" in captured.out
    assert "sk-test-secret" not in captured.out


def test_cli_creates_realtime_session_dry_run_without_secret(capsys) -> None:
    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-secret"}, clear=True):
        exit_code = main(["--create-realtime-session"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"status": "dry_run"' in captured.out
    assert '"network_request_executed": false' in captured.out
    assert "sk-test-secret" not in captured.out


def test_cli_prints_slack_config_without_secret(capsys) -> None:
    with patch.dict(
        "os.environ",
        {"SOKCON_SLACK_WEBHOOK_URL": "https://hooks.slack.test/secret"},
        clear=True,
    ):
        exit_code = main(["--print-slack-config"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "has_webhook_url" in captured.out
    assert "secret" not in captured.out


def test_cli_prints_external_config_without_secrets(capsys) -> None:
    with patch.dict(
        "os.environ",
        {
            "GITHUB_TOKEN": "ghp-secret",
            "SOKCON_GITHUB_REPOSITORY": "owner/repo",
        },
        clear=True,
    ):
        exit_code = main(["--print-external-config"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "owner/repo" in captured.out
    assert "secret" not in captured.out
    assert "github" in captured.out


def test_cli_prints_diarization_config_without_secret(capsys) -> None:
    with patch.dict(
        "os.environ",
        {"SOKCON_DIARIZATION_COMMAND": "diarize --token secret"},
        clear=True,
    ):
        exit_code = main(["--print-diarization-config"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "has_external_command" in captured.out
    assert "secret" not in captured.out


def test_cli_prints_notification_config(capsys) -> None:
    with patch.dict("os.environ", {"SOKCON_NOTIFICATION_FOCUS_APP": "vscode"}, clear=True):
        exit_code = main(["--print-notification-config"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Visual Studio Code" in captured.out
    assert "supported_focus_apps" in captured.out


def test_cli_records_privacy_options(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.txt"
    transcript.write_text(SAMPLE, encoding="utf-8")
    output_dir = tmp_path / "artifacts"

    exit_code = main([
        str(transcript),
        "--out",
        str(output_dir),
        "--confidential",
        "--retention-days",
        "3",
        "--external-destination",
        "github",
        "--enable-external-registration",
    ])

    assert exit_code == 0
    privacy = (output_dir / "privacy_manifest.json").read_text(encoding="utf-8")
    assert '"confidential": true' in privacy
    assert '"retention_days": 3' in privacy
    assert '"external_destinations": []' in privacy
    assert '"external_registration_enabled": false' in privacy


def test_cli_accepts_supported_non_development_mode(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.txt"
    transcript.write_text(SAMPLE, encoding="utf-8")
    output_dir = tmp_path / "artifacts"

    exit_code = main([str(transcript), "--out", str(output_dir), "--mode", "sales"])

    assert exit_code == 0
    mode_profile = (output_dir / "mode_profile.json").read_text(encoding="utf-8")
    assert '"name": "sales"' in mode_profile


def test_cli_starts_dashboard_server_mode_without_input(tmp_path: Path) -> None:
    with patch("sokcon.cli.serve_dashboard") as serve:
        exit_code = main(["--serve-dashboard", str(tmp_path), "--port", "0"])

    assert exit_code == 0
    serve.assert_called_once()


def test_cli_prepares_audio_without_transcript_input(tmp_path: Path) -> None:
    wav_path = tmp_path / "sample.wav"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(1000)
        wav.writeframes(b"\x00\x00" * 100)
    output_dir = tmp_path / "audio"

    exit_code = main([
        "--prepare-audio",
        str(wav_path),
        "--out",
        str(output_dir),
        "--audio-chunk-ms",
        "50",
    ])

    assert exit_code == 0
    assert (output_dir / "audio_manifest.json").exists()
    assert (output_dir / "audio_chunks.json").exists()
    assert (output_dir / "realtime_send_plan.json").exists()


def test_cli_captures_audio_dry_run(tmp_path: Path, capsys) -> None:
    output = tmp_path / "meeting.wav"

    exit_code = main(
        [
            "--capture-audio",
            str(output),
            "--duration-seconds",
            "5",
            "--audio-input-device",
            "BlackHole",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"status": "dry_run"' in captured.out
    assert "BlackHole" in captured.out
    assert '"audio_capture_executed": false' in captured.out


def test_cli_streams_realtime_audio_dry_run(tmp_path: Path, capsys) -> None:
    (tmp_path / "realtime_send_plan.json").write_text(
        '{"events":[{"type":"input_audio_buffer.commit"}]}',
        encoding="utf-8",
    )

    exit_code = main(["--stream-realtime-audio", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"status": "dry_run"' in captured.out
    assert '"network_request_executed": false' in captured.out


def test_cli_runs_realtime_live_check_dry_run(tmp_path: Path, capsys) -> None:
    (tmp_path / "realtime_send_plan.json").write_text(
        '{"events":[{"type":"input_audio_buffer.commit"}]}',
        encoding="utf-8",
    )

    exit_code = main(["--run-realtime-live-check", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"status": "dry_run"' in captured.out
    assert '"network_request_executed": false' in captured.out
    assert (tmp_path / "realtime_live_check_result.json").exists()
    assert (tmp_path / "live_verification_manifest.json").exists()


def test_cli_runs_realtime_live_check_execute_records_missing_key(
    tmp_path: Path,
    capsys,
) -> None:
    (tmp_path / "realtime_send_plan.json").write_text(
        '{"events":[{"type":"input_audio_buffer.commit"}]}',
        encoding="utf-8",
    )

    with patch.dict("os.environ", {}, clear=True):
        exit_code = main(["--run-realtime-live-check", str(tmp_path), "--execute"])

    captured = capsys.readouterr()
    result = json.loads((tmp_path / "realtime_live_check_result.json").read_text())
    manifest = json.loads((tmp_path / "live_verification_manifest.json").read_text())

    assert exit_code == 0
    assert '"status": "failed"' in captured.out
    assert result["missing"] == ["OPENAI_API_KEY"]
    assert result["network_request_executed"] is False
    assert manifest["mvp_status"] == "blocked"
    assert manifest["blocked_mvp_checks"] == ["openai_realtime_api"]


def test_cli_runs_diarization_dry_run(tmp_path: Path, capsys) -> None:
    with patch.dict(
        "os.environ",
        {"SOKCON_DIARIZATION_COMMAND": "diarize --token secret"},
        clear=True,
    ):
        exit_code = main([
            "--run-diarization",
            str(tmp_path / "meeting.wav"),
            "--out",
            str(tmp_path),
        ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"status": "dry_run"' in captured.out
    assert "secret" not in captured.out


def test_cli_writes_approval_plan_without_transcript_input(tmp_path: Path) -> None:
    (tmp_path / "action_queue.json").write_text(
        '{"actions":[{"id":"action_review_issue_candidates",'
        '"type":"review_issue_candidates","status":"pending_review",'
        '"requires_human_approval":true}]}',
        encoding="utf-8",
    )
    (tmp_path / "issue_candidates.json").write_text("[]", encoding="utf-8")

    exit_code = main([
        "--approve-actions",
        str(tmp_path),
        "--approve-action-id",
        "action_review_issue_candidates",
    ])

    assert exit_code == 0
    assert (tmp_path / "approval_plan.json").exists()


def test_cli_updates_question_status_without_transcript_input(tmp_path: Path) -> None:
    (tmp_path / "questions.json").write_text(
        '[{"id":"q_1","question":"管理者権限は必要ですか？","category":"blocker","status":"open"}]',
        encoding="utf-8",
    )

    exit_code = main([
        "--update-question-status",
        str(tmp_path),
        "--question-id",
        "q_1",
        "--question-status",
        "answered",
    ])

    assert exit_code == 0
    assert (tmp_path / "question_status.json").exists()
    assert '"status": "answered"' in (tmp_path / "questions.json").read_text(encoding="utf-8")


def test_cli_updates_issue_status_without_transcript_input(tmp_path: Path) -> None:
    (tmp_path / "issue_candidates.json").write_text(
        '[{"id":"issue_1","title":"Do work","status":"candidate"}]',
        encoding="utf-8",
    )

    exit_code = main([
        "--update-issue-status",
        str(tmp_path),
        "--issue-id",
        "issue_1",
        "--issue-status",
        "approved",
    ])

    assert exit_code == 0
    assert (tmp_path / "issue_status.json").exists()
    assert '"status": "approved"' in (
        tmp_path / "issue_candidates.json"
    ).read_text(encoding="utf-8")


def test_cli_cleanup_retention_dry_run(tmp_path: Path, capsys) -> None:
    (tmp_path / "privacy_manifest.json").write_text('{"retention_days":30}', encoding="utf-8")

    exit_code = main(["--cleanup-retention", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"status": "dry_run"' in captured.out
    assert '"cleanup_executed": false' in captured.out


def test_cli_writes_live_verification_without_transcript_input(tmp_path: Path) -> None:
    exit_code = main(["--write-live-verification", str(tmp_path)])

    assert exit_code == 0
    assert (tmp_path / "live_verification_manifest.json").exists()


def test_cli_executes_approval_plan_dry_run(tmp_path: Path, capsys) -> None:
    (tmp_path / "approval_plan.json").write_text(
        '{"actions":[{"id":"action_register_issues_github",'
        '"type":"external_issue_registration","destination":"github",'
        '"ready_to_execute":true,"execution_payload":{"items":[{"title":"Do work"}]}}]}',
        encoding="utf-8",
    )

    exit_code = main(["--execute-approval-plan", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"status": "dry_run"' in captured.out
    assert '"network_request_executed": false' in captured.out


def test_cli_sends_slack_notification_dry_run(tmp_path: Path, capsys) -> None:
    (tmp_path / "slack_notification.json").write_text(
        '{"payload":{"text":"hello"}}',
        encoding="utf-8",
    )

    exit_code = main(["--send-slack-notification", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"status": "dry_run"' in captured.out
    assert '"network_request_executed": false' in captured.out


def test_cli_sends_macos_notifications_dry_run(tmp_path: Path, capsys) -> None:
    (tmp_path / "macos_notification_plan.json").write_text(
        '{"notifications":[{"kind":"meeting_ended","command":["osascript","-e","display"]}]}',
        encoding="utf-8",
    )

    exit_code = main(["--send-macos-notifications", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"status": "dry_run"' in captured.out
    assert '"notification_request_executed": false' in captured.out
