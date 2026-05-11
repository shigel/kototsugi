import os
from pathlib import Path

from sokcon.retention import build_retention_policy, cleanup_retention


def test_build_retention_policy_records_cleanup_command() -> None:
    policy = build_retention_policy(retention_days=7, confidential=True)

    assert policy["delete_after_days"] == 7
    assert policy["confidential"] is True
    assert policy["cleanup_command"] == "--cleanup-retention"


def test_cleanup_retention_dry_run_lists_expired_files(tmp_path: Path) -> None:
    (tmp_path / "privacy_manifest.json").write_text('{"retention_days":1}', encoding="utf-8")
    old_file = tmp_path / "old.txt"
    old_file.write_text("old", encoding="utf-8")
    old_mtime = 1_000_000
    os.utime(old_file, (old_mtime, old_mtime))

    result = cleanup_retention(artifact_dir=tmp_path, now=old_mtime + 3 * 24 * 60 * 60)

    assert result["status"] == "dry_run"
    assert result["cleanup_executed"] is False
    assert result["candidate_count"] == 1
    assert old_file.exists()


def test_cleanup_retention_execute_deletes_expired_files(tmp_path: Path) -> None:
    (tmp_path / "privacy_manifest.json").write_text('{"retention_days":1}', encoding="utf-8")
    old_file = tmp_path / "old.txt"
    old_file.write_text("old", encoding="utf-8")
    old_mtime = 1_000_000
    os.utime(old_file, (old_mtime, old_mtime))

    result = cleanup_retention(
        artifact_dir=tmp_path,
        execute=True,
        now=old_mtime + 3 * 24 * 60 * 60,
    )

    assert result["status"] == "deleted"
    assert result["deleted_count"] == 1
    assert not old_file.exists()
    assert (tmp_path / "privacy_manifest.json").exists()
