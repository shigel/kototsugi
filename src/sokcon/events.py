from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any, Iterable, List

from sokcon.pipeline import TranscriptEvent


def load_transcript_events(payload: str) -> List[TranscriptEvent]:
    data = parse_event_payload(payload)
    return [normalize_event(item) for item in data]


def parse_event_payload(payload: str) -> List[dict[str, Any]]:
    stripped = payload.strip()
    if not stripped:
        return []
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except JSONDecodeError:
            return [json.loads(line) for line in stripped.splitlines() if line.strip()]
        events = data.get("events", [data]) if isinstance(data, dict) else data
        return ensure_event_dicts(events)
    return [json.loads(line) for line in stripped.splitlines() if line.strip()]


def ensure_event_dicts(items: Iterable[Any]) -> List[dict[str, Any]]:
    events: List[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Transcript event payload must contain JSON objects.")
        events.append(item)
    return events


def normalize_event(raw: dict[str, Any]) -> TranscriptEvent:
    event_type = str(raw.get("type", ""))
    kind = str(raw.get("kind") or raw.get("status") or infer_kind(event_type))
    if kind not in {"partial", "final"}:
        raise ValueError(f"Unsupported transcript event kind: {kind}")

    text = raw.get("text")
    if text is None:
        text = raw.get("delta") if kind == "partial" else raw.get("transcript")
    if text is None:
        text = raw.get("transcript") or raw.get("delta") or ""

    return TranscriptEvent(
        kind=kind,
        text=str(text),
        timestamp=str(raw.get("timestamp") or raw.get("time") or raw.get("start_time") or ""),
        speaker=str(raw.get("speaker") or raw.get("participant") or "Unknown"),
        source_event_id=str(
            raw.get("source_event_id") or raw.get("event_id") or raw.get("id") or ""
        ),
    )


def infer_kind(event_type: str) -> str:
    if event_type.endswith(".delta"):
        return "partial"
    if event_type.endswith(".completed"):
        return "final"
    return ""
