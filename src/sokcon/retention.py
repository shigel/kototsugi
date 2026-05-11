from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict


def build_retention_policy(
    *,
    retention_days: int,
    confidential: bool,
) -> Dict[str, object]:
    return {
        "retention_days": retention_days,
        "confidential": confidential,
        "delete_after_days": retention_days,
        "cleanup_command": "--cleanup-retention",
        "dry_run_default": True,
        "scope": "artifact_directory",
    }


def cleanup_retention(
    *,
    artifact_dir: Path,
    execute: bool = False,
    now: float | None = None,
) -> Dict[str, object]:
    manifest_path = artifact_dir / "privacy_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    retention_days = int(manifest.get("retention_days", 30))
    cutoff = (now if now is not None else time.time()) - retention_days * 24 * 60 * 60
    candidates = []
    for path in sorted(artifact_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "privacy_manifest.json":
            continue
        stat = path.stat()
        if stat.st_mtime < cutoff:
            candidates.append(path)
    deleted = []
    if execute:
        for path in candidates:
            path.unlink()
            deleted.append(str(path))
    return {
        "status": "deleted" if execute else "dry_run",
        "retention_days": retention_days,
        "cleanup_executed": execute,
        "candidate_count": len(candidates),
        "deleted_count": len(deleted),
        "candidates": [str(path) for path in candidates],
        "deleted": deleted,
    }
