from pathlib import Path

from sokcon.diarization import (
    build_diarization_manifest,
    describe_diarization_config,
    execute_diarization,
    load_diarization_config,
)


def test_describe_diarization_config_redacts_command() -> None:
    config = load_diarization_config({
        "SOKCON_DIARIZATION_PROVIDER": "pyannote",
        "SOKCON_DIARIZATION_COMMAND": "diarize --token secret",
        "SOKCON_DIARIZATION_MIN_SPEAKERS": "2",
        "SOKCON_DIARIZATION_MAX_SPEAKERS": "6",
    })

    description = describe_diarization_config(config)

    assert description["provider"] == "pyannote"
    assert description["has_external_command"] is True
    assert description["command_redacted"] is True
    assert "secret" not in str(description)


def test_build_diarization_manifest_records_quality_target() -> None:
    config = load_diarization_config({"SOKCON_DIARIZATION_QUALITY_TARGET": "high"})

    manifest = build_diarization_manifest(
        config=config,
        speaker_count=2,
        segments=[{"speaker": "PM"}, {"speaker": "Eng"}],
    )

    assert manifest["status"] == "ready"
    assert manifest["quality_target"] == "high"
    assert manifest["segment_count"] == 2


def test_execute_diarization_dry_run_redacts_external_command(tmp_path: Path) -> None:
    config = load_diarization_config({
        "SOKCON_DIARIZATION_COMMAND": "diarize --token secret",
    })

    result = execute_diarization(
        audio_path=tmp_path / "meeting.wav",
        output_dir=tmp_path / "out",
        config=config,
    )

    assert result["status"] == "dry_run"
    assert result["diarization_executed"] is False
    assert "secret" not in str(result)


def test_execute_diarization_uses_injected_runner(tmp_path: Path) -> None:
    config = load_diarization_config({"SOKCON_DIARIZATION_COMMAND": "diarize"})
    calls = []

    def fake_runner(command):
        calls.append(command)
        return {"returncode": 0, "stdout": "", "stderr": ""}

    result = execute_diarization(
        audio_path=tmp_path / "meeting.wav",
        output_dir=tmp_path / "out",
        config=config,
        execute=True,
        runner=fake_runner,
    )

    assert result["status"] == "completed"
    assert result["diarization_executed"] is True
    assert calls[0][0] == "diarize"
