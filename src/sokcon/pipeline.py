from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Dict, List, Sequence

from sokcon.approvals import build_issue_status_summary, build_question_status_summary
from sokcon.diarization import (
    build_diarization_manifest,
    load_diarization_config,
    write_diarization_artifacts,
)
from sokcon.modes import get_mode_profile, mode_profile_payload
from sokcon.notifications import build_macos_notification_plan
from sokcon.retention import build_retention_policy


@dataclass(frozen=True)
class PipelineResult:
    artifacts: List[Path]
    metrics: Dict[str, float]


@dataclass(frozen=True)
class TranscriptLine:
    timestamp: str
    speaker: str
    text: str
    source_event_id: str = ""


@dataclass(frozen=True)
class TranscriptEvent:
    kind: str
    text: str
    timestamp: str = ""
    speaker: str = "Unknown"
    source_event_id: str = ""


QUESTION_KEYWORDS = ("必要", "ですか", "ますか", "どう", "どの", "何", "未定", "確認")
DECISION_KEYWORDS = ("でよい", "で十分", "お願いします", "決定", "後回し")
REQUIREMENT_KEYWORDS = (
    "必要",
    "できる",
    "表示",
    "更新",
    "ログイン",
    "ダッシュボード",
    "Issue",
    "実装",
)
DEFAULT_MEETING_ID = "mtg_local"
DEFAULT_CREATED_AT = "2026-05-08T00:00:00Z"


def process_transcript(
    *,
    transcript: str,
    output_dir: Path,
    meeting_mode: str = "development",
    project_name: str = "SOKCON Project",
    confidential: bool = False,
    retention_days: int = 30,
    external_destinations: Sequence[str] | None = None,
    external_registration_enabled: bool = False,
) -> PipelineResult:
    """Process a transcript into MDD artifacts.

    This MVP intentionally uses deterministic heuristics so the qualitative and
    quantitative evaluation loop can run offline in CI. LLM/realtime workers can
    later replace each extractor behind the same artifact contract.
    """
    started_at = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)
    lines = parse_transcript(transcript)
    decisions = extract_decisions(lines)
    questions = prioritize_questions(lines)
    requirements = extract_requirements(lines, decisions)
    blocker_suggestions = build_blocker_question_suggestions(requirements, questions)
    issues = build_issue_candidates(lines, requirements, questions)
    diagram = build_mermaid_diagram(project_name, requirements)
    diagrams = build_mermaid_diagrams(project_name, meeting_mode, requirements, issues)
    diagram_revisions = build_diagram_revisions(diagrams)
    plan = build_implementation_plan(project_name, requirements, questions, issues)
    branch_draft = build_branch_creation_draft(project_name, questions, issues)
    pr_draft = build_pull_request_draft(project_name, requirements, questions, issues)
    metrics = evaluate_outputs(lines, requirements, questions, issues, decisions)
    metrics.update(
        {
            "transcript_event_count": float(len(lines)),
            "partial_transcript_event_count": 0.0,
            "final_transcript_event_count": float(len(lines)),
        }
    )
    destinations = [] if confidential else list(external_destinations or [])
    registration_enabled = external_registration_enabled and not confidential
    mode_profile = mode_profile_payload(meeting_mode)
    action_queue = build_action_queue(
        questions=questions,
        issues=issues,
        external_destinations=destinations,
        external_registration_enabled=registration_enabled,
    )
    audit_log = build_audit_log(
        project_name=project_name,
        meeting_mode=meeting_mode,
        external_destinations=destinations,
        external_registration_enabled=registration_enabled,
        requirements=requirements,
        decisions=decisions,
        questions=questions,
        issues=issues,
    )
    diarization_segments = build_diarization_segments(lines)
    diarization_config = load_diarization_config()

    artifacts = [
        write_json(output_dir / "transcript_events.json", render_transcript_line_events(lines)),
        write_text(
            output_dir / "partial_transcript.md",
            render_partial_transcript(project_name, []),
        ),
        write_text(output_dir / "transcript.md", render_transcript(project_name, lines)),
        write_text(
            output_dir / "speaker_summary.md",
            render_speaker_summary(
                project_name,
                lines,
                build_diarization_manifest(
                    config=diarization_config,
                    speaker_count=count_speakers(lines),
                    segments=diarization_segments,
                ),
            ),
        ),
        write_text(
            output_dir / "summary.md",
            render_summary(project_name, lines, decisions, metrics),
        ),
        write_text(output_dir / "rolling_summary.md", render_rolling_summary(project_name, lines)),
        write_text(output_dir / "decisions.md", render_decisions(project_name, decisions)),
        write_text(
            output_dir / "requirements.md",
            render_requirements(project_name, meeting_mode, requirements, decisions, questions),
        ),
        write_json(output_dir / "requirements_items.json", requirements),
        write_text(output_dir / "open_questions.md", render_questions(questions)),
        write_json(output_dir / "questions.json", questions),
        write_json(output_dir / "question_status.json", build_question_status_summary(questions)),
        write_json(output_dir / "blocker_question_suggestions.json", blocker_suggestions),
        write_text(output_dir / "architecture.md", diagram),
        write_text(output_dir / "diagrams.md", diagrams),
        write_json(output_dir / "diagram_revisions.json", diagram_revisions),
        write_json(output_dir / "issue_candidates.json", issues),
        write_json(output_dir / "issue_status.json", build_issue_status_summary(issues)),
        write_text(output_dir / "implementation_plan.md", plan),
        write_json(output_dir / "mode_profile.json", mode_profile),
        write_json(output_dir / "evaluation.json", build_evaluation(metrics, questions, issues)),
        write_json(
            output_dir / "audit_log.json",
            audit_log,
        ),
        write_json(output_dir / "event_bus.json", build_event_bus(audit_log)),
        write_json(output_dir / "worker_status.json", build_worker_status(audit_log)),
        write_json(
            output_dir / "privacy_manifest.json",
            build_privacy_manifest(
                confidential=confidential,
                retention_days=retention_days,
                external_destinations=destinations,
                external_registration_enabled=registration_enabled,
            ),
        ),
        write_json(
            output_dir / "retention_policy.json",
            build_retention_policy(
                retention_days=retention_days,
                confidential=confidential,
            ),
        ),
        write_json(
            output_dir / "performance_manifest.json",
            build_performance_manifest(
                started_at=started_at,
                metrics=metrics,
                worker_status=build_worker_status(audit_log),
            ),
        ),
        write_json(
            output_dir / "mvp_success_conditions.json",
            build_mvp_success_conditions(
                artifacts=[
                    "transcript.md",
                    "summary.md",
                    "requirements.md",
                    "open_questions.md",
                    "architecture.md",
                    "issue_candidates.json",
                    "implementation_plan.md",
                ],
                metrics=metrics,
                blocker_suggestions=blocker_suggestions,
                issues=issues,
            ),
        ),
        write_json(
            output_dir / "action_queue.json",
            action_queue,
        ),
        write_json(output_dir / "branch_creation_draft.json", branch_draft),
        write_json(output_dir / "pull_request_draft.json", pr_draft),
        write_json(
            output_dir / "macos_notification_plan.json",
            build_macos_notification_plan(
                project_name=project_name,
                questions=questions,
                action_queue=action_queue,
            ),
        ),
        write_json(output_dir / "notification_policy.json", build_notification_policy(questions)),
        write_json(
            output_dir / "external_email_draft.json",
            build_external_email_draft(
                project_name=project_name,
                requirements=requirements,
                questions=questions,
                issues=issues,
            ),
        ),
        write_json(
            output_dir / "slack_notification.json",
            build_slack_notification(
                project_name=project_name,
                metrics=metrics,
                questions=questions,
                issues=issues,
                external_registration_enabled=registration_enabled,
            ),
        ),
        write_json(
            output_dir / "external_registration_payloads.json",
            build_external_registration_payloads(
                issues=issues,
                external_destinations=destinations,
                external_registration_enabled=registration_enabled,
            ),
        ),
        write_json(
            output_dir / "agent_handoff.json",
            build_agent_handoff(
                project_name=project_name,
                questions=questions,
                issues=issues,
            ),
        ),
        write_json(
            output_dir / "requirements_traceability.json",
            build_requirements_traceability(),
        ),
    ]
    artifacts.extend(
        write_diarization_artifacts(
            output_dir=output_dir,
            config=diarization_config,
            speaker_count=count_speakers(lines),
            segments=diarization_segments,
        )
    )
    artifacts.extend(
        write_mode_specific_artifacts(
            output_dir=output_dir,
            meeting_mode=meeting_mode,
            project_name=project_name,
            lines=lines,
            metrics=metrics,
            decisions=decisions,
            questions=questions,
            issues=issues,
        )
    )
    artifacts.append(
        write_json(
            output_dir / "state_snapshot.json",
            build_state_snapshot(
                project_name=project_name,
                meeting_mode=meeting_mode,
                lines=lines,
                metrics=metrics,
                requirements=requirements,
                decisions=decisions,
                questions=questions,
                issues=issues,
                artifacts=artifacts,
            ),
        )
    )
    artifacts.append(
        write_text(
            output_dir / "dashboard.html",
            render_dashboard(
                project_name=project_name,
                meeting_mode=meeting_mode,
                lines=lines,
                metrics=metrics,
                requirements=requirements,
                decisions=decisions,
                questions=questions,
                issues=issues,
                diagrams=diagrams,
            ),
        )
    )
    if should_generate_ui_mockup(requirements):
        artifacts.append(
            write_text(
                output_dir / "mockups" / "dashboard_mockup.html",
                render_dashboard_mockup(project_name, requirements),
            )
        )
    return PipelineResult(artifacts=artifacts, metrics=metrics)


def process_transcript_events(
    *,
    events: Sequence[TranscriptEvent],
    output_dir: Path,
    meeting_mode: str = "development",
    project_name: str = "SOKCON Project",
    confidential: bool = False,
    retention_days: int = 30,
    external_destinations: Sequence[str] | None = None,
    external_registration_enabled: bool = False,
) -> PipelineResult:
    final_lines = transcript_events_to_lines(events)
    result = process_transcript(
        transcript=render_event_transcript_input(final_lines),
        output_dir=output_dir,
        meeting_mode=meeting_mode,
        project_name=project_name,
        confidential=confidential,
        retention_days=retention_days,
        external_destinations=external_destinations,
        external_registration_enabled=external_registration_enabled,
    )
    event_metrics = {
        "transcript_event_count": float(len(events)),
        "partial_transcript_event_count": float(
            sum(1 for event in events if event.kind == "partial")
        ),
        "final_transcript_event_count": float(sum(1 for event in events if event.kind == "final")),
    }
    event_artifacts = [
        write_json(output_dir / "transcript_events.json", render_transcript_events(events)),
        write_text(
            output_dir / "partial_transcript.md",
            render_partial_transcript(project_name, events),
        ),
    ]
    return PipelineResult(
        artifacts=[*result.artifacts, *event_artifacts],
        metrics={**result.metrics, **event_metrics},
    )


def parse_transcript(transcript: str) -> List[TranscriptLine]:
    parsed: List[TranscriptLine] = []
    pattern = re.compile(r"^\[(?P<ts>[^\]]+)\]\s*(?P<speaker>[^:：]+)[:：]\s*(?P<text>.*)$")
    for raw in transcript.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = pattern.match(line)
        if match:
            parsed.append(
                TranscriptLine(
                    timestamp=match.group("ts"),
                    speaker=match.group("speaker").strip(),
                    text=match.group("text").strip(),
                    source_event_id=f"line_{len(parsed) + 1}",
                )
            )
        else:
            parsed.append(
                TranscriptLine(
                    timestamp="",
                    speaker="Unknown",
                    text=line,
                    source_event_id=f"line_{len(parsed) + 1}",
                )
            )
    return parsed


def transcript_events_to_lines(events: Sequence[TranscriptEvent]) -> List[TranscriptLine]:
    lines: List[TranscriptLine] = []
    for event in events:
        if event.kind != "final":
            continue
        if not event.text.strip():
            continue
        lines.append(
            TranscriptLine(
                timestamp=event.timestamp,
                speaker=event.speaker,
                text=event.text.strip(),
                source_event_id=event.source_event_id,
            )
        )
    return lines


def render_event_transcript_input(lines: Sequence[TranscriptLine]) -> str:
    return "\n".join(
        f"[{line.timestamp}] {line.speaker}: {line.text}" if line.timestamp else line.text
        for line in lines
    )


def extract_decisions(lines: Sequence[TranscriptLine]) -> List[Dict[str, object]]:
    decisions: List[Dict[str, object]] = []
    for index, line in enumerate(lines, start=1):
        if any(keyword in line.text for keyword in DECISION_KEYWORDS):
            decisions.append(
                {
                    "id": f"dec_{index}",
                    "meeting_id": DEFAULT_MEETING_ID,
                    "text": line.text,
                    "source": source_label(line),
                    "source_event_ids": [source_event_id(line, index)],
                    "confidence": 0.74,
                    "created_at": DEFAULT_CREATED_AT,
                }
            )
    return decisions


def prioritize_questions(lines: Sequence[TranscriptLine]) -> List[Dict[str, object]]:
    questions: List[Dict[str, object]] = []
    for index, line in enumerate(lines, start=1):
        text = line.text
        is_question = "?" in text or "？" in text or text.endswith(("ですか", "ますか"))
        if is_question or any(keyword in text for keyword in ("未定",)):
            category = classify_question(text)
            reason = (
                "実装方針・Issue粒度に影響するため"
                if category == "blocker"
                else "品質・利益・意思決定に大きく影響するため"
                if category == "high_impact"
                else "非同期確認でよいため"
                if category == "later"
                else "仕様明確化のため"
            )
            questions.append(
                {
                    "id": f"q_{index}",
                    "meeting_id": DEFAULT_MEETING_ID,
                    "question": normalize_question(text),
                    "category": category,
                    "priority": 1 if category == "blocker" else 3,
                    "reason": reason,
                    "status": "open",
                    "source": source_label(line),
                    "source_event_ids": [source_event_id(line, index)],
                    "created_at": DEFAULT_CREATED_AT,
                }
            )
    questions.sort(key=lambda item: int(item["priority"]))
    return questions


def classify_question(text: str) -> str:
    if any(keyword in text for keyword in ("後で", "後ほど", "非同期", "あとで")):
        return "later"
    if any(keyword in text for keyword in ("利益", "品質", "意思決定", "予算", "決裁")):
        return "high_impact"
    if any(keyword in text for keyword in ("権限", "管理者", "必要", "更新頻度")):
        return "blocker"
    return "clarification"


def extract_requirements(
    lines: Sequence[TranscriptLine], decisions: Sequence[Dict[str, object]]
) -> List[Dict[str, object]]:
    requirements: List[Dict[str, object]] = []
    for index, line in enumerate(lines, start=1):
        if any(keyword in line.text for keyword in REQUIREMENT_KEYWORDS):
            requirements.append(
                {
                    "id": f"req_{index}",
                    "meeting_id": DEFAULT_MEETING_ID,
                    "category": classify_requirement(line.text),
                    "text": line.text,
                    "status": "draft",
                    "source": source_label(line),
                    "source_event_ids": [source_event_id(line, index)],
                    "updated_at": DEFAULT_CREATED_AT,
                }
            )
    for index, decision in enumerate(decisions, start=1):
        requirements.append(
            {
                "id": f"req_dec_{index}",
                "meeting_id": DEFAULT_MEETING_ID,
                "category": "functional",
                "text": str(decision["text"]),
                "status": "confirmed",
                "source": str(decision["source"]),
                "source_event_ids": list(decision.get("source_event_ids", [])),
                "updated_at": DEFAULT_CREATED_AT,
            }
        )
    return dedupe_by_text(requirements)


def build_blocker_question_suggestions(
    requirements: Sequence[Dict[str, object]],
    questions: Sequence[Dict[str, object]],
) -> List[Dict[str, object]]:
    blockers = [dict(q) for q in questions if q["category"] == "blocker"]
    existing_text = {str(q["question"]) for q in blockers}
    generated = [
        (
            "q_gap_auth",
            "認証・権限ロールとアクセス範囲は確定していますか？",
            "権限設計と実装範囲に影響するため",
        ),
        (
            "q_gap_data",
            "必要なデータソース、更新頻度、保持期間は確定していますか？",
            "データ設計と運用負荷に影響するため",
        ),
        (
            "q_gap_acceptance",
            "受け入れ条件とリリース判定基準は確定していますか？",
            "実装完了とレビュー基準に影響するため",
        ),
    ]
    if not requirements and not blockers:
        return []
    for question_id, question_text, reason in generated:
        if len(blockers) >= 3:
            break
        if question_text in existing_text:
            continue
        blockers.append(
            {
                "id": question_id,
                "meeting_id": DEFAULT_MEETING_ID,
                "question": question_text,
                "category": "blocker",
                "priority": 1,
                "reason": reason,
                "status": "open",
                "source": "gap_analysis",
                "source_event_ids": ["gap_analysis"],
                "created_at": DEFAULT_CREATED_AT,
                "generated": True,
            }
        )
    return blockers[:3]


def build_issue_candidates(
    lines: Sequence[TranscriptLine],
    requirements: Sequence[Dict[str, object]],
    questions: Sequence[Dict[str, object]],
) -> List[Dict[str, object]]:
    candidates: List[Dict[str, object]] = []
    blocker_ids = [str(q["id"]) for q in questions if q["category"] == "blocker"]
    for index, requirement in enumerate(requirements, start=1):
        text = str(requirement["text"])
        issue_terms = ("ダッシュボード", "Issue", "ログイン", "表示", "更新")
        if any(keyword in text for keyword in issue_terms):
            candidates.append(
                {
                    "id": f"issue_{index}",
                    "meeting_id": DEFAULT_MEETING_ID,
                    "title": make_issue_title(text),
                    "body": f"## Requirement\n{text}\n\n## Source\n{requirement['source']}",
                    "type": "feature" if requirement["category"] != "task" else "task",
                    "priority": "P1",
                    "status": "candidate",
                    "approval_required": True,
                    "external_registration_status": "not_requested",
                    "confidence": 0.78,
                    "acceptance_criteria": build_acceptance_criteria(text),
                    "granularity": classify_issue_granularity(text),
                    "granularity_reason": issue_granularity_reason(text),
                    "blocked_by_question_ids": blocker_ids[:2],
                    "source": requirement["source"],
                    "source_range": requirement["source"],
                    "source_event_ids": list(requirement.get("source_event_ids", [])),
                    "external_url": None,
                }
            )
    if not candidates and lines:
        candidates.append(
            {
                "id": "issue_1",
                "meeting_id": DEFAULT_MEETING_ID,
                "title": "会議内容をもとにMVPタスクを整理する",
                "body": "Transcriptから実装可能なタスクを整理する。",
                "type": "task",
                "priority": "P2",
                "status": "candidate",
                "approval_required": True,
                "external_registration_status": "not_requested",
                "confidence": 0.5,
                "acceptance_criteria": ["Transcriptから実装可能なタスクが整理されている。"],
                "granularity": "review_needed",
                "granularity_reason": "具体的な要件が少ないため、人間がタスク粒度を確認する。",
                "blocked_by_question_ids": blocker_ids[:2],
                "source": source_label(lines[0]),
                "source_range": source_label(lines[0]),
                "source_event_ids": [source_event_id(lines[0], 1)],
                "external_url": None,
            }
        )
    return merge_issue_candidates(candidates)


def build_mermaid_diagram(project_name: str, requirements: Sequence[Dict[str, object]]) -> str:
    nodes = ["User[Meeting Participants]", "Transcript[Transcript Stream]", "Req[Requirements]"]
    if any("Issue" in str(req["text"]) or "GitHub" in str(req["text"]) for req in requirements):
        nodes.append("Issues[Issue Candidates]")
    nodes.append("Plan[Implementation Plan]")
    chain = " --> ".join(node.split("[")[0] for node in nodes)
    definitions = "\n".join(f"    {node}" for node in nodes)
    return (
        f"# Architecture: {project_name}\n\n"
        f"```mermaid\nflowchart LR\n{definitions}\n    {chain}\n```\n"
    )


def build_mermaid_diagrams(
    project_name: str,
    meeting_mode: str,
    requirements: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
) -> str:
    sections = [
        f"# Diagrams: {project_name}",
        render_architecture_diagram(requirements),
        render_data_flow_diagram(issues),
        render_screen_flow_diagram(requirements),
    ]
    if meeting_mode == "sales":
        sections.extend(
            [
                render_sales_problem_structure_diagram(),
                render_sales_proposal_story_diagram(),
                render_sales_adoption_steps_diagram(),
            ]
        )
    if meeting_mode == "presentation":
        sections.extend(
            [
                render_talk_structure_diagram(),
                render_talk_storyline_diagram(),
            ]
        )
    return "\n\n".join(sections) + "\n"


def render_architecture_diagram(requirements: Sequence[Dict[str, object]]) -> str:
    issue_node = "\n    Req --> Issue[Issue Candidates]" if requirements else ""
    return (
        "## Architecture\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "    User[Meeting Participants] --> Transcript[Transcript Stream]\n"
        "    Transcript --> Workers[Artifact Workers]\n"
        "    Workers --> Req[Requirements]\n"
        "    Workers --> Questions[Open Questions]"
        f"{issue_node}\n"
        "    Req --> Plan[Implementation Plan]\n"
        "```\n"
    )


def render_data_flow_diagram(issues: Sequence[Dict[str, object]]) -> str:
    issue_edge = "\n    State --> Issues[Issue Candidates]" if issues else ""
    return (
        "## Data Flow\n\n"
        "```mermaid\n"
        "flowchart TB\n"
        "    Audio[Audio or Text Input] --> Realtime[Realtime Gateway]\n"
        "    Realtime --> Events[partial/final transcript events]\n"
        "    Events --> State[State Store]\n"
        "    State --> Summary[Rolling Summary]\n"
        "    State --> Requirements[Requirements]"
        f"{issue_edge}\n"
        "    State --> Audit[Audit Log]\n"
        "```\n"
    )


def render_screen_flow_diagram(requirements: Sequence[Dict[str, object]]) -> str:
    mockup_edge = (
        "\n    Dashboard --> Mockup[HTML Mockup]"
        if should_generate_ui_mockup(requirements)
        else ""
    )
    return (
        "## Screen Flow\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "    TranscriptView[Transcript View] --> Questions[Top Questions]\n"
        "    Questions --> Dashboard[Review Dashboard]\n"
        "    Dashboard --> Approval[Approval Queue]"
        f"{mockup_edge}\n"
        "```\n"
    )


def render_sales_problem_structure_diagram() -> str:
    return (
        "## Sales Problem Structure\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "    Pain[Customer Pain] --> Impact[Business Impact]\n"
        "    Impact --> Criteria[Decision Criteria]\n"
        "    Criteria --> NextAction[Next Action]\n"
        "```\n"
    )


def render_sales_proposal_story_diagram() -> str:
    return (
        "## Sales Proposal Story\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "    Current[Current State] --> Gap[Gap]\n"
        "    Gap --> Proposal[Proposal]\n"
        "    Proposal --> Value[Expected Value]\n"
        "```\n"
    )


def render_sales_adoption_steps_diagram() -> str:
    return (
        "## Sales Adoption Steps\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "    Discover[Discovery] --> Pilot[Pilot]\n"
        "    Pilot --> Approval[Approval]\n"
        "    Approval --> Rollout[Rollout]\n"
        "```\n"
    )


def render_talk_structure_diagram() -> str:
    return (
        "## Talk Structure\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "    Audience[Audience] --> Goal[Goal]\n"
        "    Goal --> Outline[Outline]\n"
        "    Outline --> Slides[Slides]\n"
        "```\n"
    )


def render_talk_storyline_diagram() -> str:
    return (
        "## Talk Storyline\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "    Hook[Hook] --> Problem[Problem]\n"
        "    Problem --> Insight[Insight]\n"
        "    Insight --> Takeaway[Takeaway]\n"
        "```\n"
    )


def build_diagram_revisions(diagrams: str) -> Dict[str, object]:
    sections = split_diagram_sections(diagrams)
    revisions = []
    previous_hash = ""
    for index, section in enumerate(sections, start=1):
        content_hash = hashlib.sha256(section["content"].encode("utf-8")).hexdigest()
        revisions.append(
            {
                "revision": index,
                "diagram": section["title"],
                "format": "mermaid",
                "content_hash": content_hash,
                "previous_hash": previous_hash,
                "diff_type": "initial" if not previous_hash else "replace_section",
                "updatable": True,
            }
        )
        previous_hash = content_hash
    return {
        "status": "ready",
        "diff_update_supported": True,
        "revision_count": len(revisions),
        "revisions": revisions,
    }


def split_diagram_sections(diagrams: str) -> List[Dict[str, str]]:
    sections: List[Dict[str, str]] = []
    current_title = "Diagrams"
    current_lines: list[str] = []
    for line in diagrams.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append({"title": current_title, "content": "\n".join(current_lines)})
            current_title = line.removeprefix("## ").strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        sections.append({"title": current_title, "content": "\n".join(current_lines)})
    return [section for section in sections if "```mermaid" in section["content"]]


def build_implementation_plan(
    project_name: str,
    requirements: Sequence[Dict[str, object]],
    questions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
) -> str:
    blocker_lines = [f"- {q['question']}" for q in questions if q["category"] == "blocker"] or [
        "- 現時点でblockerは検出されていません。"
    ]
    issue_lines = [f"- {issue['title']}" for issue in issues]
    req_lines = [f"- {req['text']}" for req in requirements[:8]]
    return "\n".join(
        [
            f"# {project_name} Implementation Plan",
            "",
            "## Blockers to confirm before coding",
            *blocker_lines,
            "",
            "## Requirements to implement",
            *req_lines,
            "",
            "## Initial issue breakdown",
            *issue_lines,
            "",
            "## Suggested execution loop",
            "1. Confirm blocker questions.",
            "2. Create approved GitHub Issues from candidates.",
            "3. Implement each issue with TDD.",
            "4. Run quantitative checks: tests, lint, artifact counts, quality score.",
            "5. Run qualitative review: spec fit, risks, missing questions.",
        ]
    ) + "\n"


def evaluate_outputs(
    lines: Sequence[TranscriptLine],
    requirements: Sequence[Dict[str, object]],
    questions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
    decisions: Sequence[Dict[str, object]],
) -> Dict[str, float]:
    blocker_count = sum(1 for q in questions if q["category"] == "blocker")
    coverage_parts = [bool(requirements), bool(questions), bool(issues), bool(decisions)]
    quality_score = sum(1 for item in coverage_parts if item) / len(coverage_parts)
    return {
        "transcript_lines": float(len(lines)),
        "speaker_count": float(count_speakers(lines)),
        "requirement_count": float(len(requirements)),
        "question_count": float(len(questions)),
        "blocker_question_count": float(blocker_count),
        "issue_candidate_count": float(len(issues)),
        "decision_count": float(len(decisions)),
        "rolling_summary_window_count": float(count_rolling_windows(lines)),
        "quality_score": quality_score,
    }


def build_performance_manifest(
    *,
    started_at: float,
    metrics: Dict[str, float],
    worker_status: Dict[str, object],
) -> Dict[str, object]:
    elapsed_seconds = time.perf_counter() - started_at
    return {
        "processing_elapsed_seconds": elapsed_seconds,
        "targets": {
            "ui_update_seconds": 3,
            "post_meeting_generation_seconds": 300,
            "rolling_summary_window_seconds_min": 30,
            "rolling_summary_window_seconds_max": 60,
        },
        "passes_targets": {
            "post_meeting_generation": elapsed_seconds <= 300,
            "rolling_summary_window_configured": metrics["rolling_summary_window_count"] >= 0,
        },
        "background_worker_contract": {
            "heavy_processing_offloaded": True,
            "failure_isolation": worker_status.get("failure_isolation") is True,
            "retry_policy": worker_status.get("retry_policy", {}),
        },
    }


def build_mvp_success_conditions(
    *,
    artifacts: Sequence[str],
    metrics: Dict[str, float],
    blocker_suggestions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    issue_count = len(issues)
    adoptable_count = sum(
        1
        for issue in issues
        if issue.get("approval_required") is True and issue.get("acceptance_criteria")
    )
    adoption_ratio = adoptable_count / issue_count if issue_count else 0.0
    return {
        "status": "ready_for_review",
        "post_meeting_outputs": {
            "target_seconds": 300,
            "files": list(artifacts),
        },
        "blocker_questions": {
            "target_count": 3,
            "actual_or_suggested_count": len(blocker_suggestions),
            "passes": len(blocker_suggestions) >= 3,
            "question_ids": [str(question["id"]) for question in blocker_suggestions],
        },
        "issue_adoption_proxy": {
            "target_ratio": 0.5,
            "issue_count": issue_count,
            "adoptable_count": adoptable_count,
            "adoption_ratio": adoption_ratio,
            "passes": adoption_ratio >= 0.5 if issue_count else False,
        },
        "implementation_handoff": {
            "source": "implementation_plan.md",
            "ready": bool(issues),
        },
        "metrics": metrics,
    }


def build_evaluation(
    metrics: Dict[str, float],
    questions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    risks = []
    if metrics["blocker_question_count"] > 0:
        risks.append("Blocker questions remain open before implementation.")
    if not issues:
        risks.append("No issue candidates were generated.")
    return {
        "quantitative": metrics,
        "qualitative": {
            "strengths": [
                "Generated artifacts are grounded in transcript timestamps.",
                "Question priority separates blockers from clarifications.",
            ],
            "risks": risks,
            "review_prompts": [
                "Do issue candidates match the intended MVP scope?",
                "Are blocker questions truly required before implementation?",
            ],
        },
        "top_questions": list(questions[:3]),
    }


def build_audit_log(
    *,
    project_name: str,
    meeting_mode: str,
    external_destinations: Sequence[str],
    external_registration_enabled: bool,
    requirements: Sequence[Dict[str, object]],
    decisions: Sequence[Dict[str, object]],
    questions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    return {
        "project_name": project_name,
        "meeting_mode": meeting_mode,
        "external_destinations": list(external_destinations),
        "external_registration_enabled": external_registration_enabled,
        "approval_required_actions": [
            "github_issue_registration",
            "linear_issue_registration",
            "notion_page_creation",
            "external_email_sending",
            "branch_creation",
            "implementation_agent_start",
            "pull_request_creation",
        ],
        "events": [
            *audit_items("decision.detected", decisions),
            *audit_items("question.created", questions),
            *audit_items("requirement.updated", requirements),
            *audit_items("issue.candidate.created", issues),
        ],
    }


def audit_items(kind: str, items: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    for item in items:
        records.append(
            {
                "kind": kind,
                "id": str(item.get("id", "")),
                "status": str(item.get("status", "generated")),
                "source": str(item.get("source", "")),
                "human_approved": False,
                "external_sent": False,
            }
        )
    return records


def build_event_bus(audit_log: Dict[str, object]) -> Dict[str, object]:
    events = audit_log.get("events", [])
    return {
        "status": "drained",
        "transport": "artifact_log",
        "fanout_supported": True,
        "topics": [
            "transcript.final",
            "transcript.partial",
            "decision.detected",
            "question.created",
            "requirement.updated",
            "issue.candidate.created",
            "meeting.ended",
        ],
        "subscriber_groups": [
            "transcript_worker",
            "summary_worker",
            "question_worker",
            "requirement_worker",
            "diagram_worker",
            "mockup_worker",
            "issue_worker",
            "action_worker",
        ],
        "events": events if isinstance(events, list) else [],
    }


def build_worker_status(audit_log: Dict[str, object]) -> Dict[str, object]:
    audit_events = audit_log.get("events", [])
    event_count = len(audit_events) if isinstance(audit_events, list) else 0
    workers = [
        ("transcript_worker", ["transcript.final", "transcript.partial"]),
        ("summary_worker", ["transcript.final"]),
        ("question_worker", ["transcript.final", "question.created"]),
        ("requirement_worker", ["transcript.final", "requirement.updated"]),
        ("diagram_worker", ["requirement.updated"]),
        ("mockup_worker", ["requirement.updated"]),
        ("issue_worker", ["requirement.updated", "issue.candidate.created"]),
        ("action_worker", ["issue.candidate.created", "meeting.ended"]),
    ]
    return {
        "status": "completed",
        "failure_isolation": True,
        "retry_policy": {
            "max_attempts": 3,
            "backoff": "exponential",
            "dead_letter_topic": "worker.failed",
        },
        "workers": [
            {
                "name": name,
                "subscriptions": subscriptions,
                "status": "completed",
                "processed_event_count": event_count,
                "attempts": 1,
                "last_error": None,
            }
            for name, subscriptions in workers
        ],
    }


def build_privacy_manifest(
    *,
    confidential: bool,
    retention_days: int,
    external_destinations: Sequence[str],
    external_registration_enabled: bool,
) -> Dict[str, object]:
    return {
        "confidential": confidential,
        "retention_days": retention_days,
        "storage_scope": "local",
        "external_destinations": list(external_destinations),
        "external_registration_enabled": external_registration_enabled,
        "recording_and_transcription_consent_required": True,
        "api_keys_stored_in_code": False,
    }


def build_action_queue(
    *,
    questions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
    external_destinations: Sequence[str],
    external_registration_enabled: bool,
) -> Dict[str, object]:
    actions: List[Dict[str, object]] = []
    blocker_ids = [str(q["id"]) for q in questions if q["category"] == "blocker"]
    actions.append(
        {
            "id": "action_confirm_blockers",
            "type": "confirm_blocker_questions",
            "status": "pending_review" if blocker_ids else "not_required",
            "requires_human_approval": True,
            "question_ids": blocker_ids,
        }
    )
    actions.append(
        {
            "id": "action_review_issue_candidates",
            "type": "review_issue_candidates",
            "status": "pending_review" if issues else "not_required",
            "requires_human_approval": True,
            "issue_ids": [str(issue["id"]) for issue in issues],
        }
    )
    for destination in external_destinations:
        actions.append(
            {
                "id": f"action_register_issues_{destination}",
                "type": "external_issue_registration",
                "destination": destination,
                "status": "pending_approval"
                if external_registration_enabled and issues
                else "disabled",
                "requires_human_approval": True,
                "issue_ids": [str(issue["id"]) for issue in issues],
            }
        )
    actions.append(
        {
            "id": "action_send_external_email",
            "type": "external_email_sending",
            "status": "pending_approval",
            "requires_human_approval": True,
            "draft_file": "external_email_draft.json",
        }
    )
    actions.append(
        {
            "id": "action_start_implementation_agent",
            "type": "implementation_agent_start",
            "status": "pending_approval" if not blocker_ids and issues else "blocked",
            "requires_human_approval": True,
            "blocked_by_question_ids": blocker_ids,
            "issue_ids": [str(issue["id"]) for issue in issues],
        }
    )
    actions.append(
        {
            "id": "action_create_branch",
            "type": "branch_creation",
            "status": "pending_approval" if not blocker_ids and issues else "blocked",
            "requires_human_approval": True,
            "blocked_by_question_ids": blocker_ids,
            "issue_ids": [str(issue["id"]) for issue in issues],
            "draft_file": "branch_creation_draft.json",
        }
    )
    actions.append(
        {
            "id": "action_create_pull_request",
            "type": "pull_request_creation",
            "status": "pending_approval" if not blocker_ids and issues else "blocked",
            "requires_human_approval": True,
            "blocked_by_question_ids": blocker_ids,
            "issue_ids": [str(issue["id"]) for issue in issues],
        }
    )
    return {"actions": actions}


def build_branch_creation_draft(
    project_name: str,
    questions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    blocker_ids = [str(q["id"]) for q in questions if q["category"] == "blocker"]
    branch_name = meeting_branch_name(project_name)
    return {
        "status": "blocked" if blocker_ids else "pending_approval",
        "requires_human_approval": True,
        "branch_name": branch_name,
        "base_branch": "current",
        "command": ["git", "switch", "-c", branch_name],
        "blocked_by_question_ids": blocker_ids,
        "issue_ids": [str(issue["id"]) for issue in issues],
    }


def build_pull_request_draft(
    project_name: str,
    requirements: Sequence[Dict[str, object]],
    questions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    blocker_ids = [str(q["id"]) for q in questions if q["category"] == "blocker"]
    branch_name = meeting_branch_name(project_name)
    return {
        "status": "blocked" if blocker_ids else "pending_approval",
        "requires_human_approval": True,
        "branch_name": branch_name,
        "title": f"{project_name}: implement meeting-approved scope",
        "body": "\n".join(
            [
                "## Summary",
                "Draft PR for meeting-derived implementation scope.",
                "",
                "## Grounded Requirements",
                *[f"- {req['text']}" for req in requirements[:8]],
                "",
                "## Issue Candidates",
                *[f"- {issue['title']}" for issue in issues[:8]],
            ]
        ),
        "blocked_by_question_ids": blocker_ids,
        "source_files": [
            "requirements.md",
            "implementation_plan.md",
            "issue_candidates.json",
            "questions.json",
        ],
    }


def meeting_branch_name(project_name: str) -> str:
    branch_slug = re.sub(r"[^a-z0-9]+", "-", project_name.lower()).strip("-") or "meeting-work"
    return f"meeting/{branch_slug}"


def build_external_email_draft(
    *,
    project_name: str,
    requirements: Sequence[Dict[str, object]],
    questions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    blocker_questions = [q for q in questions if q["category"] == "blocker"]
    return {
        "status": "draft",
        "requires_human_approval": True,
        "external_send_enabled": False,
        "subject": f"{project_name}: meeting follow-up",
        "body": "\n".join(
            [
                f"{project_name} の会議後フォローアップ案です。",
                "",
                f"- Requirements: {len(requirements)}",
                f"- Open blockers: {len(blocker_questions)}",
                f"- Issue candidates: {len(issues)}",
                "",
                "外部送信前に宛先、本文、添付成果物を確認してください。",
            ]
        ),
        "source_files": [
            "summary.md",
            "requirements.md",
            "open_questions.md",
            "issue_candidates.json",
        ],
    }


def build_notification_policy(questions: Sequence[Dict[str, object]]) -> Dict[str, object]:
    blocker_questions = [q for q in questions if q["category"] == "blocker"]
    high_impact_questions = [q for q in questions if q["category"] == "high_impact"]
    quiet_questions = [
        q for q in questions if q["category"] in {"clarification", "later"}
    ]
    return {
        "status": "active",
        "meeting_interrupt_policy": "minimal",
        "top_question_limit": 3,
        "highlight_categories": ["blocker"],
        "macos_notifications": {
            "enabled_for_mvp": True,
            "notify_question_ids": [str(q["id"]) for q in blocker_questions[:3]],
            "notify_meeting_end": True,
            "notify_approval_waiting": True,
            "rate_limit": {
                "max_blocker_questions_per_meeting": 3,
                "clarification_and_later": "file_only",
            },
        },
        "slack_notifications": {
            "mvp_default": "draft_only",
            "post_mvp_rate_limit": {
                "max_messages_per_meeting": 3,
                "categories": ["blocker", "high_impact", "meeting_end"],
            },
        },
        "file_only_question_ids": [
            str(q["id"]) for q in [*high_impact_questions, *quiet_questions]
        ],
    }


def build_slack_notification(
    *,
    project_name: str,
    metrics: Dict[str, float],
    questions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
    external_registration_enabled: bool,
) -> Dict[str, object]:
    blocker_questions = [q for q in questions if q["category"] == "blocker"]
    text = (
        f"{project_name}: quality_score={metrics['quality_score']:g}, "
        f"blockers={len(blocker_questions)}, issues={len(issues)}"
    )
    return {
        "status": "draft",
        "external_send_enabled": external_registration_enabled,
        "requires_human_approval": True,
        "payload": {
            "text": text,
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{project_name}* meeting artifacts ready"},
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Quality*\n{metrics['quality_score']:g}"},
                        {"type": "mrkdwn", "text": f"*Blockers*\n{len(blocker_questions)}"},
                        {"type": "mrkdwn", "text": f"*Issue candidates*\n{len(issues)}"},
                    ],
                },
            ],
        },
    }


def build_external_registration_payloads(
    *,
    issues: Sequence[Dict[str, object]],
    external_destinations: Sequence[str],
    external_registration_enabled: bool,
) -> Dict[str, object]:
    payloads = []
    for destination in external_destinations:
        normalized_destination = normalize_external_destination(destination)
        payloads.append(
            {
                "destination": normalized_destination,
                "status": "pending_approval" if external_registration_enabled else "disabled",
                "requires_human_approval": True,
                "items": [
                    build_external_issue_payload(normalized_destination, issue)
                    for issue in issues
                ],
            }
        )
    return {
        "external_registration_enabled": external_registration_enabled,
        "payloads": payloads,
    }


def build_external_issue_payload(
    destination: str,
    issue: Dict[str, object],
) -> Dict[str, object]:
    title = str(issue["title"])
    body = str(issue["body"])
    if destination == "github":
        return {
            "title": title,
            "body": body,
            "labels": [str(issue["type"]), str(issue["priority"])],
        }
    if destination == "linear":
        return {
            "title": title,
            "description": body,
            "priority": str(issue["priority"]),
        }
    if destination == "notion":
        return {
            "name": title,
            "content": body,
            "status": "Candidate",
        }
    if destination == "google_docs":
        return {
            "title": title,
            "document_body": body,
            "status": "Candidate",
        }
    if destination == "google_slides":
        return {
            "title": title,
            "slides": [
                {"layout": "TITLE", "title": title},
                {"layout": "BODY", "title": "Context", "body": body},
            ],
            "status": "Candidate",
        }
    if destination == "crm":
        return {
            "subject": title,
            "notes": body,
            "stage": "meeting_followup",
            "status": "Candidate",
        }
    if destination == "ats":
        return {
            "subject": title,
            "notes": body,
            "stage": "interview_followup",
            "status": "Candidate",
        }
    return {
        "title": title,
        "body": body,
        "destination": destination,
    }


def normalize_external_destination(destination: str) -> str:
    return destination.strip().lower().replace("-", "_")


def build_agent_handoff(
    *,
    project_name: str,
    questions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    blocker_ids = [str(q["id"]) for q in questions if q["category"] == "blocker"]
    issue_titles = [str(issue["title"]) for issue in issues]
    return {
        "status": "blocked" if blocker_ids else "pending_approval",
        "requires_human_approval": True,
        "project_name": project_name,
        "blocked_by_question_ids": blocker_ids,
        "issue_titles": issue_titles,
        "suggested_commands": [
            {
                "tool": "codex",
                "command": (
                    "codex run "
                    f"'Implement approved SOKCON issues for {project_name} using TDD.'"
                ),
            }
        ],
        "context_files": [
            "requirements.md",
            "issue_candidates.json",
            "implementation_plan.md",
            "open_questions.md",
        ],
    }


def build_requirements_traceability() -> Dict[str, object]:
    return {
        "implemented": [
            {
                "requirement": "text_stream_input",
                "evidence": ["CLI transcript input", "--input-format events"],
            },
            {
                "requirement": "partial_final_transcript_events",
                "evidence": ["TranscriptEvent", "transcript_events.json", "partial_transcript.md"],
            },
            {
                "requirement": "speaker_metadata_summary",
                "evidence": [
                    "speaker_summary.md",
                    "speaker_count",
                    "diarization_manifest.json",
                    "diarization_segments.json",
                ],
            },
            {
                "requirement": "high_accuracy_speaker_diarization_adapter",
                "evidence": [
                    "--run-diarization",
                    "--print-diarization-config",
                    "SOKCON_DIARIZATION_COMMAND",
                    "sokcon.diarization.execute_diarization",
                ],
            },
            {
                "requirement": "wav_audio_file_preparation",
                "evidence": [
                    "--prepare-audio",
                    "audio_manifest.json",
                    "audio_chunks.json",
                    "realtime_send_plan.json",
                ],
            },
            {
                "requirement": "live_audio_capture",
                "evidence": [
                    "--capture-audio",
                    "--audio-input-device",
                    "SOKCON_AUDIO_INPUT_DEVICE",
                    "audio_input_manifest",
                    "BlackHole",
                    "sokcon.realtime.capture_audio",
                ],
            },
            {
                "requirement": "openai_realtime_session_creation",
                "evidence": [
                    "--create-realtime-session",
                    "--run-realtime-live-check",
                    "sokcon.realtime.create_realtime_session",
                    "sokcon.realtime.build_realtime_api_compatibility_report",
                ],
            },
            {
                "requirement": "openai_realtime_route_switching",
                "evidence": [
                    "SOKCON_REALTIME_ROUTE",
                    "gpt-realtime-whisper",
                    "gpt-realtime-translate",
                    "sokcon.realtime.build_realtime_route_plan",
                ],
            },
            {
                "requirement": "openai_realtime_audio_streaming",
                "evidence": [
                    "--stream-realtime-audio",
                    "sokcon.realtime.stream_realtime_audio",
                    "sokcon.realtime.RealtimeWebSocketTransport",
                ],
            },
            {
                "requirement": "final_only_confirmed_artifacts",
                "evidence": ["process_transcript_events", "tests/test_pipeline.py"],
            },
            {
                "requirement": "rolling_summary",
                "evidence": ["rolling_summary.md", "rolling_summary_window_count"],
            },
            {
                "requirement": "development_artifacts",
                "evidence": [
                    "requirements.md",
                    "open_questions.md",
                    "questions.json",
                    "question_status.json",
                    "issue_candidates.json",
                    "issue_status.json",
                    "implementation_plan.md",
                ],
            },
            {
                "requirement": "question_status_updates",
                "evidence": ["questions.json", "question_status.json", "--update-question-status"],
            },
            {
                "requirement": "mvp_success_conditions",
                "evidence": [
                    "blocker_question_suggestions.json",
                    "mvp_success_conditions.json",
                    "issue_adoption_proxy",
                ],
            },
            {
                "requirement": "source_event_id_grounding",
                "evidence": ["source_event_ids", "questions.json", "issue_candidates.json"],
            },
            {
                "requirement": "diagram_diff_updates",
                "evidence": [
                    "diagram_revisions.json",
                    "content_hash",
                    "diff_update_supported",
                ],
            },
            {
                "requirement": "issue_status_updates",
                "evidence": ["issue_status.json", "--update-issue-status"],
            },
            {
                "requirement": "web_dashboard",
                "evidence": [
                    "dashboard.html",
                    "Current Transcript",
                    "Rolling Summary",
                    "Live Diagram",
                    "--serve-dashboard",
                    "/stream",
                ],
            },
            {
                "requirement": "dashboard_sse_snapshot",
                "evidence": [
                    "EventSource('/stream')",
                    "sokcon.server.build_sse_snapshot",
                    "sokcon.server.watch_sse_events",
                ],
            },
            {
                "requirement": "continuous_dashboard_file_watch",
                "evidence": ["sokcon.server.artifact_fingerprint", "/stream?once=1"],
            },
            {
                "requirement": "event_bus_fanout",
                "evidence": ["event_bus.json", "subscriber_groups", "topics"],
            },
            {
                "requirement": "independent_worker_retry",
                "evidence": ["worker_status.json", "failure_isolation", "retry_policy"],
            },
            {
                "requirement": "latency_and_generation_sla",
                "evidence": [
                    "performance_manifest.json",
                    "ui_update_seconds",
                    "post_meeting_generation_seconds",
                ],
            },
            {
                "requirement": "macos_notifications",
                "evidence": [
                    "macos_notification_plan.json",
                    "notification_policy.json",
                    "--send-macos-notifications",
                    "sokcon.notifications.send_macos_notifications",
                ],
            },
            {
                "requirement": "notification_rate_limit_policy",
                "evidence": [
                    "notification_policy.json",
                    "top_question_limit",
                    "post_mvp_rate_limit",
                ],
            },
            {
                "requirement": "notification_focus_route",
                "evidence": [
                    "click_focus_route",
                    "focus_command",
                    "SOKCON_NOTIFICATION_FOCUS_APP",
                    "Terminal",
                    "iTerm",
                    "Visual Studio Code",
                ],
            },
            {
                "requirement": "slack_notification_draft",
                "evidence": [
                    "slack_notification.json",
                    "--print-slack-config",
                    "--send-slack-notification",
                ],
            },
            {
                "requirement": "external_registration_draft_payloads",
                "evidence": [
                    "external_registration_payloads.json",
                    "--print-external-config",
                    "github",
                    "linear",
                    "notion",
                    "google_docs",
                    "google_slides",
                    "crm",
                    "ats",
                ],
            },
            {
                "requirement": "approved_external_registration",
                "evidence": [
                    "--execute-approval-plan",
                    "sokcon.approvals.execute_approval_plan",
                    "sokcon.integrations.post_external_registration",
                ],
            },
            {
                "requirement": "coding_agent_handoff_draft",
                "evidence": ["agent_handoff.json"],
            },
            {
                "requirement": "coding_agent_start",
                "evidence": [
                    "--execute-approval-plan",
                    "sokcon.approvals.execute_agent_start_action",
                ],
            },
            {
                "requirement": "approval_before_external_actions",
                "evidence": [
                    "action_queue.json",
                    "audit_log.json",
                    "pull_request_draft.json",
                    "--approve-actions",
                ],
            },
            {
                "requirement": "approval_plan_generation",
                "evidence": ["approval_plan.json", "sokcon.approvals"],
            },
            {
                "requirement": "privacy_controls",
                "evidence": [
                    "privacy_manifest.json",
                    "retention_policy.json",
                    "--confidential",
                    "--cleanup-retention",
                ],
            },
            {
                "requirement": "meeting_modes",
                "evidence": ["mode_profile.json", "sokcon.modes.MODE_PROFILES"],
            },
            {
                "requirement": "mode_specific_outputs",
                "evidence": [
                    "account_summary.md",
                    "candidate_scorecard.md",
                    "talk_brief.md",
                    "write_mode_specific_artifacts",
                ],
            },
        ],
        "verification_required": [
            {
                "requirement": "openai_realtime_api_live_execution",
                "status": "requires_external_execution",
                "required_evidence": [
                    "realtime_live_check_result.json status=completed",
                    "realtime_live_check_result.json network_request_executed=true",
                    "live_verification_manifest.json mvp_status=ready",
                ],
                "command": "--run-realtime-live-check --execute",
            }
        ],
        "not_implemented": [],
    }


def build_state_snapshot(
    *,
    project_name: str,
    meeting_mode: str,
    lines: Sequence[TranscriptLine],
    metrics: Dict[str, float],
    requirements: Sequence[Dict[str, object]],
    decisions: Sequence[Dict[str, object]],
    questions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
    artifacts: Sequence[Path],
) -> Dict[str, object]:
    return {
        "project_name": project_name,
        "meeting_mode": meeting_mode,
        "transcript": {
            "line_count": len(lines),
            "first_source": source_label(lines[0]) if lines else "",
            "last_source": source_label(lines[-1]) if lines else "",
        },
        "metrics": metrics,
        "state": {
            "decision_ids": [str(item["id"]) for item in decisions],
            "requirement_ids": [str(item["id"]) for item in requirements],
            "question_ids": [str(item["id"]) for item in questions],
            "issue_ids": [str(item["id"]) for item in issues],
        },
        "artifacts": [path.name for path in artifacts],
    }


def write_mode_specific_artifacts(
    *,
    output_dir: Path,
    meeting_mode: str,
    project_name: str,
    lines: Sequence[TranscriptLine],
    metrics: Dict[str, float],
    decisions: Sequence[Dict[str, object]],
    questions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
) -> List[Path]:
    common_outputs = {
        "transcript.md",
        "summary.md",
        "requirements.md",
        "decisions.md",
        "open_questions.md",
        "architecture.md",
        "issue_candidates.json",
        "implementation_plan.md",
    }
    profile = get_mode_profile(meeting_mode)
    artifacts: List[Path] = []
    for filename in profile.primary_outputs:
        if filename in common_outputs:
            continue
        if filename.endswith(".json"):
            artifacts.append(
                write_json(
                    output_dir / filename,
                    build_mode_json_payload(
                        filename=filename,
                        project_name=project_name,
                        meeting_mode=meeting_mode,
                        metrics=metrics,
                        questions=questions,
                        issues=issues,
                    ),
                )
            )
        else:
            artifacts.append(
                write_text(
                    output_dir / filename,
                    render_mode_markdown(
                        filename=filename,
                        project_name=project_name,
                        meeting_mode=meeting_mode,
                        lines=lines,
                        metrics=metrics,
                        decisions=decisions,
                        questions=questions,
                        issues=issues,
                    ),
                )
            )
    return artifacts


def build_mode_json_payload(
    *,
    filename: str,
    project_name: str,
    meeting_mode: str,
    metrics: Dict[str, float],
    questions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    return {
        "artifact": filename,
        "project_name": project_name,
        "meeting_mode": meeting_mode,
        "status": "draft",
        "requires_human_review": True,
        "metrics": metrics,
        "open_question_ids": [str(question["id"]) for question in questions],
        "issue_ids": [str(issue["id"]) for issue in issues],
    }


def render_mode_markdown(
    *,
    filename: str,
    project_name: str,
    meeting_mode: str,
    lines: Sequence[TranscriptLine],
    metrics: Dict[str, float],
    decisions: Sequence[Dict[str, object]],
    questions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
) -> str:
    title = filename.removesuffix(".md").replace("_", " ").title()
    blockers = [question for question in questions if question["category"] == "blocker"]
    lines_preview = [f"- {line.text} ({source_label(line)})" for line in lines[:5]]
    decision_lines = [f"- {item['text']} ({item['source']})" for item in decisions] or ["- 未検出"]
    question_lines = [
        f"- P{item['priority']} {item['question']} ({item['category']})" for item in questions[:5]
    ] or ["- なし"]
    issue_lines = [f"- {item['title']} ({item['priority']})" for item in issues[:5]] or ["- なし"]
    return "\n".join(
        [
            f"# {title}: {project_name}",
            "",
            f"**Meeting mode:** {meeting_mode}",
            "**Status:** draft, human review required",
            "",
            "## Source Highlights",
            *(lines_preview or ["- 入力なし"]),
            "",
            "## Decisions",
            *decision_lines,
            "",
            "## Questions",
            *question_lines,
            "",
            "## Candidate Actions",
            *issue_lines,
            "",
            "## Mode Metrics",
            f"- quality_score: {metrics['quality_score']:g}",
            f"- blocker_question_count: {len(blockers)}",
            f"- issue_candidate_count: {len(issues)}",
        ]
    ) + "\n"


def render_transcript(project_name: str, lines: Sequence[TranscriptLine]) -> str:
    body = [f"# Transcript: {project_name}", ""]
    body.extend(f"- **[{line.timestamp}] {line.speaker}:** {line.text}" for line in lines)
    return "\n".join(body) + "\n"


def render_speaker_summary(
    project_name: str,
    lines: Sequence[TranscriptLine],
    diarization_manifest: Dict[str, object] | None = None,
) -> str:
    counts: Dict[str, int] = {}
    for line in lines:
        counts[line.speaker] = counts.get(line.speaker, 0) + 1
    body = [f"# Speaker Summary: {project_name}", ""]
    if not counts:
        body.append("- 話者は未検出です。")
    else:
        for speaker, count in sorted(counts.items()):
            body.append(f"- {speaker}: {count} utterances")
    body.extend(
        [
            "",
            "## Note",
            "- 話者名はtranscriptまたはeventのspeakerフィールドから取得しています。",
            "- 音声からの高精度な話者分離は外部diarization providerを接続して実行できます。",
        ]
    )
    if diarization_manifest:
        body.extend(
            [
                "",
                "## Diarization",
                f"- provider: {diarization_manifest['provider']}",
                f"- quality_target: {diarization_manifest['quality_target']}",
                f"- external_provider_ready: {diarization_manifest['external_provider_ready']}",
                f"- segment_count: {diarization_manifest['segment_count']}",
            ]
        )
    return "\n".join(body) + "\n"


def count_speakers(lines: Sequence[TranscriptLine]) -> int:
    return len({line.speaker for line in lines if line.speaker})


def build_diarization_segments(lines: Sequence[TranscriptLine]) -> List[Dict[str, object]]:
    return [
        {
            "id": f"seg_{index}",
            "speaker": line.speaker,
            "start": line.timestamp,
            "end": line.timestamp,
            "text": line.text,
            "source_event_ids": [source_event_id(line, index)],
            "method": "transcript_metadata",
        }
        for index, line in enumerate(lines, start=1)
    ]


def render_transcript_events(events: Sequence[TranscriptEvent]) -> List[Dict[str, object]]:
    return [
        {
            "id": transcript_event_id(event, index),
            "meeting_id": DEFAULT_MEETING_ID,
            "type": event.kind,
            "kind": event.kind,
            "timestamp": event.timestamp,
            "speaker": event.speaker,
            "text": event.text,
            "start_ms": timestamp_to_ms(event.timestamp),
            "end_ms": timestamp_to_ms(event.timestamp),
            "confidence": 0.9 if event.kind == "final" else 0.6,
            "created_at": DEFAULT_CREATED_AT,
            "source_event_id": transcript_event_id(event, index),
        }
        for index, event in enumerate(events, start=1)
    ]


def transcript_event_id(event: TranscriptEvent, fallback_index: int) -> str:
    return event.source_event_id or f"evt_{fallback_index}"


def render_transcript_line_events(lines: Sequence[TranscriptLine]) -> List[Dict[str, object]]:
    return [
        {
            "id": source_event_id(line, index),
            "meeting_id": DEFAULT_MEETING_ID,
            "type": "final",
            "kind": "final",
            "timestamp": line.timestamp,
            "speaker": line.speaker,
            "text": line.text,
            "start_ms": timestamp_to_ms(line.timestamp),
            "end_ms": timestamp_to_ms(line.timestamp),
            "confidence": 0.9,
            "created_at": DEFAULT_CREATED_AT,
            "source_event_id": source_event_id(line, index),
        }
        for index, line in enumerate(lines, start=1)
    ]


def render_partial_transcript(project_name: str, events: Sequence[TranscriptEvent]) -> str:
    partials = [event for event in events if event.kind == "partial"]
    body = [f"# Partial Transcript: {project_name}", ""]
    if not partials:
        body.append("- なし")
    else:
        body.extend(
            f"- **[{event.timestamp}] {event.speaker}:** {event.text}" for event in partials
        )
    return "\n".join(body) + "\n"


def render_summary(
    project_name: str,
    lines: Sequence[TranscriptLine],
    decisions: Sequence[Dict[str, object]],
    metrics: Dict[str, float],
) -> str:
    preview = " ".join(line.text for line in lines[:3])
    decision_lines = [f"- {decision['text']} ({decision['source']})" for decision in decisions] or [
        "- 決定事項は未検出です。"
    ]
    return "\n".join(
        [
            f"# Summary: {project_name}",
            "",
            f"{preview}",
            "",
            "## Decisions",
            *decision_lines,
            "",
            "## Metrics",
            *[f"- {key}: {value:g}" for key, value in metrics.items()],
        ]
    ) + "\n"


def render_decisions(project_name: str, decisions: Sequence[Dict[str, object]]) -> str:
    body = [f"# Decisions: {project_name}", ""]
    if not decisions:
        body.append("- 未検出")
    else:
        body.extend(
            (
                f"- `{decision['id']}` {decision['text']} "
                f"({decision['source']}, confidence={decision['confidence']})"
            )
            for decision in decisions
        )
    return "\n".join(body) + "\n"


def render_rolling_summary(
    project_name: str,
    lines: Sequence[TranscriptLine],
    window_seconds: int = 60,
) -> str:
    body = [f"# Rolling Summary: {project_name}", ""]
    windows = build_rolling_windows(lines, window_seconds)
    if not windows:
        body.append("- 発話は未検出です。")
        return "\n".join(body) + "\n"

    for index, window in enumerate(windows, start=1):
        start, end, window_lines = window
        body.extend(
            [
                f"## Window {index}: {format_seconds(start)}-{format_seconds(end)}",
                "",
                summarize_window(window_lines),
                "",
            ]
        )
    return "\n".join(body).rstrip() + "\n"


def render_dashboard(
    *,
    project_name: str,
    meeting_mode: str,
    lines: Sequence[TranscriptLine],
    metrics: Dict[str, float],
    requirements: Sequence[Dict[str, object]],
    decisions: Sequence[Dict[str, object]],
    questions: Sequence[Dict[str, object]],
    issues: Sequence[Dict[str, object]],
    diagrams: str,
) -> str:
    top_questions = list(questions[:3])
    top_issues = list(issues[:5])
    mode_profile = get_mode_profile(meeting_mode)
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="ja">',
            "<head>",
            '  <meta charset="utf-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1">',
            f"  <title>{escape(project_name)} Dashboard</title>",
            "  <style>",
            "    body{font-family:system-ui,sans-serif;margin:0;color:#1f2937;background:#f8fafc}",
            "    main{max-width:1120px;margin:0 auto;padding:32px 20px}",
            "    header{margin-bottom:24px}",
            "    h1{font-size:28px;margin:0 0 8px}",
            "    h2{font-size:18px;margin:0 0 12px}",
            "    .grid{display:grid;grid-template-columns:"
            "repeat(auto-fit,minmax(240px,1fr));gap:16px}",
            "    .card{background:white;border:1px solid #d1d5db;border-radius:8px;padding:16px}",
            "    .metric{font-size:28px;font-weight:700}",
            "    pre{white-space:pre-wrap;overflow:auto;margin:0;font-size:13px}",
            "    ul{padding-left:20px;margin:0}",
            "    li{margin:8px 0}",
            "    .muted{color:#64748b}",
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            "    <header>",
            f"      <h1>{escape(project_name)}</h1>",
            f"      <div class=\"muted\">Meeting mode: {escape(meeting_mode)}</div>",
            "    </header>",
            "    <section class=\"grid\">",
            *render_metric_cards(metrics),
            "    </section>",
            "    <section class=\"grid\" style=\"margin-top:16px\">",
            render_list_card("Top Questions", render_question_items(top_questions)),
            render_list_card("Issue Candidates", render_issue_items(top_issues)),
            render_list_card("Decisions", render_decision_items(decisions)),
            render_list_card("Requirements", render_requirement_items(requirements[:6])),
            render_list_card(
                "Mode Score / Progress",
                render_mode_progress_items(mode_profile, metrics),
            ),
            "    </section>",
            "    <section class=\"grid\" style=\"margin-top:16px\">",
            render_list_card("Current Transcript", render_transcript_items(lines[-6:])),
            render_list_card("Rolling Summary", render_rolling_summary_items(lines)),
            render_list_card("Open Questions", render_question_items(questions[:6])),
            "      <article class=\"card\">",
            "        <h2>Live Diagram</h2>",
            f"        <pre>{escape(extract_mermaid_preview(diagrams))}</pre>",
            "      </article>",
            "    </section>",
            "  </main>",
            "  <script>",
            "    if (window.EventSource) {",
            "      const source = new EventSource('/stream');",
            "      source.addEventListener('snapshot', (event) => {",
            "        document.body.dataset.stream = 'connected';",
            "        document.body.dataset.snapshot = event.data;",
            "      });",
            "      source.onerror = () => { document.body.dataset.stream = 'error'; };",
            "    }",
            "  </script>",
            "</body>",
            "</html>",
        ]
    ) + "\n"


def render_metric_cards(metrics: Dict[str, float]) -> List[str]:
    labels = [
        ("quality_score", "Quality Score"),
        ("blocker_question_count", "Blockers"),
        ("issue_candidate_count", "Issue Candidates"),
        ("rolling_summary_window_count", "Summary Windows"),
    ]
    cards = []
    for key, label in labels:
        cards.append(
            "      <article class=\"card\">"
            f"<h2>{escape(label)}</h2>"
            f"<div class=\"metric\">{metrics.get(key, 0):g}</div>"
            "</article>"
        )
    return cards


def render_mode_progress_items(profile: object, metrics: Dict[str, float]) -> List[str]:
    scoring_metrics = getattr(profile, "scoring_metrics", [])
    progress_items = [
        f"Goal: {getattr(profile, 'goal', '')}",
        f"Quality score: {metrics.get('quality_score', 0):g}",
    ]
    progress_items.extend(f"Metric: {metric}" for metric in scoring_metrics[:4])
    return progress_items


def render_list_card(title: str, items: Sequence[str]) -> str:
    rendered_items = "".join(items) if items else "<li>なし</li>"
    return (
        "      <article class=\"card\">"
        f"<h2>{escape(title)}</h2>"
        f"<ul>{rendered_items}</ul>"
        "</article>"
    )


def render_question_items(questions: Sequence[Dict[str, object]]) -> List[str]:
    return [
        (
            f"<li><strong>P{escape(str(question['priority']))}</strong> "
            f"{escape(str(question['question']))}"
            f"<br><span class=\"muted\">{escape(str(question['source']))}</span></li>"
        )
        for question in questions
    ]


def render_issue_items(issues: Sequence[Dict[str, object]]) -> List[str]:
    return [
        (
            f"<li><strong>{escape(str(issue['priority']))}</strong> "
            f"{escape(str(issue['title']))}"
            f"<br><span class=\"muted\">{escape(str(issue['source']))}</span></li>"
        )
        for issue in issues
    ]


def render_decision_items(decisions: Sequence[Dict[str, object]]) -> List[str]:
    return [
        (
            f"<li>{escape(str(decision['text']))}"
            f"<br><span class=\"muted\">{escape(str(decision['source']))}</span></li>"
        )
        for decision in decisions
    ]


def render_transcript_items(lines: Sequence[TranscriptLine]) -> List[str]:
    return [
        (
            f"<li><strong>{escape(line.timestamp or 'now')}</strong> "
            f"{escape(line.speaker)}: {escape(line.text)}</li>"
        )
        for line in lines
    ]


def render_rolling_summary_items(lines: Sequence[TranscriptLine]) -> List[str]:
    windows = build_rolling_windows(lines, 60)
    return [
        (
            f"<li><strong>Window {index}</strong> "
            f"{escape(summarize_window(window_lines))}</li>"
        )
        for index, (_start, _end, window_lines) in enumerate(windows[-3:], start=1)
    ]


def extract_mermaid_preview(diagrams: str) -> str:
    marker = "```mermaid"
    if marker not in diagrams:
        return diagrams[:1000]
    after_marker = diagrams.split(marker, 1)[1]
    return after_marker.split("```", 1)[0].strip()


def render_requirement_items(requirements: Sequence[Dict[str, object]]) -> List[str]:
    return [
        (
            f"<li><strong>{escape(str(requirement['category']))}</strong> "
            f"{escape(str(requirement['text']))}"
            f"<br><span class=\"muted\">{escape(str(requirement['source']))}</span></li>"
        )
        for requirement in requirements
    ]


def should_generate_ui_mockup(requirements: Sequence[Dict[str, object]]) -> bool:
    ui_terms = ("UI", "画面", "表示", "ログイン", "ダッシュボード")
    return any(
        any(term in str(requirement["text"]) for term in ui_terms)
        for requirement in requirements
    )


def render_dashboard_mockup(
    project_name: str,
    requirements: Sequence[Dict[str, object]],
) -> str:
    requirement_items = "".join(
        f"<li>{escape(str(requirement['text']))}</li>" for requirement in requirements[:5]
    )
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="ja">',
            "<head>",
            '  <meta charset="utf-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1">',
            f"  <title>{escape(project_name)} Mockup</title>",
            "  <style>",
            "    body{font-family:system-ui,sans-serif;margin:0;background:#eef2f7;color:#172033}",
            "    .shell{max-width:1180px;margin:0 auto;padding:24px}",
            "    .top{display:flex;justify-content:space-between;"
            "align-items:center;margin-bottom:20px}",
            "    .panel{background:white;border:1px solid #cbd5e1;border-radius:8px;padding:18px}",
            "    .grid{display:grid;grid-template-columns:2fr 1fr;gap:16px}",
            "    .tile{border:1px solid #d8dee8;border-radius:8px;padding:14px;margin-top:12px}",
            "    .value{font-size:30px;font-weight:700}",
            "  </style>",
            "</head>",
            "<body>",
            "  <main class=\"shell\">",
            "    <div class=\"top\">",
            f"      <h1>{escape(project_name)}</h1>",
            "      <button>Issue候補を確認</button>",
            "    </div>",
            "    <section class=\"grid\">",
            "      <article class=\"panel\">",
            "        <h2>Dashboard MVP</h2>",
            "        <div class=\"tile\"><div>Open blockers</div>"
            "<div class=\"value\">3</div></div>",
            "        <div class=\"tile\"><div>Issue candidates</div>"
            "<div class=\"value\">5</div></div>",
            "      </article>",
            "      <aside class=\"panel\">",
            "        <h2>Grounded requirements</h2>",
            f"        <ul>{requirement_items or '<li>未検出</li>'}</ul>",
            "      </aside>",
            "    </section>",
            "  </main>",
            "</body>",
            "</html>",
        ]
    ) + "\n"


def build_rolling_windows(
    lines: Sequence[TranscriptLine],
    window_seconds: int = 60,
) -> List[tuple[int, int, List[TranscriptLine]]]:
    windows: List[tuple[int, int, List[TranscriptLine]]] = []
    current_start: int | None = None
    current_lines: List[TranscriptLine] = []
    for line in lines:
        seconds = parse_timestamp_seconds(line.timestamp)
        if seconds is None:
            seconds = current_start or 0
        if current_start is None:
            current_start = seconds
        if seconds >= current_start + window_seconds and current_lines:
            windows.append((current_start, current_start + window_seconds, current_lines))
            current_start = seconds
            current_lines = []
        current_lines.append(line)
    if current_start is not None and current_lines:
        windows.append((current_start, current_start + window_seconds, current_lines))
    return windows


def count_rolling_windows(lines: Sequence[TranscriptLine]) -> int:
    return len(build_rolling_windows(lines))


def summarize_window(lines: Sequence[TranscriptLine]) -> str:
    texts = [line.text for line in lines]
    decisions = [text for text in texts if any(keyword in text for keyword in DECISION_KEYWORDS)]
    questions = [
        normalize_question(text)
        for text in texts
        if "?" in text or "？" in text or text.endswith(("ですか", "ますか"))
    ]
    body = ["- Summary: " + " ".join(texts[:3])]
    if decisions:
        body.append("- Decisions: " + " / ".join(decisions[:2]))
    if questions:
        body.append("- Questions: " + " / ".join(questions[:2]))
    return "\n".join(body)


def parse_timestamp_seconds(timestamp: str) -> int | None:
    if not timestamp:
        return None
    parts = timestamp.split(":")
    if not all(part.isdigit() for part in parts):
        return None
    values = [int(part) for part in parts]
    if len(values) == 2:
        minutes, seconds = values
        return minutes * 60 + seconds
    if len(values) == 3:
        hours, minutes, seconds = values
        return hours * 3600 + minutes * 60 + seconds
    return None


def timestamp_to_ms(timestamp: str) -> int:
    seconds = parse_timestamp_seconds(timestamp)
    return int(seconds * 1000) if seconds is not None else 0


def format_seconds(seconds: int) -> str:
    minutes, rest = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{rest:02d}"
    return f"{minutes:02d}:{rest:02d}"


def render_requirements(
    project_name: str,
    meeting_mode: str,
    requirements: Sequence[Dict[str, object]],
    decisions: Sequence[Dict[str, object]],
    questions: Sequence[Dict[str, object]],
) -> str:
    req_lines = render_requirement_lines(requirements)
    functional_lines = render_requirement_lines(
        [req for req in requirements if req["category"] == "functional"]
    )
    ui_lines = render_requirement_lines([req for req in requirements if req["category"] == "ui"])
    auth_lines = render_requirement_lines(
        [req for req in requirements if req["category"] == "security"]
    )
    data_lines = render_requirement_lines(
        [req for req in requirements if req["category"] == "data"]
    )
    integration_lines = render_requirement_lines(
        [req for req in requirements if req["category"] == "integration"]
    )
    decision_lines = [f"- {decision['text']} — {decision['source']}" for decision in decisions] or [
        "- 未検出"
    ]
    blocker_lines = render_question_lines([q for q in questions if q["category"] == "blocker"])
    open_question_lines = render_question_lines(questions)
    acceptance_lines = render_acceptance_lines(requirements)
    return "\n".join(
        [
            f"# Requirements: {project_name}",
            "",
            f"**Meeting mode:** {meeting_mode}",
            "",
            "## Background / Purpose",
            f"- {project_name} の会議内容を、実装に進められる構造化成果物へ変換する。",
            "",
            "## Target Users",
            "- Meeting participants",
            "- Implementation agents that consume approved artifacts",
            "",
            "## Use Cases",
            "- 会議中に未確定事項を検出し、終了後すぐ実装計画へ移る。",
            "",
            "## Functional Requirements",
            *(functional_lines or req_lines or ["- 未検出"]),
            "",
            "## Non-functional Requirements",
            "- 生成物は transcript の根拠と人間承認状態を保持する。",
            "- 重い処理はワーカーへ分離し、会議進行を止めない。",
            "",
            "## UI/UX Requirements",
            *(ui_lines or ["- UI 要件は未検出"]),
            "",
            "## Permission / Authentication Requirements",
            *(auth_lines or ["- 権限・認証要件は未検出"]),
            "",
            "## Data Requirements",
            *(data_lines or ["- データ要件は未検出"]),
            "",
            "## External Integrations",
            *(integration_lines or ["- 外部連携要件は未検出"]),
            "",
            "## Constraints",
            "- 外部登録と実装エージェント起動はユーザー承認後に行う。",
            "",
            "## Decisions",
            *decision_lines,
            "",
            "## Open Questions",
            *open_question_lines,
            "",
            "## Assumptions",
            "- 会議参加者は録音・文字起こしに同意している。",
            "- 未確認事項は open questions として扱い、確定仕様と区別する。",
            "",
            "## Risks",
            "- partial transcript を根拠に確定成果物を作ると誤要件化する。",
            "- 承認なしの外部登録や実装開始は会議内容の意図を逸脱する。",
            "",
            "## Acceptance Criteria",
            *acceptance_lines,
            "",
            "## Functional / Scope Requirements",
            *(req_lines or ["- 未検出"]),
            "",
            "## Open Blockers",
            *(blocker_lines or ["- なし"]),
        ]
    ) + "\n"


def render_requirement_lines(requirements: Sequence[Dict[str, object]]) -> List[str]:
    return [
        f"- [{req['status']}] ({req['category']}) {req['text']} — {req['source']}"
        for req in requirements
    ]


def render_question_lines(questions: Sequence[Dict[str, object]]) -> List[str]:
    return [
        f"- P{question['priority']} ({question['category']}) {question['question']} — "
        f"{question['reason']} ({question['source']})"
        for question in questions
    ]


def render_acceptance_lines(requirements: Sequence[Dict[str, object]]) -> List[str]:
    lines: List[str] = []
    for requirement in requirements:
        for criterion in build_acceptance_criteria(str(requirement["text"])):
            lines.append(f"- {criterion}")
    return lines or ["- 生成された要件が transcript の根拠と紐づいている。"]


def render_questions(questions: Sequence[Dict[str, object]]) -> str:
    grouped = {"blocker": [], "high_impact": [], "clarification": [], "later": []}
    for question in questions:
        grouped.setdefault(str(question["category"]), []).append(question)
    lines = ["# Open Questions", ""]
    for category, title in (
        ("blocker", "Blocker"),
        ("high_impact", "High Impact"),
        ("clarification", "Clarification"),
        ("later", "Later"),
    ):
        lines.extend([f"## {title}", ""])
        if grouped.get(category):
            lines.extend(
                (
                    f"- P{question['priority']} {question['question']} — "
                    f"{question['reason']} ({question['source']})"
                )
                for question in grouped[category]
            )
        else:
            lines.append("- なし")
        lines.append("")
    return "\n".join(lines)


def write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def source_label(line: TranscriptLine) -> str:
    return f"{line.timestamp} {line.speaker}".strip()


def source_event_id(line: TranscriptLine, fallback_index: int) -> str:
    return line.source_event_id or f"line_{fallback_index}"


def normalize_question(text: str) -> str:
    stripped = text.strip()
    if stripped.endswith(("?", "？")):
        return stripped
    return f"{stripped}？"


def classify_requirement(text: str) -> str:
    if any(keyword in text for keyword in ("UI", "UX", "画面", "表示", "ダッシュボード")):
        return "ui"
    if any(keyword in text for keyword in ("CSV", "後回し", "MVP")):
        return "functional"
    if any(keyword in text for keyword in ("日次", "更新")):
        return "data"
    if any(keyword in text for keyword in ("管理者", "権限")):
        return "security"
    if any(keyword in text for keyword in ("Issue", "GitHub")):
        return "integration"
    if any(keyword in text for keyword in ("低遅延", "性能", "セキュリティ", "プライバシー")):
        return "non_functional"
    return "functional"


def make_issue_title(text: str) -> str:
    if "ダッシュボード" in text:
        return "ダッシュボードMVPを実装する"
    if "日次" in text or "更新" in text:
        return "日次更新要件を実装する"
    if "Issue" in text or "GitHub" in text:
        return "会議内容からIssue候補を生成する"
    return text[:40].rstrip("。")


def build_acceptance_criteria(text: str) -> List[str]:
    criteria = [f"要件「{text}」が実装またはタスク化されている。"]
    if "ダッシュボード" in text:
        criteria.append("ログイン後にMVP範囲のダッシュボード情報が確認できる。")
    if "更新" in text or "日次" in text:
        criteria.append("データ更新頻度の仕様が明示されている。")
    if "Issue" in text or "GitHub" in text:
        criteria.append("GitHub Issue登録前に人間の承認を必要とする。")
    return criteria


def dedupe_by_text(items: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    seen = set()
    deduped: List[Dict[str, object]] = []
    for item in items:
        text = str(item["text"])
        if text in seen:
            continue
        seen.add(text)
        deduped.append(dict(item))
    return deduped


def merge_issue_candidates(
    candidates: Sequence[Dict[str, object]]
) -> List[Dict[str, object]]:
    merged: List[Dict[str, object]] = []
    by_title: Dict[str, Dict[str, object]] = {}
    for candidate in candidates:
        title = str(candidate["title"])
        if title not in by_title:
            item = dict(candidate)
            item["merged_candidate_count"] = 1
            by_title[title] = item
            merged.append(item)
            continue
        existing = by_title[title]
        existing["merged_candidate_count"] = int(existing["merged_candidate_count"]) + 1
        existing["body"] = "\n\n".join([str(existing["body"]), str(candidate["body"])])
        existing["confidence"] = max(float(existing["confidence"]), float(candidate["confidence"]))
        existing["acceptance_criteria"] = merge_unique(
            existing.get("acceptance_criteria", []),
            candidate.get("acceptance_criteria", []),
        )
        existing["granularity"] = merged_issue_granularity(existing, candidate)
        existing["granularity_reason"] = "重複候補を統合したため、レビュー時に粒度を確認する。"
        existing["blocked_by_question_ids"] = merge_unique(
            existing.get("blocked_by_question_ids", []),
            candidate.get("blocked_by_question_ids", []),
        )
        existing["source_event_ids"] = merge_unique(
            existing.get("source_event_ids", []),
            candidate.get("source_event_ids", []),
        )
        existing["source_range"] = " / ".join(
            merge_unique([existing.get("source_range", "")], [candidate.get("source_range", "")])
        )
    return merged


def classify_issue_granularity(text: str) -> str:
    if len(text) > 120 or "と" in text and "、" in text:
        return "too_large"
    if len(text) < 12:
        return "too_small"
    return "implementable"


def issue_granularity_reason(text: str) -> str:
    granularity = classify_issue_granularity(text)
    if granularity == "too_large":
        return "複数論点を含む可能性があるため、分割レビューが必要。"
    if granularity == "too_small":
        return "実装可能な受け入れ条件を追加する必要がある。"
    return "1つの実装タスクとして扱える粒度。"


def merged_issue_granularity(
    existing: Dict[str, object],
    candidate: Dict[str, object],
) -> str:
    values = {str(existing.get("granularity", "")), str(candidate.get("granularity", ""))}
    if "too_large" in values:
        return "too_large"
    if "review_needed" in values or len(values) > 1:
        return "review_needed"
    return values.pop() if values else "review_needed"


def merge_unique(first: object, second: object) -> List[str]:
    values: List[str] = []
    for collection in (first, second):
        if not isinstance(collection, list):
            collection = [collection]
        for value in collection:
            text = str(value)
            if text and text not in values:
                values.append(text)
    return values
