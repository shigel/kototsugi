from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence


@dataclass(frozen=True)
class PipelineResult:
    artifacts: List[Path]
    metrics: Dict[str, float]


@dataclass(frozen=True)
class TranscriptLine:
    timestamp: str
    speaker: str
    text: str


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


def process_transcript(
    *,
    transcript: str,
    output_dir: Path,
    meeting_mode: str = "development",
    project_name: str = "KOTOTSUGI Project",
) -> PipelineResult:
    """Process a transcript into MDD artifacts.

    This MVP intentionally uses deterministic heuristics so the qualitative and
    quantitative evaluation loop can run offline in CI. LLM/realtime workers can
    later replace each extractor behind the same artifact contract.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    lines = parse_transcript(transcript)
    decisions = extract_decisions(lines)
    questions = prioritize_questions(lines)
    requirements = extract_requirements(lines, decisions)
    issues = build_issue_candidates(lines, requirements, questions)
    diagram = build_mermaid_diagram(project_name, requirements)
    plan = build_implementation_plan(project_name, requirements, questions, issues)
    metrics = evaluate_outputs(lines, requirements, questions, issues, decisions)

    artifacts = [
        write_text(output_dir / "transcript.md", render_transcript(project_name, lines)),
        write_text(
            output_dir / "summary.md",
            render_summary(project_name, lines, decisions, metrics),
        ),
        write_text(
            output_dir / "requirements.md",
            render_requirements(project_name, meeting_mode, requirements, decisions, questions),
        ),
        write_text(output_dir / "open_questions.md", render_questions(questions)),
        write_text(output_dir / "architecture.md", diagram),
        write_json(output_dir / "issue_candidates.json", issues),
        write_text(output_dir / "implementation_plan.md", plan),
        write_json(output_dir / "evaluation.json", build_evaluation(metrics, questions, issues)),
    ]
    return PipelineResult(artifacts=artifacts, metrics=metrics)


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
                )
            )
        else:
            parsed.append(TranscriptLine(timestamp="", speaker="Unknown", text=line))
    return parsed


def extract_decisions(lines: Sequence[TranscriptLine]) -> List[Dict[str, object]]:
    decisions: List[Dict[str, object]] = []
    for index, line in enumerate(lines, start=1):
        if any(keyword in line.text for keyword in DECISION_KEYWORDS):
            decisions.append(
                {
                    "id": f"dec_{index}",
                    "text": line.text,
                    "source": source_label(line),
                    "confidence": 0.74,
                }
            )
    return decisions


def prioritize_questions(lines: Sequence[TranscriptLine]) -> List[Dict[str, object]]:
    questions: List[Dict[str, object]] = []
    for index, line in enumerate(lines, start=1):
        text = line.text
        is_question = "?" in text or "？" in text or text.endswith(("ですか", "ますか"))
        if is_question or any(keyword in text for keyword in ("未定",)):
            blocker_terms = ("権限", "管理者", "必要", "更新頻度")
            category = "blocker" if any(k in text for k in blocker_terms) else "clarification"
            reason = (
                "実装方針・Issue粒度に影響するため"
                if category == "blocker"
                else "仕様明確化のため"
            )
            questions.append(
                {
                    "id": f"q_{index}",
                    "question": normalize_question(text),
                    "category": category,
                    "priority": 1 if category == "blocker" else 3,
                    "reason": reason,
                    "status": "open",
                    "source": source_label(line),
                }
            )
    questions.sort(key=lambda item: int(item["priority"]))
    return questions


def extract_requirements(
    lines: Sequence[TranscriptLine], decisions: Sequence[Dict[str, object]]
) -> List[Dict[str, object]]:
    requirements: List[Dict[str, object]] = []
    for index, line in enumerate(lines, start=1):
        if any(keyword in line.text for keyword in REQUIREMENT_KEYWORDS):
            requirements.append(
                {
                    "id": f"req_{index}",
                    "category": classify_requirement(line.text),
                    "text": line.text,
                    "status": "draft",
                    "source": source_label(line),
                }
            )
    for index, decision in enumerate(decisions, start=1):
        requirements.append(
            {
                "id": f"req_dec_{index}",
                "category": "scope",
                "text": str(decision["text"]),
                "status": "confirmed",
                "source": str(decision["source"]),
            }
        )
    return dedupe_by_text(requirements)


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
                    "title": make_issue_title(text),
                    "body": f"## Requirement\n{text}\n\n## Source\n{requirement['source']}",
                    "type": "feature" if requirement["category"] != "task" else "task",
                    "priority": "P1",
                    "status": "candidate",
                    "confidence": 0.78,
                    "blocked_by_question_ids": blocker_ids[:2],
                    "source": requirement["source"],
                }
            )
    if not candidates and lines:
        candidates.append(
            {
                "id": "issue_1",
                "title": "会議内容をもとにMVPタスクを整理する",
                "body": "Transcriptから実装可能なタスクを整理する。",
                "type": "task",
                "priority": "P2",
                "status": "candidate",
                "confidence": 0.5,
                "blocked_by_question_ids": blocker_ids[:2],
                "source": source_label(lines[0]),
            }
        )
    return candidates


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
        "requirement_count": float(len(requirements)),
        "question_count": float(len(questions)),
        "blocker_question_count": float(blocker_count),
        "issue_candidate_count": float(len(issues)),
        "decision_count": float(len(decisions)),
        "quality_score": quality_score,
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


def render_transcript(project_name: str, lines: Sequence[TranscriptLine]) -> str:
    body = [f"# Transcript: {project_name}", ""]
    body.extend(f"- **[{line.timestamp}] {line.speaker}:** {line.text}" for line in lines)
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


def render_requirements(
    project_name: str,
    meeting_mode: str,
    requirements: Sequence[Dict[str, object]],
    decisions: Sequence[Dict[str, object]],
    questions: Sequence[Dict[str, object]],
) -> str:
    req_lines = [
        f"- [{req['status']}] ({req['category']}) {req['text']} — {req['source']}"
        for req in requirements
    ]
    decision_lines = [f"- {decision['text']} — {decision['source']}" for decision in decisions] or [
        "- 未検出"
    ]
    blocker_lines = [f"- {q['question']}" for q in questions if q["category"] == "blocker"] or [
        "- なし"
    ]
    return "\n".join(
        [
            f"# Requirements: {project_name}",
            "",
            f"**Meeting mode:** {meeting_mode}",
            "",
            "## Functional / Scope Requirements",
            *(req_lines or ["- 未検出"]),
            "",
            "## Decisions",
            *decision_lines,
            "",
            "## Open Blockers",
            *blocker_lines,
        ]
    ) + "\n"


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
    path.write_text(content, encoding="utf-8")
    return path


def write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def source_label(line: TranscriptLine) -> str:
    return f"{line.timestamp} {line.speaker}".strip()


def normalize_question(text: str) -> str:
    stripped = text.strip()
    if stripped.endswith(("?", "？")):
        return stripped
    return f"{stripped}？"


def classify_requirement(text: str) -> str:
    if any(keyword in text for keyword in ("CSV", "後回し", "MVP")):
        return "scope"
    if any(keyword in text for keyword in ("日次", "更新")):
        return "data"
    if any(keyword in text for keyword in ("管理者", "権限")):
        return "security"
    if any(keyword in text for keyword in ("Issue", "GitHub")):
        return "task"
    return "functional"


def make_issue_title(text: str) -> str:
    if "ダッシュボード" in text:
        return "ダッシュボードMVPを実装する"
    if "日次" in text or "更新" in text:
        return "日次更新要件を実装する"
    if "Issue" in text or "GitHub" in text:
        return "会議内容からIssue候補を生成する"
    return text[:40].rstrip("。")


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
