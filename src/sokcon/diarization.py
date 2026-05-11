from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Sequence


@dataclass(frozen=True)
class DiarizationConfig:
    provider: str = "transcript_metadata"
    command: str = ""
    min_speakers: int = 1
    max_speakers: int = 8
    quality_target: str = "high"

    @property
    def external_provider_ready(self) -> bool:
        return bool(self.command)


def load_diarization_config(env: Dict[str, str] | None = None) -> DiarizationConfig:
    values = env if env is not None else os.environ
    return DiarizationConfig(
        provider=values.get("SOKCON_DIARIZATION_PROVIDER", "transcript_metadata"),
        command=values.get("SOKCON_DIARIZATION_COMMAND", ""),
        min_speakers=int(values.get("SOKCON_DIARIZATION_MIN_SPEAKERS", "1")),
        max_speakers=int(values.get("SOKCON_DIARIZATION_MAX_SPEAKERS", "8")),
        quality_target=values.get("SOKCON_DIARIZATION_QUALITY_TARGET", "high"),
    )


def describe_diarization_config(config: DiarizationConfig) -> Dict[str, object]:
    payload = asdict(config)
    payload["has_external_command"] = config.external_provider_ready
    payload["command_redacted"] = bool(config.command)
    payload.pop("command", None)
    return payload


def build_diarization_manifest(
    *,
    config: DiarizationConfig,
    speaker_count: int,
    segments: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    return {
        "status": "ready" if speaker_count else "needs_audio_or_speaker_metadata",
        "provider": config.provider,
        "quality_target": config.quality_target,
        "external_provider_ready": config.external_provider_ready,
        "min_speakers": config.min_speakers,
        "max_speakers": config.max_speakers,
        "speaker_count": speaker_count,
        "segment_count": len(segments),
        "precision_note": (
            "High-accuracy diarization requires an external audio diarization provider; "
            "transcript speaker metadata is preserved as a fallback."
        ),
    }


def execute_diarization(
    *,
    audio_path: Path,
    output_dir: Path,
    config: DiarizationConfig,
    execute: bool = False,
    runner: object | None = None,
) -> Dict[str, object]:
    if not config.command:
        return {
            "status": "missing_external_provider",
            "diarization_executed": False,
            "audio_path": str(audio_path),
        }
    command = [
        *shlex.split(config.command),
        "--audio",
        str(audio_path),
        "--out",
        str(output_dir / "diarization_segments.json"),
        "--min-speakers",
        str(config.min_speakers),
        "--max-speakers",
        str(config.max_speakers),
    ]
    if not execute:
        return {
            "status": "dry_run",
            "diarization_executed": False,
            "command": redact_command(command),
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    run = runner if runner is not None else run_command
    result = run(command)
    return {
        "status": "completed" if result["returncode"] == 0 else "failed",
        "diarization_executed": True,
        "result": result,
    }


def run_command(command: list[str]) -> Dict[str, object]:
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def redact_command(command: list[str]) -> list[str]:
    return command[:1] + ["<args-redacted>"] if command else []


def write_diarization_artifacts(
    *,
    output_dir: Path,
    config: DiarizationConfig,
    speaker_count: int,
    segments: Sequence[Dict[str, object]],
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    segments_path = output_dir / "diarization_segments.json"
    manifest_path = output_dir / "diarization_manifest.json"
    segments_path.write_text(json.dumps(list(segments), ensure_ascii=False, indent=2) + "\n")
    manifest = build_diarization_manifest(
        config=config,
        speaker_count=speaker_count,
        segments=segments,
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return [segments_path, manifest_path]
