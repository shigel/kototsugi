from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict


@dataclass(frozen=True)
class SlackConfig:
    webhook_url: str = ""
    channel: str = ""

    @property
    def has_webhook_url(self) -> bool:
        return bool(self.webhook_url)


@dataclass(frozen=True)
class ExternalRegistrationConfig:
    github_token: str = ""
    github_repository: str = ""
    linear_api_key: str = ""
    linear_team_key: str = ""
    notion_token: str = ""
    notion_database_id: str = ""
    google_api_token: str = ""
    google_docs_folder_id: str = ""
    google_slides_folder_id: str = ""
    crm_api_key: str = ""
    crm_endpoint: str = ""
    ats_api_key: str = ""
    ats_endpoint: str = ""

    @property
    def github_ready(self) -> bool:
        return bool(self.github_token and self.github_repository)

    @property
    def linear_ready(self) -> bool:
        return bool(self.linear_api_key and self.linear_team_key)

    @property
    def notion_ready(self) -> bool:
        return bool(self.notion_token and self.notion_database_id)

    @property
    def google_docs_ready(self) -> bool:
        return bool(self.google_api_token and self.google_docs_folder_id)

    @property
    def google_slides_ready(self) -> bool:
        return bool(self.google_api_token and self.google_slides_folder_id)

    @property
    def crm_ready(self) -> bool:
        return bool(self.crm_api_key and self.crm_endpoint)

    @property
    def ats_ready(self) -> bool:
        return bool(self.ats_api_key and self.ats_endpoint)


def load_slack_config(env: Dict[str, str] | None = None) -> SlackConfig:
    values = env if env is not None else os.environ
    return SlackConfig(
        webhook_url=values.get("SOKCON_SLACK_WEBHOOK_URL", ""),
        channel=values.get("SOKCON_SLACK_CHANNEL", ""),
    )


def load_external_registration_config(
    env: Dict[str, str] | None = None,
) -> ExternalRegistrationConfig:
    values = env if env is not None else os.environ
    return ExternalRegistrationConfig(
        github_token=values.get("GITHUB_TOKEN", ""),
        github_repository=values.get("SOKCON_GITHUB_REPOSITORY", ""),
        linear_api_key=values.get("LINEAR_API_KEY", ""),
        linear_team_key=values.get("SOKCON_LINEAR_TEAM_KEY", ""),
        notion_token=values.get("NOTION_TOKEN", ""),
        notion_database_id=values.get("SOKCON_NOTION_DATABASE_ID", ""),
        google_api_token=values.get("GOOGLE_API_TOKEN", ""),
        google_docs_folder_id=values.get("SOKCON_GOOGLE_DOCS_FOLDER_ID", ""),
        google_slides_folder_id=values.get("SOKCON_GOOGLE_SLIDES_FOLDER_ID", ""),
        crm_api_key=values.get("SOKCON_CRM_API_KEY", ""),
        crm_endpoint=values.get("SOKCON_CRM_ENDPOINT", ""),
        ats_api_key=values.get("SOKCON_ATS_API_KEY", ""),
        ats_endpoint=values.get("SOKCON_ATS_ENDPOINT", ""),
    )


def describe_slack_config(config: SlackConfig) -> Dict[str, object]:
    payload = asdict(config)
    payload.pop("webhook_url", None)
    return {
        **payload,
        "has_webhook_url": config.has_webhook_url,
        "send_supported": config.has_webhook_url,
        "credential_redacted": True,
    }


def describe_external_registration_config(
    config: ExternalRegistrationConfig,
) -> Dict[str, object]:
    return {
        "github": {
            "has_token": bool(config.github_token),
            "repository": config.github_repository,
            "ready": config.github_ready,
        },
        "linear": {
            "has_api_key": bool(config.linear_api_key),
            "team_key": config.linear_team_key,
            "ready": config.linear_ready,
        },
        "notion": {
            "has_token": bool(config.notion_token),
            "database_id": config.notion_database_id,
            "ready": config.notion_ready,
        },
        "google_docs": {
            "has_token": bool(config.google_api_token),
            "folder_id": config.google_docs_folder_id,
            "ready": config.google_docs_ready,
        },
        "google_slides": {
            "has_token": bool(config.google_api_token),
            "folder_id": config.google_slides_folder_id,
            "ready": config.google_slides_ready,
        },
        "crm": {
            "has_api_key": bool(config.crm_api_key),
            "endpoint": config.crm_endpoint,
            "ready": config.crm_ready,
        },
        "ats": {
            "has_api_key": bool(config.ats_api_key),
            "endpoint": config.ats_endpoint,
            "ready": config.ats_ready,
        },
        "credential_redacted": True,
    }


def send_slack_notification(
    *,
    artifact_dir: Path,
    config: SlackConfig,
    execute: bool = False,
    post_json: object | None = None,
) -> Dict[str, object]:
    draft = json.loads((artifact_dir / "slack_notification.json").read_text(encoding="utf-8"))
    payload = draft.get("payload", {})
    if not execute:
        return {
            "status": "dry_run",
            "network_request_executed": False,
            "payload": payload,
            "has_webhook_url": config.has_webhook_url,
        }
    if not config.webhook_url:
        raise ValueError("SOKCON_SLACK_WEBHOOK_URL is required when execute=True")
    sender = post_json if post_json is not None else post_slack_webhook
    response = sender(config.webhook_url, payload)
    return {
        "status": "sent",
        "network_request_executed": True,
        "response": response,
    }


def post_slack_webhook(webhook_url: str, payload: object) -> Dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return {"status_code": response.status, "body": response.read().decode("utf-8")}
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8")
        raise RuntimeError(f"Slack webhook request failed: {error.code} {message}") from error


def post_external_registration(
    destination: str,
    payload: Dict[str, object],
    config: ExternalRegistrationConfig,
) -> Dict[str, object]:
    if destination == "github":
        if not config.github_ready:
            raise ValueError("GITHUB_TOKEN and SOKCON_GITHUB_REPOSITORY are required")
        url = f"https://api.github.com/repos/{config.github_repository}/issues"
        return post_json_with_bearer(url, config.github_token, payload)
    if destination == "linear":
        if not config.linear_ready:
            raise ValueError("LINEAR_API_KEY and SOKCON_LINEAR_TEAM_KEY are required")
        body = {
            "query": (
                "mutation IssueCreate($input: IssueCreateInput!) { "
                "issueCreate(input: $input) { success issue { id identifier } } }"
            ),
            "variables": {
                "input": {
                    "teamId": config.linear_team_key,
                    "title": payload.get("title", ""),
                    "description": payload.get("description", ""),
                }
            },
        }
        return post_json_with_bearer("https://api.linear.app/graphql", config.linear_api_key, body)
    if destination == "notion":
        if not config.notion_ready:
            raise ValueError("NOTION_TOKEN and SOKCON_NOTION_DATABASE_ID are required")
        body = {
            "parent": {"database_id": config.notion_database_id},
            "properties": {
                "Name": {"title": [{"text": {"content": str(payload.get("name", ""))}}]},
            },
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {"type": "text", "text": {"content": str(payload.get("content", ""))}}
                        ]
                    },
                }
            ],
        }
        return post_json_with_bearer(
            "https://api.notion.com/v1/pages",
            config.notion_token,
            body,
            extra_headers={"Notion-Version": "2022-06-28"},
        )
    if destination == "google_docs":
        if not config.google_docs_ready:
            raise ValueError("GOOGLE_API_TOKEN and SOKCON_GOOGLE_DOCS_FOLDER_ID are required")
        body = {
            "name": str(payload.get("title", "")),
            "mimeType": "application/vnd.google-apps.document",
            "parents": [config.google_docs_folder_id],
            "description": str(payload.get("document_body", "")),
        }
        return post_json_with_bearer(
            "https://www.googleapis.com/drive/v3/files",
            config.google_api_token,
            body,
        )
    if destination == "google_slides":
        if not config.google_slides_ready:
            raise ValueError(
                "GOOGLE_API_TOKEN and SOKCON_GOOGLE_SLIDES_FOLDER_ID are required"
            )
        body = {
            "name": str(payload.get("title", "")),
            "mimeType": "application/vnd.google-apps.presentation",
            "parents": [config.google_slides_folder_id],
            "description": json.dumps(payload.get("slides", []), ensure_ascii=False),
        }
        return post_json_with_bearer(
            "https://www.googleapis.com/drive/v3/files",
            config.google_api_token,
            body,
        )
    if destination == "crm":
        if not config.crm_ready:
            raise ValueError("SOKCON_CRM_API_KEY and SOKCON_CRM_ENDPOINT are required")
        return post_json_with_bearer(config.crm_endpoint, config.crm_api_key, payload)
    if destination == "ats":
        if not config.ats_ready:
            raise ValueError("SOKCON_ATS_API_KEY and SOKCON_ATS_ENDPOINT are required")
        return post_json_with_bearer(config.ats_endpoint, config.ats_api_key, payload)
    raise ValueError(f"Unsupported external registration destination: {destination}")


def post_json_with_bearer(
    url: str,
    token: str,
    payload: Dict[str, object],
    extra_headers: Dict[str, str] | None = None,
) -> Dict[str, object]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        **(extra_headers or {}),
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return {"status_code": response.status, "body": json.loads(raw) if raw else {}}
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8")
        raise RuntimeError(f"External registration failed: {error.code} {message}") from error
