from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List


@dataclass(frozen=True)
class MeetingModeProfile:
    name: str
    goal: str
    primary_outputs: List[str]
    question_criteria: List[str]
    scoring_metrics: List[str]
    allowed_tools: List[str]
    post_meeting_actions: List[str]


MODE_PROFILES: Dict[str, MeetingModeProfile] = {
    "development": MeetingModeProfile(
        name="development",
        goal="実装に必要な未確定事項を潰し、会議終了後すぐ開発を開始できる状態にする。",
        primary_outputs=[
            "transcript.md",
            "summary.md",
            "requirements.md",
            "decisions.md",
            "open_questions.md",
            "architecture.md",
            "issue_candidates.json",
            "implementation_plan.md",
        ],
        question_criteria=["blocker", "high_impact", "implementation_scope"],
        scoring_metrics=["quality_score", "blocker_question_count", "issue_candidate_count"],
        allowed_tools=["mermaid", "github_issue_candidate", "html_mockup"],
        post_meeting_actions=["review_issues", "confirm_blockers", "start_agent_after_approval"],
    ),
    "sales": MeetingModeProfile(
        name="sales",
        goal="相手の課題、予算感、決裁構造、次アクションを整理する。",
        primary_outputs=[
            "account_summary.md",
            "pain_points.md",
            "opportunity_score.md",
            "negotiation_notes.md",
            "next_actions.md",
            "followup_email_draft.md",
            "crm_update.json",
        ],
        question_criteria=["budget", "authority", "need", "timeline"],
        scoring_metrics=["opportunity_score", "risk_count"],
        allowed_tools=["followup_email_draft", "crm_update_candidate"],
        post_meeting_actions=["draft_followup", "review_crm_update"],
    ),
    "hiring": MeetingModeProfile(
        name="hiring",
        goal="候補者の強み、懸念、深掘り不足を構造化して判断材料にする。",
        primary_outputs=[
            "interview_transcript.md",
            "candidate_scorecard.md",
            "strengths.md",
            "concerns.md",
            "followup_questions.md",
            "hiring_recommendation.md",
        ],
        question_criteria=["specificity", "depth", "role_fit"],
        scoring_metrics=["scorecard_completeness", "concern_count"],
        allowed_tools=["scorecard", "followup_questions"],
        post_meeting_actions=["review_scorecard", "draft_hiring_recommendation"],
    ),
    "presentation": MeetingModeProfile(
        name="presentation",
        goal="登壇内容の骨子、聴衆、持ち帰り、スライド構成を固める。",
        primary_outputs=[
            "talk_brief.md",
            "audience_persona.md",
            "outline.md",
            "slide_structure.md",
            "key_messages.md",
            "speaker_notes_draft.md",
            "slides_draft.md",
        ],
        question_criteria=["audience", "message", "storyline"],
        scoring_metrics=["outline_completeness", "missing_context_count"],
        allowed_tools=["slide_outline", "speaker_notes_draft"],
        post_meeting_actions=["review_outline", "draft_slides_after_approval"],
    ),
    "customer_success": MeetingModeProfile(
        name="customer_success",
        goal="顧客課題、導入状況、リスク、次の支援アクションを整理する。",
        primary_outputs=["customer_summary.md", "risks.md", "next_actions.md"],
        question_criteria=["adoption", "blocker", "stakeholder"],
        scoring_metrics=["risk_count", "action_count"],
        allowed_tools=["success_plan", "support_ticket_candidate"],
        post_meeting_actions=["review_actions", "draft_customer_update"],
    ),
    "fundraising": MeetingModeProfile(
        name="fundraising",
        goal="投資家の関心、懸念、追加資料、次回接点を整理する。",
        primary_outputs=["investor_summary.md", "concerns.md", "followup_materials.md"],
        question_criteria=["traction", "market", "financials", "next_step"],
        scoring_metrics=["concern_count", "followup_count"],
        allowed_tools=["followup_email_draft", "data_room_request"],
        post_meeting_actions=["draft_followup", "prepare_materials"],
    ),
    "legal": MeetingModeProfile(
        name="legal",
        goal="契約・法務論点、未確認事項、リスク、承認待ち事項を整理する。",
        primary_outputs=["legal_issues.md", "risks.md", "approval_items.md"],
        question_criteria=["risk", "liability", "approval"],
        scoring_metrics=["risk_count", "approval_item_count"],
        allowed_tools=["legal_review_notes"],
        post_meeting_actions=["review_with_counsel", "track_approval_items"],
    ),
    "executive": MeetingModeProfile(
        name="executive",
        goal="意思決定、経営論点、担当者、期限を明確にする。",
        primary_outputs=["executive_summary.md", "decisions.md", "action_items.md"],
        question_criteria=["decision", "owner", "deadline", "impact"],
        scoring_metrics=["decision_count", "action_count"],
        allowed_tools=["decision_log", "action_tracker"],
        post_meeting_actions=["review_decisions", "assign_actions"],
    ),
    "research": MeetingModeProfile(
        name="research",
        goal="仮説、知見、未検証事項、次の実験や調査を整理する。",
        primary_outputs=["research_notes.md", "hypotheses.md", "next_experiments.md"],
        question_criteria=["hypothesis", "evidence", "method"],
        scoring_metrics=["hypothesis_count", "open_question_count"],
        allowed_tools=["literature_notes", "experiment_plan"],
        post_meeting_actions=["review_hypotheses", "plan_experiments"],
    ),
    "general": MeetingModeProfile(
        name="general",
        goal="会議内容、決定事項、未確認事項、次アクションを整理する。",
        primary_outputs=["summary.md", "decisions.md", "open_questions.md", "next_actions.md"],
        question_criteria=["clarity", "decision", "owner"],
        scoring_metrics=["decision_count", "question_count"],
        allowed_tools=["summary", "action_tracker"],
        post_meeting_actions=["review_summary", "confirm_next_actions"],
    ),
}


def supported_modes() -> List[str]:
    return list(MODE_PROFILES.keys())


def get_mode_profile(mode: str) -> MeetingModeProfile:
    try:
        return MODE_PROFILES[mode]
    except KeyError as error:
        allowed = ", ".join(supported_modes())
        raise ValueError(f"Unsupported meeting mode: {mode}. Allowed modes: {allowed}") from error


def mode_profile_payload(mode: str) -> Dict[str, object]:
    return asdict(get_mode_profile(mode))
