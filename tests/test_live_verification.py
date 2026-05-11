from pathlib import Path

from sokcon.diarization import load_diarization_config
from sokcon.integrations import load_external_registration_config, load_slack_config
from sokcon.live_verification import (
    build_live_verification_manifest,
    write_live_verification_manifest,
)
from sokcon.realtime import load_realtime_config


def test_build_live_verification_manifest_reports_blockers(tmp_path: Path) -> None:
    manifest = build_live_verification_manifest(
        artifact_dir=tmp_path,
        realtime_config=load_realtime_config({}),
        diarization_config=load_diarization_config({}),
        external_config=load_external_registration_config({}),
        slack_config=load_slack_config({}),
    )

    assert manifest["status"] == "blocked"
    assert manifest["mvp_status"] == "blocked"
    assert "openai_realtime_api" in manifest["blocked_checks"]
    assert manifest["blocked_mvp_checks"] == ["openai_realtime_api"]
    assert "external_diarization_provider" in manifest["blocked_checks"]


def test_build_live_verification_manifest_reports_ready_components(tmp_path: Path) -> None:
    (tmp_path / "realtime_send_plan.json").write_text('{"events":[]}', encoding="utf-8")
    (tmp_path / "realtime_live_check_result.json").write_text(
        '{"status":"completed","network_request_executed":true}',
        encoding="utf-8",
    )

    manifest = build_live_verification_manifest(
        artifact_dir=tmp_path,
        realtime_config=load_realtime_config({"OPENAI_API_KEY": "sk-test-secret"}),
        diarization_config=load_diarization_config({"SOKCON_DIARIZATION_COMMAND": "diarize"}),
        external_config=load_external_registration_config({
            "GITHUB_TOKEN": "ghp-secret",
            "SOKCON_GITHUB_REPOSITORY": "owner/repo",
        }),
        slack_config=load_slack_config({
            "SOKCON_SLACK_WEBHOOK_URL": "https://hooks.example.test/secret"
        }),
    )

    assert manifest["status"] == "ready"
    assert manifest["mvp_status"] == "ready"
    assert manifest["blocked_checks"] == []


def test_build_live_verification_manifest_requires_executed_live_check(
    tmp_path: Path,
) -> None:
    (tmp_path / "realtime_send_plan.json").write_text('{"events":[]}', encoding="utf-8")
    (tmp_path / "realtime_live_check_result.json").write_text(
        '{"status":"dry_run","network_request_executed":false}',
        encoding="utf-8",
    )

    manifest = build_live_verification_manifest(
        artifact_dir=tmp_path,
        realtime_config=load_realtime_config({"OPENAI_API_KEY": "sk-test-secret"}),
        diarization_config=load_diarization_config({}),
        external_config=load_external_registration_config({}),
        slack_config=load_slack_config({}),
    )

    openai_check = next(
        check for check in manifest["checks"] if check["id"] == "openai_realtime_api"
    )
    assert manifest["mvp_status"] == "blocked"
    assert "openai_realtime_api" in manifest["blocked_mvp_checks"]
    assert openai_check["missing"] == []
    assert "realtime_live_check_completed_network_execution" in openai_check["unverified"]


def test_write_live_verification_manifest(tmp_path: Path) -> None:
    output = write_live_verification_manifest(
        artifact_dir=tmp_path,
        realtime_config=load_realtime_config({}),
        diarization_config=load_diarization_config({}),
        external_config=load_external_registration_config({}),
        slack_config=load_slack_config({}),
    )

    assert output == tmp_path / "live_verification_manifest.json"
    assert output.exists()
