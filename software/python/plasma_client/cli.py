from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from plasma_core.enums import JobState, Operation
from plasma_core.errors import PlasmaError
from plasma_core.models import JobRequest

from .client import PlasmaClient


class ProgressRenderer:
    """Single-line terminal progress display; final JSON remains on stdout."""

    def __init__(self, stream: TextIO = sys.stderr, *, enabled: bool = True, width: int = 28) -> None:
        self.stream = stream
        self.enabled = enabled
        self.width = width
        self._line_open = False

    def update(self, job: dict[str, Any]) -> None:
        if not self.enabled:
            return
        percent = min(100.0, max(0.0, float(job.get("progress_percent") or 0.0)))
        completed = round(self.width * percent / 100.0)
        bar = "█" * completed + "─" * (self.width - completed)
        stage = str(job.get("stage") or job.get("state") or "queued").upper()
        stage_percent = float(job.get("stage_progress_percent") or 0.0)
        byte_text = ""
        if job.get("bytes_total") is not None:
            byte_text = f"  {int(job.get('bytes_done') or 0):,}/{int(job['bytes_total']):,} B"
        cancel_text = "  CANCEL REQUESTED" if job.get("cancel_requested") else ""
        line = (
            f"CH{job['channel_id']} {stage:<9} [{bar}] {percent:5.1f}%"
            f"  stage {stage_percent:5.1f}%{byte_text}{cancel_text}"
        )
        self.stream.write("\r\033[2K" + line)
        self.stream.flush()
        self._line_open = True
        if JobState(str(job["state"])).terminal:
            self.finish()

    def message(self, message: str) -> None:
        if not self.enabled:
            return
        if self._line_open:
            self.finish()
        self.stream.write(message + "\n")
        self.stream.flush()

    def finish(self) -> None:
        if self.enabled and self._line_open:
            self.stream.write("\n")
            self.stream.flush()
            self._line_open = False


def _load_map(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("map JSON root must be an object")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plasma", description="Plasma programming client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9900)
    subcommands = parser.add_subparsers(dest="command", required=True)

    def channel_command(name: str) -> argparse.ArgumentParser:
        command = subcommands.add_parser(name)
        command.add_argument("--channel", type=int, required=True)
        command.add_argument("--timeout", type=float, default=30.0)
        command.add_argument("--retries", type=int, default=0)
        command.add_argument("--poll-interval", type=float, default=0.1)
        command.add_argument("--no-progress", action="store_true")
        return command

    program = channel_command("program")
    program.add_argument("--bin", type=Path, required=True)
    program.add_argument("--map", type=Path)

    channel_command("erase")

    verify = channel_command("verify")
    verify.add_argument("--bin", type=Path, required=True)

    read = channel_command("read")
    read.add_argument("--map", type=Path, required=True)

    status = subcommands.add_parser("status")
    status.add_argument("--channel", type=int)
    status.add_argument("--job")

    cancel = subcommands.add_parser("cancel")
    cancel.add_argument("--job", required=True)
    return parser


def _build_request(args: argparse.Namespace) -> JobRequest:
    if args.command == "program":
        return JobRequest(
            channel_id=args.channel,
            operation=Operation.PROGRAM,
            firmware=args.bin.read_bytes(),
            map_data=_load_map(args.map),
            timeout_s=args.timeout,
            max_retries=args.retries,
            client_id="plasma-cli",
            metadata={"firmware_name": args.bin.name},
        )
    if args.command == "erase":
        return JobRequest(
            channel_id=args.channel,
            operation=Operation.ERASE,
            timeout_s=args.timeout,
            max_retries=args.retries,
            client_id="plasma-cli",
        )
    if args.command == "verify":
        return JobRequest(
            channel_id=args.channel,
            operation=Operation.VERIFY,
            firmware=args.bin.read_bytes(),
            timeout_s=args.timeout,
            max_retries=args.retries,
            client_id="plasma-cli",
        )
    if args.command == "read":
        return JobRequest(
            channel_id=args.channel,
            operation=Operation.READ,
            map_data=_load_map(args.map),
            timeout_s=args.timeout,
            max_retries=args.retries,
            client_id="plasma-cli",
        )
    raise RuntimeError(f"unsupported work command: {args.command}")


async def _run_work(
    client: PlasmaClient,
    request: JobRequest,
    *,
    poll_interval_s: float,
    renderer: ProgressRenderer,
) -> dict[str, Any]:
    accepted = await client.start(request)
    job_id = str(accepted["job"]["job_id"])
    renderer.message(f"Job {job_id} queued. Press Ctrl+C to cancel.")
    wait_timeout = request.timeout_s * (request.max_retries + 1) + 10.0
    try:
        return await client.wait_for_job(
            job_id,
            poll_interval_s=poll_interval_s,
            timeout_s=wait_timeout,
            on_update=renderer.update,
        )
    except asyncio.CancelledError:
        renderer.message(f"Cancellation requested for {job_id}; waiting for Server acknowledgement...")
        await client.cancel(job_id)
        result = await client.wait_for_job(
            job_id,
            poll_interval_s=min(0.1, poll_interval_s),
            timeout_s=5.0,
            on_update=renderer.update,
        )
        renderer.finish()
        return result
    finally:
        renderer.finish()


async def _execute(args: argparse.Namespace) -> dict[str, Any]:
    client = PlasmaClient(args.host, args.port)
    if args.command == "status":
        return await client.status(channel_id=args.channel, job_id=args.job)
    if args.command == "cancel":
        return await client.cancel(args.job)
    renderer = ProgressRenderer(enabled=not args.no_progress)
    return await _run_work(
        client,
        _build_request(args),
        poll_interval_s=args.poll_interval,
        renderer=renderer,
    )


def main() -> None:
    args = _parser().parse_args()
    try:
        result = asyncio.run(_execute(args))
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": {"message": "cancel interrupted"}}), file=sys.stderr)
        raise SystemExit(130)
    except (OSError, ValueError, json.JSONDecodeError, PlasmaError) as exc:
        if isinstance(exc, PlasmaError):
            error = {
                "error_code": exc.code.value,
                "error_type": exc.error_type,
                "message": exc.message,
                "recoverable": exc.recoverable,
                "context": exc.context,
            }
        else:
            error = {"error_type": type(exc).__name__, "message": str(exc)}
        print(json.dumps({"ok": False, "error": error}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
