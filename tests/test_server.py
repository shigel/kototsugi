from pathlib import Path

from sokcon.server import (
    artifact_fingerprint,
    build_sse_snapshot,
    guess_content_type,
    resolve_artifact_path,
    watch_sse_events,
)


def test_guess_content_type() -> None:
    assert guess_content_type(Path("dashboard.html")) == "text/html; charset=utf-8"
    assert guess_content_type(Path("state_snapshot.json")) == "application/json"
    assert guess_content_type(Path("summary.md")) == "text/markdown; charset=utf-8"


def test_resolve_artifact_path_allows_files_under_root(tmp_path: Path) -> None:
    artifact = tmp_path / "summary.md"
    artifact.write_text("# Summary", encoding="utf-8")

    resolved = resolve_artifact_path(tmp_path, "summary.md")

    assert resolved == artifact.resolve()


def test_resolve_artifact_path_rejects_path_escape(tmp_path: Path) -> None:
    assert resolve_artifact_path(tmp_path, "../secret.txt") is None


def test_build_sse_snapshot_reads_dashboard_state(tmp_path: Path) -> None:
    (tmp_path / "state_snapshot.json").write_text('{"project_name":"SSE"}', encoding="utf-8")
    (tmp_path / "action_queue.json").write_text('{"actions":[]}', encoding="utf-8")
    (tmp_path / "requirements_traceability.json").write_text(
        '{"implemented":[],"not_implemented":[]}',
        encoding="utf-8",
    )

    event = build_sse_snapshot(tmp_path)

    assert event.startswith("event: snapshot\n")
    assert '"project_name": "SSE"' in event
    assert event.endswith("\n\n")


def test_artifact_fingerprint_tracks_watched_files(tmp_path: Path) -> None:
    first = artifact_fingerprint(tmp_path)
    (tmp_path / "state_snapshot.json").write_text('{"project_name":"SSE"}', encoding="utf-8")
    second = artifact_fingerprint(tmp_path)

    assert first["state_snapshot.json"] == 0
    assert second["state_snapshot.json"] > 0


def test_watch_sse_events_once_yields_snapshot(tmp_path: Path) -> None:
    (tmp_path / "state_snapshot.json").write_text('{"project_name":"SSE"}', encoding="utf-8")

    events = list(watch_sse_events(tmp_path, once=True, poll_interval=0))

    assert len(events) == 1
    assert events[0].startswith("event: snapshot\n")
