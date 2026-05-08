from pathlib import Path

from kototsugi.cli import main

SAMPLE = """[00:00] PM: ログイン後のダッシュボードをMVPで作ります。
[00:20] Eng: 管理者権限は必要ですか？
[00:50] PM: MVPでは一般ユーザーだけでよいです。Issue化してください。
"""


def test_cli_generates_artifacts_and_returns_success(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.txt"
    transcript.write_text(SAMPLE, encoding="utf-8")
    output_dir = tmp_path / "artifacts"

    exit_code = main([str(transcript), "--out", str(output_dir), "--project", "CLI MVP"])

    assert exit_code == 0
    assert (output_dir / "requirements.md").exists()
    assert (output_dir / "evaluation.json").exists()


def test_cli_fails_when_quality_gate_is_too_high(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("[00:00] A: 雑談です。", encoding="utf-8")
    output_dir = tmp_path / "artifacts"

    exit_code = main([
        str(transcript),
        "--out",
        str(output_dir),
        "--min-quality-score",
        "1.1",
    ])

    assert exit_code == 2
