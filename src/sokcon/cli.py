from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sokcon.approvals import (
    execute_approval_plan,
    update_issue_status,
    update_question_status,
    write_approval_plan,
)
from sokcon.diarization import (
    describe_diarization_config,
    execute_diarization,
    load_diarization_config,
)
from sokcon.events import load_transcript_events
from sokcon.integrations import (
    describe_external_registration_config,
    describe_slack_config,
    load_external_registration_config,
    load_slack_config,
    send_slack_notification,
)
from sokcon.live_verification import write_live_verification_manifest
from sokcon.modes import supported_modes
from sokcon.notifications import (
    describe_notification_config,
    load_notification_config,
    send_macos_notifications,
)
from sokcon.pipeline import process_transcript, process_transcript_events
from sokcon.realtime import (
    capture_audio,
    create_realtime_session,
    describe_realtime_config,
    load_realtime_config,
    prepare_wav_audio,
    run_realtime_live_check,
    stream_realtime_audio,
)
from sokcon.retention import cleanup_retention
from sokcon.server import serve_dashboard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sokcon",
        description=(
            "Social conversation to construction: turn meeting transcripts into "
            "MDD artifacts: specs, questions, diagrams, issues, and plans."
        ),
    )
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        help="Transcript text file. Use '-' to read stdin.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("sokcon-output"),
        help="Output directory",
    )
    parser.add_argument(
        "--mode",
        choices=supported_modes(),
        default="development",
        help="Meeting mode",
    )
    parser.add_argument("--project", default="SOKCON Project", help="Project name")
    parser.add_argument(
        "--input-format",
        choices=("transcript", "events"),
        default="transcript",
        help="Read plain transcript text or transcript event JSON/JSONL.",
    )
    parser.add_argument(
        "--min-quality-score",
        type=float,
        default=0.5,
        help="Fail if quantitative quality_score is below this threshold.",
    )
    parser.add_argument(
        "--confidential",
        action="store_true",
        help="Disable external registration and mark outputs as confidential local storage.",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help="Retention period recorded in privacy_manifest.json.",
    )
    parser.add_argument(
        "--external-destination",
        action="append",
        default=[],
        help="External destination to disclose in audit/privacy metadata.",
    )
    parser.add_argument(
        "--enable-external-registration",
        action="store_true",
        help="Mark external registration paths as enabled; still requires approval.",
    )
    parser.add_argument(
        "--print-realtime-config",
        action="store_true",
        help="Print redacted Realtime Gateway configuration and exit.",
    )
    parser.add_argument(
        "--create-realtime-session",
        action="store_true",
        help="Create or dry-run an OpenAI Realtime session and exit.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute network/external side effects for commands that support it.",
    )
    parser.add_argument(
        "--print-slack-config",
        action="store_true",
        help="Print redacted Slack integration configuration and exit.",
    )
    parser.add_argument(
        "--print-external-config",
        action="store_true",
        help="Print redacted GitHub/Linear/Notion registration configuration and exit.",
    )
    parser.add_argument(
        "--print-diarization-config",
        action="store_true",
        help="Print redacted speaker diarization configuration and exit.",
    )
    parser.add_argument(
        "--print-notification-config",
        action="store_true",
        help="Print macOS notification focus configuration and exit.",
    )
    parser.add_argument(
        "--serve-dashboard",
        type=Path,
        help="Serve an artifact directory as a local dashboard and exit when interrupted.",
    )
    parser.add_argument(
        "--prepare-audio",
        type=Path,
        help="Prepare an uncompressed 16-bit PCM WAV file as Realtime audio chunks.",
    )
    parser.add_argument(
        "--capture-audio",
        type=Path,
        help="Capture microphone audio to a WAV file using macOS afrecord.",
    )
    parser.add_argument(
        "--audio-input-device",
        help="Audio input device id/name for --capture-audio, for example BlackHole.",
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=30,
        help="Capture duration for --capture-audio.",
    )
    parser.add_argument(
        "--stream-realtime-audio",
        type=Path,
        help="Stream or dry-run realtime_send_plan.json from an audio artifact directory.",
    )
    parser.add_argument(
        "--run-realtime-live-check",
        type=Path,
        help="Run or dry-run session creation plus realtime_send_plan.json streaming.",
    )
    parser.add_argument(
        "--run-diarization",
        type=Path,
        help="Run or dry-run external diarization for an audio file.",
    )
    parser.add_argument(
        "--approve-actions",
        type=Path,
        help="Create approval_plan.json from an artifact directory.",
    )
    parser.add_argument(
        "--execute-approval-plan",
        type=Path,
        help="Execute or dry-run approved external actions from approval_plan.json.",
    )
    parser.add_argument(
        "--update-question-status",
        type=Path,
        help="Update questions.json/question_status.json in an artifact directory.",
    )
    parser.add_argument(
        "--update-issue-status",
        type=Path,
        help="Update issue_candidates.json/issue_status.json in an artifact directory.",
    )
    parser.add_argument(
        "--cleanup-retention",
        type=Path,
        help="Delete or dry-run deletion of expired artifact files using privacy_manifest.json.",
    )
    parser.add_argument(
        "--write-live-verification",
        type=Path,
        help="Write live_verification_manifest.json for external/API readiness.",
    )
    parser.add_argument(
        "--send-slack-notification",
        type=Path,
        help="Send or dry-run slack_notification.json from an artifact directory.",
    )
    parser.add_argument(
        "--send-macos-notifications",
        type=Path,
        help="Send or dry-run macos_notification_plan.json from an artifact directory.",
    )
    parser.add_argument(
        "--approve-action-id",
        action="append",
        default=[],
        help="Action id to approve for --approve-actions. Can be repeated.",
    )
    parser.add_argument("--question-id", help="Question id for --update-question-status.")
    parser.add_argument("--issue-id", help="Issue id for --update-issue-status.")
    parser.add_argument(
        "--question-status",
        choices=("open", "answered", "dismissed"),
        help="New status for --update-question-status.",
    )
    parser.add_argument(
        "--issue-status",
        choices=("candidate", "draft", "approved", "registered", "rejected"),
        help="New status for --update-issue-status.",
    )
    parser.add_argument(
        "--audio-chunk-ms",
        type=int,
        default=100,
        help="Audio chunk duration for --prepare-audio.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard server host.")
    parser.add_argument("--port", type=int, default=8765, help="Dashboard server port.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.print_realtime_config:
        print(json.dumps(describe_realtime_config(load_realtime_config()), ensure_ascii=False))
        return 0
    if args.create_realtime_session:
        print(
            json.dumps(
                create_realtime_session(load_realtime_config(), execute=args.execute),
                ensure_ascii=False,
            )
        )
        return 0
    if args.print_slack_config:
        print(json.dumps(describe_slack_config(load_slack_config()), ensure_ascii=False))
        return 0
    if args.print_external_config:
        print(
            json.dumps(
                describe_external_registration_config(load_external_registration_config()),
                ensure_ascii=False,
            )
        )
        return 0
    if args.print_diarization_config:
        print(
            json.dumps(
                describe_diarization_config(load_diarization_config()),
                ensure_ascii=False,
            )
        )
        return 0
    if args.print_notification_config:
        print(
            json.dumps(
                describe_notification_config(load_notification_config()),
                ensure_ascii=False,
            )
        )
        return 0
    if args.serve_dashboard is not None:
        serve_dashboard(args.serve_dashboard, host=args.host, port=args.port, announce=print)
        return 0
    if args.prepare_audio is not None:
        result = prepare_wav_audio(
            input_path=args.prepare_audio,
            output_dir=args.out,
            chunk_ms=args.audio_chunk_ms,
        )
        print(json.dumps(result["manifest"], ensure_ascii=False))
        return 0
    if args.capture_audio is not None:
        realtime_config = load_realtime_config()
        print(
            json.dumps(
                capture_audio(
                    output_path=args.capture_audio,
                    duration_seconds=args.duration_seconds,
                    audio_input_device=(
                        args.audio_input_device or realtime_config.audio_input_device
                    ),
                    execute=args.execute,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.stream_realtime_audio is not None:
        print(
            json.dumps(
                stream_realtime_audio(
                    artifact_dir=args.stream_realtime_audio,
                    config=load_realtime_config(),
                    execute=args.execute,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.run_realtime_live_check is not None:
        result = run_realtime_live_check(
            artifact_dir=args.run_realtime_live_check,
            config=load_realtime_config(),
            execute=args.execute,
            write_result=True,
        )
        write_live_verification_manifest(
            artifact_dir=args.run_realtime_live_check,
            realtime_config=load_realtime_config(),
            diarization_config=load_diarization_config(),
            external_config=load_external_registration_config(),
            slack_config=load_slack_config(),
        )
        print(
            json.dumps(
                result,
                ensure_ascii=False,
            )
        )
        return 0
    if args.run_diarization is not None:
        print(
            json.dumps(
                execute_diarization(
                    audio_path=args.run_diarization,
                    output_dir=args.out,
                    config=load_diarization_config(),
                    execute=args.execute,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.approve_actions is not None:
        output = write_approval_plan(
            artifact_dir=args.approve_actions,
            approved_action_ids=args.approve_action_id,
        )
        print(str(output))
        return 0
    if args.execute_approval_plan is not None:
        print(
            json.dumps(
                execute_approval_plan(
                    artifact_dir=args.execute_approval_plan,
                    config=load_external_registration_config(),
                    execute=args.execute,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.update_question_status is not None:
        if not args.question_id or not args.question_status:
            build_parser().error(
                "--update-question-status requires --question-id and --question-status"
            )
        output = update_question_status(
            artifact_dir=args.update_question_status,
            question_id=args.question_id,
            status=args.question_status,
        )
        print(str(output))
        return 0
    if args.update_issue_status is not None:
        if not args.issue_id or not args.issue_status:
            build_parser().error("--update-issue-status requires --issue-id and --issue-status")
        output = update_issue_status(
            artifact_dir=args.update_issue_status,
            issue_id=args.issue_id,
            status=args.issue_status,
        )
        print(str(output))
        return 0
    if args.cleanup_retention is not None:
        print(
            json.dumps(
                cleanup_retention(
                    artifact_dir=args.cleanup_retention,
                    execute=args.execute,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.write_live_verification is not None:
        output = write_live_verification_manifest(
            artifact_dir=args.write_live_verification,
            realtime_config=load_realtime_config(),
            diarization_config=load_diarization_config(),
            external_config=load_external_registration_config(),
            slack_config=load_slack_config(),
        )
        print(str(output))
        return 0
    if args.send_slack_notification is not None:
        print(
            json.dumps(
                send_slack_notification(
                    artifact_dir=args.send_slack_notification,
                    config=load_slack_config(),
                    execute=args.execute,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.send_macos_notifications is not None:
        print(
            json.dumps(
                send_macos_notifications(
                    artifact_dir=args.send_macos_notifications,
                    execute=args.execute,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.input is None:
        build_parser().error(
            "input is required unless --print-realtime-config, --serve-dashboard, "
            "--prepare-audio, --capture-audio, --approve-actions, --print-slack-config, "
            "--print-external-config, --create-realtime-session, "
            "--print-diarization-config, --print-notification-config, --run-diarization, "
            "--send-slack-notification, --send-macos-notifications, --stream-realtime-audio, "
            "--run-realtime-live-check, "
            "--update-question-status, --update-issue-status, --cleanup-retention, "
            "--write-live-verification, or --execute-approval-plan is used"
        )

    input_text = (
        sys.stdin.read() if str(args.input) == "-" else args.input.read_text(encoding="utf-8")
    )
    if args.input_format == "events":
        result = process_transcript_events(
            events=load_transcript_events(input_text),
            output_dir=args.out,
            meeting_mode=args.mode,
            project_name=args.project,
            confidential=args.confidential,
            retention_days=args.retention_days,
            external_destinations=args.external_destination,
            external_registration_enabled=args.enable_external_registration,
        )
    else:
        result = process_transcript(
            transcript=input_text,
            output_dir=args.out,
            meeting_mode=args.mode,
            project_name=args.project,
            confidential=args.confidential,
            retention_days=args.retention_days,
            external_destinations=args.external_destination,
            external_registration_enabled=args.enable_external_registration,
        )
    quality_score = result.metrics["quality_score"]
    print(f"SOKCON generated {len(result.artifacts)} artifacts in {args.out}")
    print(f"quality_score={quality_score:g}")
    if quality_score < args.min_quality_score:
        print(
            f"quality_score below threshold: {quality_score:g} < {args.min_quality_score:g}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
