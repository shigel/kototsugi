import json
import subprocess
from pathlib import Path


def test_auto_review_script_generates_report() -> None:
    completed = subprocess.run(
        ["python", "scripts/auto_review.py"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    report_path = Path("review-report.json")
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["quantitative"]["tests_passed"] is True
    assert report["quantitative"]["lint_passed"] is True
    assert report["qualitative"]["passed"] is True
