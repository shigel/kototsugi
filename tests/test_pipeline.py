import json
from pathlib import Path

from kototsugi.pipeline import process_transcript

SAMPLE_TRANSCRIPT = """
[00:00] PM: 今日はログイン後のダッシュボードMVPを決めたいです。
[00:30] Eng: 管理者と一般ユーザーで表示内容を変える必要がありますか？
[01:00] PM: MVPでは一般ユーザーだけでよいです。CSVエクスポートは後回しです。
[01:40] Eng: データ更新頻度は日次で十分ですか？
[02:00] PM: はい、日次更新でお願いします。GitHub Issueにもしておいてください。
""".strip()


def test_process_transcript_generates_core_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    result = process_transcript(
        transcript=SAMPLE_TRANSCRIPT,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="Dashboard MVP",
    )

    assert result.metrics["transcript_lines"] == 5
    assert result.metrics["question_count"] >= 2
    assert result.metrics["requirement_count"] >= 2
    assert result.metrics["issue_candidate_count"] >= 1
    assert result.metrics["quality_score"] >= 0.5

    expected_files = {
        "transcript.md",
        "summary.md",
        "requirements.md",
        "open_questions.md",
        "architecture.md",
        "issue_candidates.json",
        "implementation_plan.md",
        "evaluation.json",
    }
    assert expected_files.issubset({path.name for path in result.artifacts})

    requirements = (output_dir / "requirements.md").read_text(encoding="utf-8")
    assert "Dashboard MVP" in requirements
    assert "ダッシュボード" in requirements
    assert "日次" in requirements

    issues = json.loads((output_dir / "issue_candidates.json").read_text(encoding="utf-8"))
    assert any("ダッシュボード" in issue["title"] for issue in issues)


def test_process_transcript_prioritizes_blocker_questions(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    result = process_transcript(
        transcript=SAMPLE_TRANSCRIPT,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="Dashboard MVP",
    )

    questions = (output_dir / "open_questions.md").read_text(encoding="utf-8")
    assert "## Blocker" in questions
    assert "権限" in questions or "管理者" in questions
    assert result.metrics["blocker_question_count"] >= 1


def test_plain_mvp_mentions_do_not_become_confirmed_decisions(tmp_path: Path) -> None:
    transcript = "[00:00] PM: MVPではログイン後のダッシュボードが必要です。"
    output_dir = tmp_path / "out"

    result = process_transcript(
        transcript=transcript,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="False Positive Guard",
    )

    assert result.metrics["decision_count"] == 0
    requirements = (output_dir / "requirements.md").read_text(encoding="utf-8")
    assert "[confirmed]" not in requirements


def test_plain_requirement_mentions_do_not_become_questions(tmp_path: Path) -> None:
    transcript = "[00:00] PM: MVPではログイン後のダッシュボードが必要です。"
    output_dir = tmp_path / "out"

    result = process_transcript(
        transcript=transcript,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="False Positive Guard",
    )

    assert result.metrics["question_count"] == 0


def test_prioritized_questions_keep_transcript_order_within_same_priority(
    tmp_path: Path,
) -> None:
    transcript = "\n".join(
        f"[00:{index:02d}] Eng: 確認事項その{index}ですか？" for index in range(1, 12)
    )
    output_dir = tmp_path / "out"

    process_transcript(
        transcript=transcript,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="Question Ordering",
    )

    questions = (output_dir / "open_questions.md").read_text(encoding="utf-8")
    assert questions.index("確認事項その2") < questions.index("確認事項その10")


def test_process_transcript_evaluation_contains_quantitative_and_qualitative_sections(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"

    process_transcript(
        transcript=SAMPLE_TRANSCRIPT,
        output_dir=output_dir,
        meeting_mode="development",
        project_name="Dashboard MVP",
    )

    evaluation = json.loads((output_dir / "evaluation.json").read_text(encoding="utf-8"))
    assert "quantitative" in evaluation
    assert "qualitative" in evaluation
    assert "quality_score" in evaluation["quantitative"]
    assert "strengths" in evaluation["qualitative"]
    assert "risks" in evaluation["qualitative"]
