from sokcon.modes import get_mode_profile, mode_profile_payload, supported_modes


def test_supported_modes_match_requirements() -> None:
    assert supported_modes() == [
        "development",
        "sales",
        "hiring",
        "presentation",
        "customer_success",
        "fundraising",
        "legal",
        "executive",
        "research",
        "general",
    ]


def test_mode_profile_contains_switchable_policy() -> None:
    profile = mode_profile_payload("development")

    assert profile["goal"]
    assert "requirements.md" in profile["primary_outputs"]
    assert "blocker" in profile["question_criteria"]
    assert "quality_score" in profile["scoring_metrics"]
    assert "github_issue_candidate" in profile["allowed_tools"]
    assert "review_issues" in profile["post_meeting_actions"]


def test_named_mode_outputs_match_requirements() -> None:
    sales = mode_profile_payload("sales")
    hiring = mode_profile_payload("hiring")
    presentation = mode_profile_payload("presentation")

    assert "crm_update.json" in sales["primary_outputs"]
    assert "opportunity_score.md" in sales["primary_outputs"]
    assert "interview_transcript.md" in hiring["primary_outputs"]
    assert "hiring_recommendation.md" in hiring["primary_outputs"]
    assert "audience_persona.md" in presentation["primary_outputs"]
    assert "speaker_notes_draft.md" in presentation["primary_outputs"]


def test_unknown_mode_is_rejected() -> None:
    try:
        get_mode_profile("unknown")
    except ValueError as error:
        assert "Unsupported meeting mode" in str(error)
    else:
        raise AssertionError("unknown mode should be rejected")
