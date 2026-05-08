# KOTOTSUGI

KOTOTSUGI is a prototype CLI for **Meeting Driven Development (MDD)**.
It turns meeting transcripts into structured artifacts:

- transcript
- rolling-style summary
- requirements
- prioritized questions
- Mermaid architecture diagram
- GitHub Issue candidates
- implementation plan
- quantitative + qualitative evaluation report

The current MVP is intentionally offline and deterministic. Realtime audio, LLM
workers, and external integrations can be added behind the same artifact
contract later.

## Quick start

```bash
uv run kototsugi path/to/transcript.txt --out ./artifacts --project "Dashboard MVP"
```

or with stdin:

```bash
cat transcript.txt | uv run kototsugi - --out ./artifacts
```

## Quality gate

```bash
uv run kototsugi transcript.txt --min-quality-score 0.75
```

The command exits with code `2` if `quality_score` is below the threshold.

## Development

```bash
uv run --active pytest -q
uv run --active ruff check .
```
