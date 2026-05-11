import json
import wave
from pathlib import Path

from sokcon.realtime import (
    audio_format_payload,
    build_audio_capture_command,
    build_audio_input_manifest,
    build_realtime_api_compatibility_report,
    build_realtime_route_plan,
    build_realtime_send_plan,
    build_realtime_session_payload,
    build_websocket_frame,
    capture_audio,
    create_realtime_session,
    describe_realtime_config,
    load_realtime_config,
    prepare_wav_audio,
    realtime_model_for_route,
    run_realtime_live_check,
    stream_realtime_audio,
    websocket_accept_key,
)


def test_load_realtime_config_uses_env_without_exposing_secret() -> None:
    config = load_realtime_config(
        {
            "OPENAI_API_KEY": "sk-test-secret",
            "SOKCON_REALTIME_MODEL": "gpt-realtime-2",
            "SOKCON_TRANSCRIPTION_REALTIME_MODEL": "gpt-realtime-whisper",
            "SOKCON_TRANSLATION_REALTIME_MODEL": "gpt-realtime-translate",
            "SOKCON_TRANSCRIPTION_MODEL": "gpt-4o-transcribe",
            "SOKCON_REALTIME_ROUTE": "primary",
            "SOKCON_TRANSLATION_TARGET_LANGUAGE": "en",
            "SOKCON_AUDIO_INPUT_DEVICE": "BlackHole",
            "SOKCON_ENABLE_EXTERNAL_REGISTRATION": "1",
        }
    )

    description = describe_realtime_config(config)

    assert description["has_openai_api_key"] is True
    assert "sk-test-secret" not in str(description)
    assert description["external_registration_enabled"] is True
    assert description["realtime_model"] == "gpt-realtime-2"
    assert description["transcription_realtime_model"] == "gpt-realtime-whisper"
    assert description["translation_realtime_model"] == "gpt-realtime-translate"
    assert description["translation_target_language"] == "en"
    assert description["audio_input_device"] == "BlackHole"
    assert description["audio_input_manifest"]["recommended_virtual_device"] == "BlackHole"


def test_build_realtime_session_payload_requests_transcription() -> None:
    config = load_realtime_config({})

    payload = build_realtime_session_payload(config)

    assert payload["model"] == "gpt-realtime-2"
    assert payload["type"] == "realtime"
    assert payload["output_modalities"] == ["audio", "text"]
    assert payload["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert payload["audio"]["input"]["transcription"] == {"model": "gpt-4o-transcribe"}


def test_audio_format_payload_maps_current_realtime_formats() -> None:
    assert audio_format_payload("pcm16") == {"type": "audio/pcm", "rate": 24000}
    assert audio_format_payload("pcmu") == {"type": "audio/pcmu"}
    assert audio_format_payload("pcma") == {"type": "audio/pcma"}


def test_build_realtime_route_plan_supports_whisper_and_translate_candidates() -> None:
    config = load_realtime_config({})

    plan = build_realtime_route_plan(config)

    assert plan["routes"]["primary"]["model"] == "gpt-realtime-2"
    assert plan["routes"]["transcription"]["model"] == "gpt-realtime-whisper"
    assert plan["routes"]["translation"]["model"] == "gpt-realtime-translate"
    assert plan["post_mvp_candidates"] == ["transcription", "translation"]


def test_realtime_route_can_select_translation_payload() -> None:
    config = load_realtime_config({
        "SOKCON_REALTIME_ROUTE": "translation",
        "SOKCON_TRANSLATION_TARGET_LANGUAGE": "en",
    })

    payload = build_realtime_session_payload(config)

    assert payload["model"] == "gpt-realtime-translate"
    assert payload["route"] == "translation"
    assert payload["type"] == "realtime"
    assert "en" in str(payload["instructions"])
    assert realtime_model_for_route(config, "transcription") == "gpt-realtime-whisper"


def test_transcription_route_uses_transcription_session_shape() -> None:
    config = load_realtime_config({"SOKCON_REALTIME_ROUTE": "transcription"})

    payload = build_realtime_session_payload(config)

    assert payload["type"] == "transcription"
    assert payload["route"] == "transcription"
    assert payload["audio"]["input"]["transcription"]["model"] == "gpt-4o-transcribe"
    assert payload["include"] == ["item.input_audio_transcription.logprobs"]


def test_realtime_api_compatibility_report_detects_current_session_shape() -> None:
    config = load_realtime_config({"OPENAI_API_KEY": "sk-test-secret"})

    report = build_realtime_api_compatibility_report(config)

    assert report["status"] == "ready_for_live_check"
    assert report["session_shape"]["has_type"] is True
    assert report["session_shape"]["has_audio_object"] is True
    assert report["session_shape"]["uses_legacy_modalities_field"] is False
    assert "conversation.item.input_audio_transcription.delta" in report["transcription_events"]


def test_prepare_wav_audio_writes_manifest_and_chunks(tmp_path: Path) -> None:
    wav_path = tmp_path / "sample.wav"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(1000)
        wav.writeframes(b"\x00\x00" * 250)

    result = prepare_wav_audio(input_path=wav_path, output_dir=tmp_path / "out", chunk_ms=100)

    manifest = result["manifest"]
    assert manifest["sample_rate_hz"] == 1000
    assert manifest["realtime_recommended_sample_rate_hz"] == 24000
    assert manifest["realtime_sample_rate_ready"] is False
    assert manifest["duration_ms"] == 250
    assert manifest["chunk_count"] == 3
    manifest_file = tmp_path / "out" / "audio_manifest.json"
    chunks_file = tmp_path / "out" / "audio_chunks.json"
    send_plan_file = tmp_path / "out" / "realtime_send_plan.json"
    assert manifest_file.exists()
    assert chunks_file.exists()
    assert send_plan_file.exists()
    chunks = json.loads(chunks_file.read_text(encoding="utf-8"))
    assert chunks[0]["encoding"] == "base64_pcm16"
    assert chunks[0]["audio"]
    send_plan = json.loads(send_plan_file.read_text(encoding="utf-8"))
    assert send_plan["network_send_enabled"] is False
    assert send_plan["events"][-1] == {"type": "input_audio_buffer.commit"}


def test_capture_audio_dry_run_builds_afrecord_command(tmp_path: Path) -> None:
    output = tmp_path / "meeting.wav"

    result = capture_audio(
        output_path=output,
        duration_seconds=5,
        audio_input_device="BlackHole",
    )

    assert result["status"] == "dry_run"
    assert result["audio_capture_executed"] is False
    assert result["command"] == [
        "afrecord",
        "-f",
        "WAVE",
        "-d",
        "5",
        "-i",
        "BlackHole",
        str(output),
    ]
    assert result["audio_input_manifest"]["configured_audio_input_device"] == "BlackHole"


def test_capture_audio_execute_uses_runner(tmp_path: Path) -> None:
    output = tmp_path / "meeting.wav"
    calls = []

    def fake_runner(command):
        calls.append(command)
        return {"returncode": 0, "stdout": "", "stderr": ""}

    result = capture_audio(
        output_path=output,
        duration_seconds=5,
        execute=True,
        runner=fake_runner,
    )

    assert result["status"] == "captured"
    assert result["audio_capture_executed"] is True
    assert calls == [["afrecord", "-f", "WAVE", "-d", "5", str(output)]]
    assert (tmp_path / "audio_input_manifest.json").exists()


def test_build_audio_input_manifest_documents_virtual_audio() -> None:
    manifest = build_audio_input_manifest(
        load_realtime_config({"SOKCON_AUDIO_INPUT_DEVICE": "BlackHole"})
    )

    assert "macos_virtual_audio_device" in manifest["supported_sources"]
    assert "mixed_self_and_remote_audio" in manifest["supported_sources"]
    assert manifest["macos_virtual_audio_expected"] is True
    assert manifest["configured_audio_input_device"] == "BlackHole"
    assert manifest["participant_audio_policy"]["self_voice_supported"] is True
    assert manifest["participant_audio_policy"]["remote_voice_supported"] is True
    assert {"Google Meet", "Zoom", "Slack Huddle"}.issubset(
        set(manifest["supported_meeting_apps"])
    )


def test_build_audio_capture_command_rejects_invalid_duration(tmp_path: Path) -> None:
    try:
        build_audio_capture_command(tmp_path / "meeting.wav", 0)
    except ValueError as error:
        assert "duration_seconds" in str(error)
    else:
        raise AssertionError("invalid duration should fail")


def test_build_realtime_send_plan_uses_audio_append_events() -> None:
    plan = build_realtime_send_plan(
        {"source": "sample.wav", "realtime_input_audio_format": "pcm16"},
        [{"index": 0, "start_ms": 0, "audio": "AAAA"}],
    )

    assert plan["status"] == "draft"
    assert plan["event_count"] == 2
    assert plan["events"][0]["type"] == "input_audio_buffer.append"


def test_create_realtime_session_dry_run_does_not_execute_network() -> None:
    config = load_realtime_config({"OPENAI_API_KEY": "sk-test-secret"})

    result = create_realtime_session(config)

    assert result["status"] == "dry_run"
    assert result["network_request_executed"] is False
    assert "sk-test-secret" not in str(result)


def test_create_realtime_session_execute_uses_injected_sender() -> None:
    config = load_realtime_config({"OPENAI_API_KEY": "sk-test-secret"})
    calls = []

    def fake_sender(url, api_key, payload):
        calls.append((url, api_key, payload))
        return {"id": "sess_123"}

    result = create_realtime_session(config, execute=True, post_json=fake_sender)

    assert result["status"] == "created"
    assert result["network_request_executed"] is True
    assert result["response"] == {"id": "sess_123"}
    assert calls[0][1] == "sk-test-secret"


def test_stream_realtime_audio_dry_run_counts_events(tmp_path: Path) -> None:
    (tmp_path / "realtime_send_plan.json").write_text(
        '{"events":[{"type":"input_audio_buffer.commit"}]}',
        encoding="utf-8",
    )
    config = load_realtime_config({"OPENAI_API_KEY": "sk-test-secret"})

    result = stream_realtime_audio(artifact_dir=tmp_path, config=config)

    assert result["status"] == "dry_run"
    assert result["network_request_executed"] is False
    assert result["event_count"] == 1


def test_stream_realtime_audio_execute_uses_transport_factory(tmp_path: Path) -> None:
    (tmp_path / "realtime_send_plan.json").write_text(
        '{"events":[{"type":"input_audio_buffer.commit"}]}',
        encoding="utf-8",
    )
    sent = []

    class FakeTransport:
        def __init__(self, url, api_key):
            self.url = url
            self.api_key = api_key

        def connect(self):
            sent.append(("connect", self.url, self.api_key))

        def send_json(self, payload):
            sent.append(("send", payload["type"]))

        def close(self):
            sent.append(("close",))

    config = load_realtime_config({"OPENAI_API_KEY": "sk-test-secret"})

    result = stream_realtime_audio(
        artifact_dir=tmp_path,
        config=config,
        execute=True,
        transport_factory=FakeTransport,
    )

    assert result["status"] == "streamed"
    assert result["network_request_executed"] is True
    assert result["event_count"] == 2
    assert sent[0][0] == "connect"
    assert ("send", "session.update") in sent
    assert ("send", "input_audio_buffer.commit") in sent


def test_run_realtime_live_check_dry_run_reports_readiness(tmp_path: Path) -> None:
    (tmp_path / "realtime_send_plan.json").write_text(
        '{"events":[{"type":"input_audio_buffer.commit"}]}',
        encoding="utf-8",
    )
    config = load_realtime_config({"OPENAI_API_KEY": "sk-test-secret"})

    result = run_realtime_live_check(artifact_dir=tmp_path, config=config)

    assert result["status"] == "dry_run"
    assert result["network_request_executed"] is False
    assert result["has_openai_api_key"] is True
    assert result["has_realtime_send_plan"] is True
    assert "--execute" in result["next_action"]
    assert result["session"]["payload"]["type"] == "realtime"
    assert result["compatibility"]["session_shape"]["has_audio_object"] is True


def test_run_realtime_live_check_writes_result_when_requested(tmp_path: Path) -> None:
    (tmp_path / "realtime_send_plan.json").write_text(
        '{"events":[{"type":"input_audio_buffer.commit"}]}',
        encoding="utf-8",
    )
    config = load_realtime_config({"OPENAI_API_KEY": "sk-test-secret"})

    result = run_realtime_live_check(
        artifact_dir=tmp_path,
        config=config,
        write_result=True,
    )

    assert result["status"] == "dry_run"
    written = json.loads((tmp_path / "realtime_live_check_result.json").read_text())
    assert written["status"] == "dry_run"


def test_run_realtime_live_check_execute_writes_failed_result_without_key(
    tmp_path: Path,
) -> None:
    (tmp_path / "realtime_send_plan.json").write_text(
        '{"events":[{"type":"input_audio_buffer.commit"}]}',
        encoding="utf-8",
    )

    result = run_realtime_live_check(
        artifact_dir=tmp_path,
        config=load_realtime_config({}),
        execute=True,
        write_result=True,
    )

    assert result["status"] == "failed"
    assert result["network_request_executed"] is False
    assert result["missing"] == ["OPENAI_API_KEY"]
    assert "OPENAI_API_KEY" in result["next_action"]
    assert "--execute" in result["next_action"]
    written = json.loads((tmp_path / "realtime_live_check_result.json").read_text())
    assert written["status"] == "failed"


def test_websocket_helpers_build_protocol_values() -> None:
    assert websocket_accept_key("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
    frame = build_websocket_frame(b"hello")
    assert frame[0] == 0x81
    assert frame[1] & 0x80
