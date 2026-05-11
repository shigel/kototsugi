from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from sokcon.diarization import DiarizationConfig
from sokcon.integrations import ExternalRegistrationConfig, SlackConfig
from sokcon.realtime import RealtimeConfig, build_realtime_api_compatibility_report


def build_live_verification_manifest(
    *,
    artifact_dir: Path,
    realtime_config: RealtimeConfig,
    diarization_config: DiarizationConfig,
    external_config: ExternalRegistrationConfig,
    slack_config: SlackConfig,
) -> Dict[str, object]:
    has_realtime_send_plan = (artifact_dir / "realtime_send_plan.json").exists()
    has_realtime_live_check_result = (
        artifact_dir / "realtime_live_check_result.json"
    ).exists()
    live_check_result = load_realtime_live_check_result(artifact_dir)
    live_check_ready = (
        bool(live_check_result)
        and live_check_result.get("status") == "completed"
        and live_check_result.get("network_request_executed") is True
    )
    checks = [
        {
            "id": "openai_realtime_api",
            "required_for_mvp": True,
            "ready": realtime_config.has_api_key and has_realtime_send_plan and live_check_ready,
            "execute_command": "--run-realtime-live-check --execute",
            "missing": missing(
                {
                    "OPENAI_API_KEY": realtime_config.has_api_key,
                    "realtime_send_plan.json": has_realtime_send_plan,
                    "realtime_live_check_result.json": has_realtime_live_check_result,
                }
            ),
            "unverified": []
            if live_check_ready
            else ["realtime_live_check_completed_network_execution"],
            "live_check_result": live_check_result,
            "compatibility": build_realtime_api_compatibility_report(realtime_config),
        },
        {
            "id": "external_diarization_provider",
            "required_for_mvp": False,
            "ready": diarization_config.external_provider_ready,
            "execute_command": "--run-diarization",
            "missing": missing({
                "SOKCON_DIARIZATION_COMMAND": diarization_config.external_provider_ready
            }),
        },
        {
            "id": "slack_webhook",
            "required_for_mvp": False,
            "ready": slack_config.has_webhook_url,
            "execute_command": "--send-slack-notification",
            "missing": missing({"SOKCON_SLACK_WEBHOOK_URL": slack_config.has_webhook_url}),
        },
        {
            "id": "external_registration_targets",
            "required_for_mvp": False,
            "ready": any(external_readiness(external_config).values()),
            "execute_command": "--execute-approval-plan",
            "targets": external_readiness(external_config),
            "missing": [
                name for name, ready in external_readiness(external_config).items() if not ready
            ],
        },
    ]
    return {
        "status": "ready" if all(check["ready"] for check in checks) else "blocked",
        "mvp_status": "ready"
        if all(check["ready"] for check in checks if check["required_for_mvp"])
        else "blocked",
        "artifact_dir": str(artifact_dir),
        "checks": checks,
        "blocked_checks": [check["id"] for check in checks if not check["ready"]],
        "blocked_mvp_checks": [
            check["id"]
            for check in checks
            if check["required_for_mvp"] and not check["ready"]
        ],
        "blocked_post_mvp_checks": [
            check["id"]
            for check in checks
            if not check["required_for_mvp"] and not check["ready"]
        ],
    }


def write_live_verification_manifest(
    *,
    artifact_dir: Path,
    realtime_config: RealtimeConfig,
    diarization_config: DiarizationConfig,
    external_config: ExternalRegistrationConfig,
    slack_config: SlackConfig,
) -> Path:
    manifest = build_live_verification_manifest(
        artifact_dir=artifact_dir,
        realtime_config=realtime_config,
        diarization_config=diarization_config,
        external_config=external_config,
        slack_config=slack_config,
    )
    output = artifact_dir / "live_verification_manifest.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def external_readiness(config: ExternalRegistrationConfig) -> Dict[str, bool]:
    return {
        "github": config.github_ready,
        "linear": config.linear_ready,
        "notion": config.notion_ready,
        "google_docs": config.google_docs_ready,
        "google_slides": config.google_slides_ready,
        "crm": config.crm_ready,
        "ats": config.ats_ready,
    }


def load_realtime_live_check_result(artifact_dir: Path) -> Dict[str, object]:
    path = artifact_dir / "realtime_live_check_result.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def missing(values: Dict[str, bool]) -> list[str]:
    return [name for name, ready in values.items() if not ready]
