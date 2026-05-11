# SOKCON

**Social conversation to construction.**

**会話を、即今、構築へ。**

SOKCON is a prototype CLI for **Meeting Driven Development (MDD)**.
It turns live meeting conversations and transcripts into structured artifacts:

- transcript
- speaker summary
- diarization manifest and speaker segments
- rolling-style summary
- rolling_summary.md windows
- requirements
- requirement item JSON
- decisions
- prioritized questions
- blocker question suggestions
- question status state and updates
- Mermaid architecture diagram
- Mermaid architecture/data-flow/screen-flow diagrams
- diagram revision manifest for diff updates
- GitHub Issue candidates
- issue status state and updates
- implementation plan
- static dashboard
- HTML mockups when UI requirements are detected
- audit log
- event bus and worker status manifests
- performance and latency manifest
- MVP success condition manifest
- privacy manifest
- retention policy and cleanup
- approval action queue
- branch creation draft
- pull request draft
- external email draft
- meeting mode profile
- requirements traceability report
- requirements audit script for generated artifact directories
- live verification manifest
- state snapshot
- local dashboard server
- macOS notification plan and sender
- notification policy manifest
- Slack notification draft payload
- external registration draft payloads
- implementation agent handoff draft
- approval plan generation for selected actions
- WAV audio preparation for Realtime input
- quantitative + qualitative evaluation report

The current MVP keeps transcript-to-artifact generation deterministic, while the
Realtime Gateway, audio capture/preparation, approval-gated integrations, and
live verification commands are implemented as explicit boundaries. A completed
OpenAI Realtime verification requires `OPENAI_API_KEY` plus an executed
`--run-realtime-live-check --execute` run; dry runs remain useful diagnostics but
do not satisfy the completion audit.

## Quick start

```bash
uv run sokcon path/to/transcript.txt --out ./artifacts --project "Dashboard MVP"
```

or with stdin:

```bash
cat transcript.txt | uv run sokcon - --out ./artifacts
```

For a Realtime-style transcript event stream, use JSON or JSONL:

```bash
uv run sokcon events.jsonl --input-format events --out ./artifacts
```

Supported event inputs include SOKCON events:

```json
{"kind":"final","timestamp":"00:20","speaker":"Eng","text":"管理者権限は必要ですか？"}
```

and OpenAI Realtime transcription event shapes such as:

```json
{"type":"conversation.item.input_audio_transcription.completed","transcript":"ログイン後のダッシュボードをMVPで作ります。"}
```

Partial events are saved to `partial_transcript.md` and `transcript_events.json`, but only final
events are used for confirmed artifacts.

## Realtime gateway configuration

SOKCON reads Realtime Gateway settings from exported environment variables. The API key is never
printed by diagnostic output. Use `.env.example` as a local template and keep real `.env` files
untracked.

```bash
set -a; . ./.env; set +a
uv run sokcon --print-realtime-config
```

Supported variables:

- `OPENAI_API_KEY`
- `SOKCON_REALTIME_MODEL` defaults to `gpt-realtime-2`
- `SOKCON_TRANSCRIPTION_REALTIME_MODEL` defaults to `gpt-realtime-whisper`
- `SOKCON_TRANSLATION_REALTIME_MODEL` defaults to `gpt-realtime-translate`
- `SOKCON_REALTIME_ROUTE` selects `primary`, `transcription`, or `translation`
- `SOKCON_TRANSLATION_TARGET_LANGUAGE` defaults to `ja`
- `SOKCON_TRANSCRIPTION_MODEL` defaults to `gpt-4o-transcribe`
- `SOKCON_REALTIME_VOICE` defaults to `alloy`
- `SOKCON_INPUT_AUDIO_FORMAT` defaults to `pcm16`
- `SOKCON_OUTPUT_AUDIO_FORMAT` defaults to `pcm16`
- `SOKCON_AUDIO_INPUT_DEVICE` selects a macOS input device for capture, for example `BlackHole`
- `SOKCON_ENABLE_EXTERNAL_REGISTRATION=1` enables external registration paths

The diagnostic output includes an API compatibility report for the current Realtime session shape:
`type`, `audio.input.format`, `audio.input.transcription`, and the transcript delta/completed
event names used by the pipeline. It links to the current OpenAI Realtime docs:
https://developers.openai.com/api/docs/guides/realtime and
https://developers.openai.com/api/docs/guides/realtime-transcription.

Prepare an uncompressed 16-bit PCM WAV file into Realtime-ready base64 PCM chunks:

```bash
uv run sokcon --prepare-audio meeting.wav --out ./audio-artifacts --audio-chunk-ms 100
```

This writes `audio_manifest.json`, `audio_chunks.json`, and `realtime_send_plan.json`. It does
not send audio to OpenAI.

Dry-run microphone capture on macOS:

```bash
uv run sokcon --capture-audio meeting.wav --duration-seconds 60
```

For meeting-app/system audio on macOS, route audio through a virtual input such as BlackHole:

```bash
uv run sokcon --capture-audio meeting.wav --duration-seconds 60 --audio-input-device BlackHole
```

Add `--execute` to run `afrecord` and actually create the WAV file. Executed captures also write
`audio_input_manifest.json` beside the WAV file. The manifest records the supported topology for
mixed self and remote meeting audio: route microphone plus meeting-app/system audio into one macOS
virtual input, then preserve or recover speakers through transcript metadata or diarization.
The manifest names Google Meet, Zoom, and Slack Huddle as expected meeting-app sources.

Dry-run Realtime session creation:

```bash
OPENAI_API_KEY=... uv run sokcon --create-realtime-session
```

Add `--execute` to actually POST the session request to OpenAI. The API key is never printed.
Use `SOKCON_REALTIME_ROUTE=transcription` to evaluate the `gpt-realtime-whisper` route, or
`SOKCON_REALTIME_ROUTE=translation` to evaluate the `gpt-realtime-translate` route.

Dry-run or execute streaming of a generated audio send plan:

```bash
OPENAI_API_KEY=... uv run sokcon --stream-realtime-audio ./audio-artifacts
```

Add `--execute` to open the Realtime WebSocket and send the audio events.

Run a combined live-readiness check for session creation plus audio streaming:

```bash
OPENAI_API_KEY=... uv run sokcon --run-realtime-live-check ./audio-artifacts
```

Add `--execute` to perform both network operations. The command writes
`realtime_live_check_result.json` into the artifact directory and refreshes
`live_verification_manifest.json`. Completion audits require the live check result to show
`status: completed` and `network_request_executed: true`; a dry run is kept as evidence, but it is
not treated as a completed Realtime verification.

## Speaker diarization

Transcript/event speaker metadata is preserved by default. For audio-based high-accuracy
diarization, configure an external provider command:

```bash
SOKCON_DIARIZATION_COMMAND="diarize" uv run sokcon --print-diarization-config
```

Dry-run or execute the external command:

```bash
uv run sokcon --run-diarization meeting.wav --out ./artifacts
```

Add `--execute` to run the configured command. Pipeline runs also write
`diarization_manifest.json` and `diarization_segments.json`.

## macOS notifications

Each pipeline run writes `macos_notification_plan.json` for blocker questions, meeting completion,
and approval-waiting actions. By default, sending is a dry run:

```bash
uv run sokcon --send-macos-notifications ./artifacts
```

Add `--execute` to call `osascript` and display the notifications. The plan also includes a
focus command that can be wired from notification handlers or approval tooling to return to the
active terminal/app window. Set `SOKCON_NOTIFICATION_FOCUS_APP` to `Terminal`, `iTerm2`, or
`VS Code` to choose the focus target. Inspect the resolved command with:

```bash
uv run sokcon --print-notification-config
```

## Slack configuration

```bash
SOKCON_SLACK_WEBHOOK_URL=... uv run sokcon --print-slack-config
```

The webhook URL is never printed. Actual Slack sending is still represented as a draft payload and
approval step.

Dry-run a generated Slack notification:

```bash
uv run sokcon --send-slack-notification ./artifacts
```

Add `--execute` to POST to `SOKCON_SLACK_WEBHOOK_URL`.

## External registration configuration

```bash
GITHUB_TOKEN=... SOKCON_GITHUB_REPOSITORY=owner/repo \
  uv run sokcon --print-external-config
```

Supported diagnostics cover GitHub, Linear, Notion, Google Docs, Google Slides, CRM, and ATS.
Tokens and API keys are never printed. Draft payloads for those destinations are written to
`external_registration_payloads.json` when they are passed with `--external-destination`.

## Privacy controls

```bash
uv run sokcon transcript.txt \
  --confidential \
  --retention-days 7 \
  --external-destination github
```

`--confidential` forces external registration off and clears external destinations in
`audit_log.json` and `privacy_manifest.json`.

Clean up expired artifact files according to `privacy_manifest.json`:

```bash
uv run sokcon --cleanup-retention ./artifacts
```

This is a dry run by default. Add `--execute` to delete expired files. Each run also writes
`retention_policy.json`.

## Local dashboard server

Serve a generated artifact directory locally:

```bash
uv run sokcon --serve-dashboard ./artifacts --port 8765
```

Routes:

- `/` serves `dashboard.html`
- `/state` serves `state_snapshot.json`
- `/stream` serves Server-Sent Events snapshots when watched artifact files change
- `/stream?once=1` serves a single snapshot for diagnostics
- `/events` serves `transcript_events.json`
- `/actions` serves `action_queue.json`
- `/privacy` serves `privacy_manifest.json`
- `/traceability` serves `requirements_traceability.json`
- `/artifacts/<name>` serves generated artifacts without allowing path escapes

## Approval plan

Promote selected queued actions into an execution-ready plan without performing external effects:

```bash
uv run sokcon --approve-actions ./artifacts \
  --approve-action-id action_review_issue_candidates
```

This writes `approval_plan.json`. It does not call Slack, GitHub, Linear, Notion, email clients, or
coding agents. `external_email_draft.json` is also treated as an approval-gated draft; execution
returns `manual_send_required` until a human-operated mail client integration is configured.
`branch_creation_draft.json` records the proposed `git switch -c ...` command and is executed only
from an approved plan with `--execute`.

Dry-run or execute approved external registrations:

```bash
uv run sokcon --execute-approval-plan ./artifacts
```

Add `--execute` to actually call the configured external APIs or start an approved agent handoff.

Update a question after it is answered or dismissed:

```bash
uv run sokcon --update-question-status ./artifacts \
  --question-id q_2 \
  --question-status answered
```

This updates `questions.json` and rewrites `question_status.json`.

Update an Issue candidate after review or registration:

```bash
uv run sokcon --update-issue-status ./artifacts \
  --issue-id issue_1 \
  --issue-status approved
```

This updates `issue_candidates.json` and rewrites `issue_status.json`.

## Meeting modes

`--mode` accepts:

```text
development, sales, hiring, presentation, customer_success, fundraising, legal, executive, research, general
```

Each run writes `mode_profile.json` with the selected mode's goal, expected outputs, question
criteria, scoring metrics, allowed tools, and post-meeting actions.

Mode-specific files are also generated. For example, `--mode sales` writes
`account_summary.md`, `pain_points.md`, `opportunity_score.md`, `negotiation_notes.md`,
`next_actions.md`, `followup_email_draft.md`, and `crm_update.json`; `--mode hiring` writes
interview scorecard artifacts; `--mode presentation` writes talk brief and speaker-note drafts.

## Quality gate

```bash
uv run sokcon transcript.txt --min-quality-score 0.75
```

The command exits with code `2` if `quality_score` is below the threshold.

Audit generated artifacts against the explicit requirements checklist:

```bash
uv run python scripts/requirements_audit.py ./artifacts
```

This writes `requirements-audit.json` and exits non-zero when required evidence is missing.
For a completion audit, regenerate the transcript artifacts and Realtime audio artifacts in the
same artifact directory before running the audit, so stale audio evidence cannot satisfy the
checklist:

```bash
uv run sokcon transcript.txt --out ./artifacts --project "Dashboard MVP"
uv run sokcon --prepare-audio meeting.wav --out ./artifacts --audio-chunk-ms 100
OPENAI_API_KEY=... uv run sokcon --run-realtime-live-check ./artifacts --execute
uv run python scripts/requirements_audit.py ./artifacts
```

Write a live verification readiness manifest for OpenAI, diarization, Slack, and external
registration credentials:

```bash
uv run sokcon --write-live-verification ./artifacts
```

This writes `live_verification_manifest.json` and lists blocked checks without executing external
network calls. The manifest separates `blocked_mvp_checks` from post-MVP checks such as Slack,
CRM/ATS, and external diarization providers. `openai_realtime_api` remains blocked until
`realtime_live_check_result.json` records a successful executed Realtime live check.

## Development

```bash
uv run --active pytest -q
uv run --active ruff check .
```
