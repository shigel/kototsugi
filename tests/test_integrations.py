from unittest.mock import patch

from sokcon.integrations import (
    describe_external_registration_config,
    describe_slack_config,
    load_external_registration_config,
    load_slack_config,
    post_external_registration,
    send_slack_notification,
)


def test_describe_slack_config_redacts_webhook_url() -> None:
    config = load_slack_config(
        {
            "SOKCON_SLACK_WEBHOOK_URL": "https://hooks.slack.test/secret",
            "SOKCON_SLACK_CHANNEL": "#dev",
        }
    )

    description = describe_slack_config(config)

    assert description["has_webhook_url"] is True
    assert description["send_supported"] is True
    assert description["channel"] == "#dev"
    assert "secret" not in str(description)
    assert "webhook_url" not in description


def test_describe_external_registration_config_redacts_credentials() -> None:
    config = load_external_registration_config(
        {
            "GITHUB_TOKEN": "ghp-secret",
            "SOKCON_GITHUB_REPOSITORY": "owner/repo",
            "LINEAR_API_KEY": "lin-secret",
            "SOKCON_LINEAR_TEAM_KEY": "ENG",
            "NOTION_TOKEN": "notion-secret",
            "SOKCON_NOTION_DATABASE_ID": "db123",
            "GOOGLE_API_TOKEN": "google-secret",
            "SOKCON_GOOGLE_DOCS_FOLDER_ID": "docs-folder",
            "SOKCON_GOOGLE_SLIDES_FOLDER_ID": "slides-folder",
            "SOKCON_CRM_API_KEY": "crm-secret",
            "SOKCON_CRM_ENDPOINT": "https://crm.example.test",
            "SOKCON_ATS_API_KEY": "ats-secret",
            "SOKCON_ATS_ENDPOINT": "https://ats.example.test",
        }
    )

    description = describe_external_registration_config(config)

    assert description["github"]["ready"] is True
    assert description["linear"]["ready"] is True
    assert description["notion"]["ready"] is True
    assert description["google_docs"]["ready"] is True
    assert description["google_slides"]["ready"] is True
    assert description["crm"]["ready"] is True
    assert description["ats"]["ready"] is True
    assert "secret" not in str(description)
    assert description["credential_redacted"] is True


def test_send_slack_notification_dry_run_does_not_execute_network(tmp_path) -> None:
    (tmp_path / "slack_notification.json").write_text(
        '{"payload":{"text":"hello"}}',
        encoding="utf-8",
    )
    config = load_slack_config({"SOKCON_SLACK_WEBHOOK_URL": "https://hooks/secret"})

    result = send_slack_notification(artifact_dir=tmp_path, config=config)

    assert result["status"] == "dry_run"
    assert result["network_request_executed"] is False
    assert result["payload"] == {"text": "hello"}
    assert "secret" not in str(result)


def test_send_slack_notification_execute_uses_injected_sender(tmp_path) -> None:
    (tmp_path / "slack_notification.json").write_text(
        '{"payload":{"text":"hello"}}',
        encoding="utf-8",
    )
    config = load_slack_config({"SOKCON_SLACK_WEBHOOK_URL": "https://hooks/secret"})
    calls = []

    def fake_sender(webhook_url, payload):
        calls.append((webhook_url, payload))
        return {"status_code": 200}

    result = send_slack_notification(
        artifact_dir=tmp_path,
        config=config,
        execute=True,
        post_json=fake_sender,
    )

    assert result["status"] == "sent"
    assert result["network_request_executed"] is True
    assert calls == [("https://hooks/secret", {"text": "hello"})]


def test_post_external_registration_requires_destination_config() -> None:
    config = load_external_registration_config({})

    try:
        post_external_registration("github", {"title": "Do work"}, config)
    except ValueError as error:
        assert "GITHUB_TOKEN" in str(error)
    else:
        raise AssertionError("missing GitHub config should fail")


def test_post_external_registration_supports_named_destinations() -> None:
    config = load_external_registration_config(
        {
            "GITHUB_TOKEN": "ghp-secret",
            "SOKCON_GITHUB_REPOSITORY": "owner/repo",
            "LINEAR_API_KEY": "linear-secret",
            "SOKCON_LINEAR_TEAM_KEY": "team-id",
            "NOTION_TOKEN": "notion-secret",
            "SOKCON_NOTION_DATABASE_ID": "db-id",
            "GOOGLE_API_TOKEN": "google-secret",
            "SOKCON_GOOGLE_DOCS_FOLDER_ID": "docs-folder",
            "SOKCON_GOOGLE_SLIDES_FOLDER_ID": "slides-folder",
            "SOKCON_CRM_API_KEY": "crm-secret",
            "SOKCON_CRM_ENDPOINT": "https://crm.example.test",
            "SOKCON_ATS_API_KEY": "ats-secret",
            "SOKCON_ATS_ENDPOINT": "https://ats.example.test",
        }
    )
    destinations = ["github", "linear", "notion", "google_docs", "google_slides", "crm", "ats"]

    with patch("sokcon.integrations.post_json_with_bearer") as sender:
        sender.return_value = {"status_code": 200}
        for destination in destinations:
            post_external_registration(
                destination,
                {"title": "Do work", "name": "Do work"},
                config,
            )

    assert sender.call_count == len(destinations)
