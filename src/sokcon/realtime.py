from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import subprocess
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Dict
from urllib.parse import urlencode, urlparse

DEFAULT_REALTIME_MODEL = "gpt-realtime-2"
DEFAULT_TRANSCRIPTION_REALTIME_MODEL = "gpt-realtime-whisper"
DEFAULT_TRANSLATION_REALTIME_MODEL = "gpt-realtime-translate"
DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-transcribe"
DEFAULT_VOICE = "alloy"
DEFAULT_AUDIO_CHUNK_MS = 100
DEFAULT_REALTIME_SESSION_URL = "https://api.openai.com/v1/realtime/sessions"
DEFAULT_REALTIME_WS_URL = "wss://api.openai.com/v1/realtime"
REALTIME_ROUTES = ("primary", "transcription", "translation")
OPENAI_REALTIME_DOCS_URL = "https://developers.openai.com/api/docs/guides/realtime"
OPENAI_REALTIME_TRANSCRIPTION_DOCS_URL = (
    "https://developers.openai.com/api/docs/guides/realtime-transcription"
)


@dataclass(frozen=True)
class RealtimeConfig:
    api_key: str
    realtime_model: str = DEFAULT_REALTIME_MODEL
    transcription_realtime_model: str = DEFAULT_TRANSCRIPTION_REALTIME_MODEL
    translation_realtime_model: str = DEFAULT_TRANSLATION_REALTIME_MODEL
    transcription_model: str = DEFAULT_TRANSCRIPTION_MODEL
    realtime_route: str = "primary"
    translation_target_language: str = "ja"
    voice: str = DEFAULT_VOICE
    input_audio_format: str = "pcm16"
    output_audio_format: str = "pcm16"
    audio_input_device: str = ""
    external_registration_enabled: bool = False

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)


def load_realtime_config(env: Dict[str, str] | None = None) -> RealtimeConfig:
    values = env if env is not None else os.environ
    return RealtimeConfig(
        api_key=values.get("OPENAI_API_KEY", ""),
        realtime_model=values.get("SOKCON_REALTIME_MODEL", DEFAULT_REALTIME_MODEL),
        transcription_realtime_model=values.get(
            "SOKCON_TRANSCRIPTION_REALTIME_MODEL",
            DEFAULT_TRANSCRIPTION_REALTIME_MODEL,
        ),
        translation_realtime_model=values.get(
            "SOKCON_TRANSLATION_REALTIME_MODEL",
            DEFAULT_TRANSLATION_REALTIME_MODEL,
        ),
        transcription_model=values.get(
            "SOKCON_TRANSCRIPTION_MODEL",
            DEFAULT_TRANSCRIPTION_MODEL,
        ),
        realtime_route=values.get("SOKCON_REALTIME_ROUTE", "primary"),
        translation_target_language=values.get("SOKCON_TRANSLATION_TARGET_LANGUAGE", "ja"),
        voice=values.get("SOKCON_REALTIME_VOICE", DEFAULT_VOICE),
        input_audio_format=values.get("SOKCON_INPUT_AUDIO_FORMAT", "pcm16"),
        output_audio_format=values.get("SOKCON_OUTPUT_AUDIO_FORMAT", "pcm16"),
        audio_input_device=values.get("SOKCON_AUDIO_INPUT_DEVICE", ""),
        external_registration_enabled=values.get("SOKCON_ENABLE_EXTERNAL_REGISTRATION")
        == "1",
    )


def build_realtime_session_payload(config: RealtimeConfig) -> Dict[str, object]:
    route = normalize_realtime_route(config.realtime_route)
    model = realtime_model_for_route(config, route)
    if route == "transcription":
        return build_realtime_transcription_session_payload(config, model)
    return {
        "type": "realtime",
        "model": model,
        "route": route,
        "output_modalities": ["audio", "text"],
        "audio": {
            "input": {
                "format": audio_format_payload(config.input_audio_format),
                "transcription": {"model": config.transcription_model},
                "turn_detection": {"type": "server_vad"},
            },
            "output": {
                "format": audio_format_payload(config.output_audio_format),
                "voice": config.voice,
            },
        },
        "instructions": instructions_for_route(route, config.translation_target_language),
    }


def build_realtime_transcription_session_payload(
    config: RealtimeConfig,
    model: str,
) -> Dict[str, object]:
    return {
        "type": "transcription",
        "model": model,
        "route": "transcription",
        "audio": {
            "input": {
                "format": audio_format_payload(config.input_audio_format),
                "transcription": {"model": config.transcription_model},
                "turn_detection": {"type": "server_vad"},
            }
        },
        "include": ["item.input_audio_transcription.logprobs"],
        "instructions": instructions_for_route("transcription", config.translation_target_language),
    }


def audio_format_payload(format_name: str) -> Dict[str, object]:
    normalized = format_name.strip().lower()
    if normalized in {"pcm16", "audio/pcm"}:
        return {"type": "audio/pcm", "rate": 24000}
    if normalized in {"g711_ulaw", "pcmu", "audio/pcmu"}:
        return {"type": "audio/pcmu"}
    if normalized in {"g711_alaw", "pcma", "audio/pcma"}:
        return {"type": "audio/pcma"}
    return {"type": normalized}


def build_realtime_api_compatibility_report(config: RealtimeConfig) -> Dict[str, object]:
    payload = build_realtime_session_payload(config)
    return {
        "status": "ready_for_live_check" if config.has_api_key else "missing_api_key",
        "docs": {
            "realtime": OPENAI_REALTIME_DOCS_URL,
            "transcription": OPENAI_REALTIME_TRANSCRIPTION_DOCS_URL,
        },
        "configured_model": realtime_model_for_route(
            config,
            normalize_realtime_route(config.realtime_route),
        ),
        "configured_route": normalize_realtime_route(config.realtime_route),
        "session_shape": {
            "has_type": "type" in payload,
            "has_audio_object": "audio" in payload,
            "uses_legacy_modalities_field": "modalities" in payload,
            "uses_legacy_input_audio_format_field": "input_audio_format" in payload,
        },
        "transcription_events": [
            "conversation.item.input_audio_transcription.delta",
            "conversation.item.input_audio_transcription.completed",
        ],
        "audio_append_event": "input_audio_buffer.append",
    }


def build_realtime_route_plan(config: RealtimeConfig) -> Dict[str, object]:
    return {
        "default_route": normalize_realtime_route(config.realtime_route),
        "routes": {
            route: {
                "model": realtime_model_for_route(config, route),
                "payload": build_realtime_session_payload(
                    RealtimeConfig(
                        api_key=config.api_key,
                        realtime_model=config.realtime_model,
                        transcription_realtime_model=config.transcription_realtime_model,
                        translation_realtime_model=config.translation_realtime_model,
                        transcription_model=config.transcription_model,
                        realtime_route=route,
                        translation_target_language=config.translation_target_language,
                        voice=config.voice,
                        input_audio_format=config.input_audio_format,
                        output_audio_format=config.output_audio_format,
                        audio_input_device=config.audio_input_device,
                        external_registration_enabled=config.external_registration_enabled,
                    )
                ),
            }
            for route in REALTIME_ROUTES
        },
        "mvp_default": "primary",
        "post_mvp_candidates": ["transcription", "translation"],
    }


def normalize_realtime_route(route: str) -> str:
    normalized = route.strip().lower()
    if normalized not in REALTIME_ROUTES:
        allowed = ", ".join(REALTIME_ROUTES)
        raise ValueError(f"Unsupported realtime route: {route}. Allowed routes: {allowed}")
    return normalized


def realtime_model_for_route(config: RealtimeConfig, route: str) -> str:
    normalized = normalize_realtime_route(route)
    if normalized == "transcription":
        return config.transcription_realtime_model
    if normalized == "translation":
        return config.translation_realtime_model
    return config.realtime_model


def instructions_for_route(route: str, target_language: str) -> str:
    normalized = normalize_realtime_route(route)
    if normalized == "transcription":
        return (
            "You are SOKCON's low-latency transcription route. Emit partial "
            "transcript events for display and final transcript events for grounded artifacts."
        )
    if normalized == "translation":
        return (
            "You are SOKCON's simultaneous interpretation candidate route. "
            f"Translate meeting speech into {target_language} while preserving final transcript "
            "events for grounded artifacts."
        )
    return (
        "You are SOKCON's realtime meeting gateway. Emit partial transcript "
        "events for display, final transcript events for grounded artifacts, and short "
        "meeting-intent triggers for worker actions."
    )


def create_realtime_session(
    config: RealtimeConfig,
    *,
    execute: bool = False,
    post_json: object | None = None,
) -> Dict[str, object]:
    payload = build_realtime_session_payload(config)
    if not execute:
        return {
            "status": "dry_run",
            "network_request_executed": False,
            "url": DEFAULT_REALTIME_SESSION_URL,
            "payload": payload,
        }
    if not config.api_key:
        raise ValueError("OPENAI_API_KEY is required when execute=True")
    sender = post_json if post_json is not None else post_realtime_session
    response = sender(DEFAULT_REALTIME_SESSION_URL, config.api_key, payload)
    return {
        "status": "created",
        "network_request_executed": True,
        "url": DEFAULT_REALTIME_SESSION_URL,
        "response": response,
    }


def post_realtime_session(
    url: str,
    api_key: str,
    payload: Dict[str, object],
) -> Dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8")
        raise RuntimeError(f"Realtime session request failed: {error.code} {message}") from error


def describe_realtime_config(config: RealtimeConfig) -> Dict[str, object]:
    return {
        "has_openai_api_key": config.has_api_key,
        "realtime_model": config.realtime_model,
        "transcription_realtime_model": config.transcription_realtime_model,
        "translation_realtime_model": config.translation_realtime_model,
        "transcription_model": config.transcription_model,
        "realtime_route": normalize_realtime_route(config.realtime_route),
        "translation_target_language": config.translation_target_language,
        "voice": config.voice,
        "input_audio_format": config.input_audio_format,
        "output_audio_format": config.output_audio_format,
        "audio_input_device": config.audio_input_device,
        "audio_input_manifest": build_audio_input_manifest(config),
        "external_registration_enabled": config.external_registration_enabled,
        "session_payload": build_realtime_session_payload(config),
        "route_plan": build_realtime_route_plan(config),
        "api_compatibility": build_realtime_api_compatibility_report(config),
    }


def prepare_wav_audio(
    *,
    input_path: Path,
    output_dir: Path,
    chunk_ms: int = DEFAULT_AUDIO_CHUNK_MS,
) -> Dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest, chunks = build_wav_audio_payload(input_path, chunk_ms)
    manifest_path = output_dir / "audio_manifest.json"
    chunks_path = output_dir / "audio_chunks.json"
    send_plan_path = output_dir / "realtime_send_plan.json"
    send_plan = build_realtime_send_plan(manifest, chunks)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    chunks_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n")
    send_plan_path.write_text(json.dumps(send_plan, ensure_ascii=False, indent=2) + "\n")
    return {
        "manifest": manifest,
        "chunks": chunks,
        "send_plan": send_plan,
        "artifacts": [str(manifest_path), str(chunks_path), str(send_plan_path)],
    }


def build_audio_input_manifest(config: RealtimeConfig) -> Dict[str, object]:
    return {
        "supported_sources": [
            "microphone",
            "macos_virtual_audio_device",
            "meeting_app_system_audio",
            "mixed_self_and_remote_audio",
            "future_bot",
            "future_sip_webrtc",
            "future_browser_extension",
        ],
        "participant_audio_policy": {
            "self_voice_supported": True,
            "remote_voice_supported": True,
            "recommended_capture_topology": (
                "Route microphone and meeting-app/system audio into one macOS virtual input."
            ),
            "separate_channel_detection": "post_capture_diarization_or_transcript_metadata",
        },
        "supported_meeting_apps": ["Google Meet", "Zoom", "Slack Huddle"],
        "macos_virtual_audio_expected": True,
        "recommended_virtual_device": "BlackHole",
        "configured_audio_input_device": config.audio_input_device,
        "device_selection_supported": True,
        "capture_command": "afrecord",
    }


def build_audio_capture_command(
    output_path: Path,
    duration_seconds: int,
    audio_input_device: str = "",
) -> list[str]:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    command = ["afrecord", "-f", "WAVE", "-d", str(duration_seconds)]
    if audio_input_device:
        command.extend(["-i", audio_input_device])
    command.append(str(output_path))
    return command


def capture_audio(
    *,
    output_path: Path,
    duration_seconds: int,
    audio_input_device: str = "",
    execute: bool = False,
    runner: object | None = None,
) -> Dict[str, object]:
    config = RealtimeConfig(api_key="", audio_input_device=audio_input_device)
    audio_input_manifest = build_audio_input_manifest(config)
    command = build_audio_capture_command(output_path, duration_seconds, audio_input_device)
    if not execute:
        return {
            "status": "dry_run",
            "command": command,
            "audio_input_manifest": audio_input_manifest,
            "audio_capture_executed": False,
        }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    (output_path.parent / "audio_input_manifest.json").write_text(
        json.dumps(audio_input_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    run = runner if runner is not None else run_capture_command
    result = run(command)
    return {
        "status": "captured" if result["returncode"] == 0 else "failed",
        "command": command,
        "audio_input_manifest": audio_input_manifest,
        "audio_capture_executed": True,
        "result": result,
    }


def run_capture_command(command: list[str]) -> Dict[str, object]:
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def build_wav_audio_payload(
    input_path: Path,
    chunk_ms: int,
) -> tuple[Dict[str, object], list[Dict[str, object]]]:
    if chunk_ms <= 0:
        raise ValueError("chunk_ms must be positive")
    with wave.open(str(input_path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        frame_rate = wav.getframerate()
        frame_count = wav.getnframes()
        compression = wav.getcomptype()
        if compression != "NONE":
            raise ValueError("Only uncompressed PCM WAV is supported")
        if sample_width != 2:
            raise ValueError("Only 16-bit PCM WAV is supported")

        frames_per_chunk = max(1, int(frame_rate * chunk_ms / 1000))
        chunks = []
        index = 0
        while True:
            data = wav.readframes(frames_per_chunk)
            if not data:
                break
            start_ms = int(index * frames_per_chunk * 1000 / frame_rate)
            chunks.append(
                {
                    "index": index,
                    "start_ms": start_ms,
                    "duration_ms": int(len(data) / (channels * sample_width) * 1000 / frame_rate),
                    "encoding": "base64_pcm16",
                    "audio": base64.b64encode(data).decode("ascii"),
                }
            )
            index += 1

    manifest = {
        "source": str(input_path),
        "format": "wav",
        "channels": channels,
        "sample_width_bytes": sample_width,
        "sample_rate_hz": frame_rate,
        "realtime_recommended_sample_rate_hz": 24000,
        "realtime_sample_rate_ready": frame_rate == 24000,
        "frame_count": frame_count,
        "duration_ms": int(frame_count * 1000 / frame_rate) if frame_rate else 0,
        "chunk_ms": chunk_ms,
        "chunk_count": len(chunks),
        "realtime_input_audio_format": "pcm16",
    }
    return manifest, chunks


def build_realtime_send_plan(
    manifest: Dict[str, object],
    chunks: list[Dict[str, object]],
) -> Dict[str, object]:
    events = [
        {
            "type": "input_audio_buffer.append",
            "audio": chunk["audio"],
            "chunk_index": chunk["index"],
            "start_ms": chunk["start_ms"],
        }
        for chunk in chunks
    ]
    events.append({"type": "input_audio_buffer.commit"})
    return {
        "status": "draft",
        "network_send_enabled": False,
        "source": manifest["source"],
        "realtime_input_audio_format": manifest["realtime_input_audio_format"],
        "event_count": len(events),
        "events": events,
    }


def build_realtime_ws_url(config: RealtimeConfig) -> str:
    model = realtime_model_for_route(config, normalize_realtime_route(config.realtime_route))
    return f"{DEFAULT_REALTIME_WS_URL}?{urlencode({'model': model})}"


def stream_realtime_audio(
    *,
    artifact_dir: Path,
    config: RealtimeConfig,
    execute: bool = False,
    transport_factory: object | None = None,
) -> Dict[str, object]:
    send_plan = json.loads((artifact_dir / "realtime_send_plan.json").read_text(encoding="utf-8"))
    events = send_plan.get("events", [])
    if not execute:
        return {
            "status": "dry_run",
            "network_request_executed": False,
            "event_count": len(events),
            "url": build_realtime_ws_url(config),
        }
    if not config.api_key:
        raise ValueError("OPENAI_API_KEY is required when execute=True")
    factory = transport_factory if transport_factory is not None else RealtimeWebSocketTransport
    transport = factory(build_realtime_ws_url(config), config.api_key)
    sent = 0
    try:
        transport.connect()
        transport.send_json(
            {"type": "session.update", "session": build_realtime_session_payload(config)}
        )
        sent += 1
        for event in events:
            if isinstance(event, dict):
                transport.send_json(event)
                sent += 1
    finally:
        transport.close()
    return {
        "status": "streamed",
        "network_request_executed": True,
        "event_count": sent,
    }


def run_realtime_live_check(
    *,
    artifact_dir: Path,
    config: RealtimeConfig,
    execute: bool = False,
    write_result: bool = False,
    post_json: object | None = None,
    transport_factory: object | None = None,
) -> Dict[str, object]:
    compatibility = build_realtime_api_compatibility_report(config)
    send_plan_path = artifact_dir / "realtime_send_plan.json"
    has_send_plan = send_plan_path.exists()
    if not execute:
        result = {
            "status": "dry_run",
            "network_request_executed": False,
            "has_openai_api_key": config.has_api_key,
            "has_realtime_send_plan": has_send_plan,
            "next_action": realtime_live_check_next_action(
                config=config,
                has_send_plan=has_send_plan,
                execute_required=True,
            ),
            "session": create_realtime_session(config, execute=False),
            "stream": {
                "status": "ready" if has_send_plan else "missing_realtime_send_plan",
                "url": build_realtime_ws_url(config),
            },
            "compatibility": compatibility,
        }
        if write_result:
            write_realtime_live_check_result(artifact_dir, result)
        return result
    if not config.api_key or not has_send_plan:
        result = {
            "status": "failed",
            "network_request_executed": False,
            "has_openai_api_key": config.has_api_key,
            "has_realtime_send_plan": has_send_plan,
            "missing": missing_realtime_live_check_inputs(config, has_send_plan),
            "next_action": realtime_live_check_next_action(
                config=config,
                has_send_plan=has_send_plan,
                execute_required=False,
            ),
            "compatibility": compatibility,
        }
        if write_result:
            write_realtime_live_check_result(artifact_dir, result)
        return result
    try:
        session_result = create_realtime_session(config, execute=True, post_json=post_json)
        stream_result = stream_realtime_audio(
            artifact_dir=artifact_dir,
            config=config,
            execute=True,
            transport_factory=transport_factory,
        )
    except Exception as error:
        result = {
            "status": "failed",
            "network_request_executed": False,
            "has_openai_api_key": config.has_api_key,
            "has_realtime_send_plan": has_send_plan,
            "error_type": type(error).__name__,
            "error": str(error),
            "next_action": "Fix the reported Realtime session or streaming error, then rerun "
            "`--run-realtime-live-check <artifact-dir> --execute`.",
            "compatibility": compatibility,
        }
        if write_result:
            write_realtime_live_check_result(artifact_dir, result)
        return result
    result = {
        "status": "completed",
        "network_request_executed": True,
        "session": session_result,
        "stream": stream_result,
        "compatibility": compatibility,
    }
    if write_result:
        write_realtime_live_check_result(artifact_dir, result)
    return result


def missing_realtime_live_check_inputs(config: RealtimeConfig, has_send_plan: bool) -> list[str]:
    missing = []
    if not config.api_key:
        missing.append("OPENAI_API_KEY")
    if not has_send_plan:
        missing.append("realtime_send_plan.json")
    return missing


def realtime_live_check_next_action(
    *,
    config: RealtimeConfig,
    has_send_plan: bool,
    execute_required: bool,
) -> str:
    missing = missing_realtime_live_check_inputs(config, has_send_plan)
    if missing:
        return (
            "Provide the missing input(s): "
            + ", ".join(missing)
            + "; then rerun `--run-realtime-live-check <artifact-dir> --execute`."
        )
    if execute_required:
        return (
            "Rerun `--run-realtime-live-check <artifact-dir> --execute` to perform "
            "network verification."
        )
    return (
        "Rerun `--run-realtime-live-check <artifact-dir> --execute` after fixing "
        "the failed check."
    )


def write_realtime_live_check_result(
    artifact_dir: Path,
    result: Dict[str, object],
) -> Path:
    output = artifact_dir / "realtime_live_check_result.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


class RealtimeWebSocketTransport:
    def __init__(self, url: str, api_key: str) -> None:
        self.url = url
        self.api_key = api_key
        self.sock = None

    def connect(self) -> None:
        parsed = urlparse(self.url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        raw_sock = socket.create_connection((host, port), timeout=30)
        self.sock = ssl.create_default_context().wrap_socket(raw_sock, server_hostname=host)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = "\r\n".join(
            [
                f"GET {path} HTTP/1.1",
                f"Host: {host}",
                "Upgrade: websocket",
                "Connection: Upgrade",
                f"Sec-WebSocket-Key: {key}",
                "Sec-WebSocket-Version: 13",
                f"Authorization: Bearer {self.api_key}",
                "OpenAI-Beta: realtime=v1",
                "\r\n",
            ]
        )
        self.sock.sendall(request.encode("ascii"))
        response = self.sock.recv(4096)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"Realtime WebSocket handshake failed: {response[:120]!r}")
        accept = websocket_accept_key(key).encode("ascii")
        if accept not in response:
            raise RuntimeError("Realtime WebSocket handshake returned an invalid accept key")

    def send_json(self, payload: Dict[str, object]) -> None:
        self.send_text(json.dumps(payload, ensure_ascii=False))

    def send_text(self, text: str) -> None:
        if self.sock is None:
            raise RuntimeError("WebSocket is not connected")
        self.sock.sendall(build_websocket_frame(text.encode("utf-8")))

    def close(self) -> None:
        if self.sock is None:
            return
        try:
            self.sock.sendall(build_websocket_frame(b"", opcode=0x8))
        finally:
            self.sock.close()
            self.sock = None


def websocket_accept_key(sec_websocket_key: str) -> str:
    magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    digest = hashlib.sha1((sec_websocket_key + magic).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def build_websocket_frame(payload: bytes, opcode: int = 0x1) -> bytes:
    first = 0x80 | opcode
    length = len(payload)
    mask = os.urandom(4)
    if length < 126:
        header = bytes([first, 0x80 | length])
    elif length < 65536:
        header = bytes([first, 0x80 | 126]) + length.to_bytes(2, "big")
    else:
        header = bytes([first, 0x80 | 127]) + length.to_bytes(8, "big")
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return header + mask + masked
