"""plasmactl: the one PLASMA operator CLI.

Programming and observation use the existing Manager APIs only. Deployment
and maintenance delegate to the existing platform backends. Nothing here
depends on an execution path (Path 2/Path 3), a GitHub Runner or a host name.

Exit codes (all commands):
  0 PASS / accepted / observed      1 FAIL, PARTIAL, BLOCKED or NOT_VERIFIED
  2 invalid input or contract error 3 OUTCOME_UNKNOWN (reconcile, never resend)
  4 refused / never admitted        5 still in progress
Machine output is one JSON object on stdout; errors are JSON on stderr.

Deployment profiles (executed by the existing platform backends):
  integration            SWPC development/integration host (default; user systemd)
  local-control-station  Linux reference Control Station: Console/BFF + Manager only
  swpc-z2like            x86_64 PS-only PPU surrogate; root/system systemd
  z2-ps                  Real PYNQ-Z2 ARMv7 PS-only PPU runtime; no PL/Site/IC claim

  plasmactl install local-control-station --ppu-endpoint URL [--ppu-alias ALIAS]
  plasmactl deploy|verify|status|logs|restart local-control-station
  sudo plasmactl install|deploy swpc-z2like [--ppu-id ID] [--facility-id ID]
  sudo plasmactl verify swpc-z2like     root-read-only surrogate readiness
  sudo plasmactl bootstrap-sites swpc-z2like
  sudo plasmactl install|deploy z2-ps --release-artifact PATH --gateway-host IPv4 ...
  plasmactl verify|status|logs z2-ps    (restart stays with the Deployment Coordinator)
  plasmactl update|test|restart|web-restart|start|stop|ports|logs [TARGET]
                                        integration host; update-and-restart = deploy
  plasmactl verify fleet                integration Manager/Fleet read-only verification
  plasmactl hil programming --profile bluepill-ab ...  SWPC engineering CDC harness

Programming (Manager Batch API only; never a direct PPU write):
  plasmactl program submit --target PPU:SITE[,SITE...] [--target ...] --icpn ICPN
      (--image BIN | --bundle ZIP | --operations erase --address A --length N)
      --journal NEW_FILE [--retry-limit N] [--stop-after-failed-sites N] [--no-wait]
  plasmactl program status|receipt|stop --batch-id ID
  plasmactl program reconcile (--journal FILE | --start-id ID)

Safety boundary: z2-full remains reserved for PS + PL + Site/Programming
qualification; `z2` is intentionally not accepted and neither aliases
swpc-z2like. No profile alone proves PL, FPGA, Site electrical, real-IC
programming, eight-Site concurrency or production readiness. A program PASS is
the Manager-reported Batch outcome, not an independent electrical qualification.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import operations, programming
from .api import FleetError, manager_batch, manager_deployment_status, manager_fleet, require_id
from .programming import EXIT_IN_PROGRESS, EXIT_NOT_PASS, EXIT_PASS, EXIT_USAGE
from .targets import Target, parse_targets

DEFAULT_MANAGER = "http://127.0.0.1:18280"


def select_fleet(fleet: dict, targets: tuple[Target, ...], *, all_ppus: bool) -> tuple[dict, bool]:
    """Present exact observed data, never interpret mock/host data as HIL PASS."""
    available: dict[str, dict] = {}
    for item in fleet["ppus"]:
        if not isinstance(item, dict) or not isinstance(item.get("alias"), str):
            raise FleetError("Manager Fleet contains invalid PPU observation")
        alias = item["alias"]
        if alias in available:
            raise FleetError("Manager Fleet contains duplicate PPU aliases")
        available[alias] = item
    if all_ppus:
        # A successful GET is not a healthy Fleet; fail closed on degraded,
        # missing, duplicate or offline PPU observations.
        healthy = (
            bool(available) and fleet.get("degraded") is False
            and all(
                item.get("gateway_live") is True
                and item.get("identity_conflict") is False
                and item.get("errors") == []
                for item in available.values()
            )
        )
        return {
            "schema": "plasma.utility.diagnose.v1",
            "observed_at": fleet.get("observed_at"),
            "summary": fleet.get("summary"),
            "degraded": fleet.get("degraded"),
            "ppus": fleet["ppus"],
        }, healthy
    observations = []
    complete = True
    for target in targets:
        item = available.get(target.ppu_alias)
        if item is None:
            complete = False
            observations.append({
                "ppu_alias": target.ppu_alias,
                "site_ids": list(target.site_ids),
                "status": "NOT_FOUND",
            })
            continue
        sites = item.get("sites")
        if not isinstance(sites, list):
            raise FleetError("Manager Fleet contains invalid Site topology")
        present: dict[int, dict] = {}
        for site in sites:
            if not isinstance(site, dict) or type(site.get("site_id")) is not int:
                raise FleetError("Manager Fleet contains invalid Site identity")
            site_id = site["site_id"]
            if site_id in present:
                raise FleetError("Manager Fleet contains duplicate Site IDs")
            present[site_id] = site
        missing = [site_id for site_id in target.site_ids if site_id not in present]
        verified = (
            not missing and item.get("gateway_live") is True
            and item.get("identity_conflict") is False
            and item.get("errors") == []
        )
        if not verified:
            complete = False
        ppu = item.get("ppu") if isinstance(item.get("ppu"), dict) else {}
        observations.append({
            "ppu_alias": target.ppu_alias,
            "ppu_id": ppu.get("ppu_id"),
            "facility_id": ppu.get("facility_id"),
            "status": "OBSERVED" if verified else "NOT_VERIFIED",
            "gateway_live": item.get("gateway_live"),
            "execution_ready": item.get("execution_ready"),
            "errors": item.get("errors"),
            "missing_site_ids": missing,
            "sites": [present[site_id] for site_id in target.site_ids if site_id in present],
        })
    return {
        "schema": "plasma.utility.diagnose.v1",
        "observed_at": fleet.get("observed_at"),
        "ppus": observations,
    }, complete


def observe_deployments(manager_url: str, ppus: list[str], *, timeout: float = 5.0) -> tuple[dict, bool]:
    """Collect independent read-only Bootstrap observations for multiple PPUs."""
    if len(set(ppus)) != len(ppus):
        raise FleetError("duplicate PPU alias")
    items = []
    complete = True
    for alias in ppus:
        try:
            items.append(manager_deployment_status(manager_url, alias, timeout=timeout))
        except FleetError as exc:
            complete = False
            items.append({"ppu_alias": alias, "status": "NOT_VERIFIED", "reason": str(exc)})
    return {
        "schema": "plasma.utility.deployment-status.v1",
        "evidence_kind": "MANAGER_BOOTSTRAP_STATUS_ONLY",
        "ppus": items,
    }, complete


def _manager(parser: argparse.ArgumentParser, timeout: float = 5.0) -> None:
    parser.add_argument("--manager-url", default=DEFAULT_MANAGER)
    parser.add_argument("--timeout", type=float, default=timeout,
                        help="per-request timeout in seconds")


def _int(text: str) -> int:
    return int(text, 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plasmactl", description=__doc__.split("\n\n")[0],
        epilog=__doc__.split("\n\n", 1)[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    subs = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    diagnose = subs.add_parser("diagnose", help="read-only Manager Fleet / PPU-Site observations")
    _manager(diagnose)
    choice = diagnose.add_mutually_exclusive_group(required=True)
    choice.add_argument("--target", action="append", metavar="PPU:SITE[,SITE...]",
                        help="repeat for different PPUs")
    choice.add_argument("--all", action="store_true", help="observe all registered PPUs")

    program = subs.add_parser("program", help="programming through the Manager Batch API")
    psub = program.add_subparsers(dest="program_command", required=True, metavar="ACTION")
    submit = psub.add_parser("submit", help="issue a start ID and submit ONE Batch (never resent)")
    _manager(submit, 10.0)
    submit.add_argument("--target", action="append", required=True,
                        metavar="PPU:SITE[,SITE...]", help="repeat for each PPU (multi-PPU Target Set)")
    submit.add_argument("--icpn", required=True, help="IC part number declared by a Programming Route")
    submit.add_argument("--operations", default="erase,program,verify",
                        help="ordered subset of erase,program,verify")
    source = submit.add_mutually_exclusive_group()
    source.add_argument("--image", type=Path, help="Programming Image (BIN)")
    source.add_argument("--bundle", type=Path, help="Programming Bundle v3 archive")
    submit.add_argument("--address", type=_int, help="erase-only range start")
    submit.add_argument("--length", type=_int, help="erase-only range length")
    submit.add_argument("--retry-limit", type=int, default=0, choices=range(0, 6), metavar="0..5",
                        help="Manager retry of a definite FAIL only (default 0)")
    submit.add_argument("--stop-after-failed-sites", type=int, metavar="N",
                        help="Manager stop policy: submit nothing further after N FAILs")
    submit.add_argument("--journal", type=Path, required=True,
                        help="new local submission journal (exclusive create)")
    submit.add_argument("--no-wait", action="store_true", help="return once the Batch is accepted")
    submit.add_argument("--wait-timeout", type=float, default=1800.0)
    submit.add_argument("--quiet", action="store_true", help="no progress lines on stderr")

    status = psub.add_parser("status", help="observe a Batch (read-only)")
    _manager(status)
    status.add_argument("--batch-id", required=True)
    status.add_argument("--wait", action="store_true", help="observe until the Batch finishes")
    status.add_argument("--wait-timeout", type=float, default=1800.0)
    status.add_argument("--quiet", action="store_true")

    receipt = psub.add_parser("receipt", help="verify the Manager-persisted Batch outcome")
    _manager(receipt)
    receipt.add_argument("--batch-id", required=True)
    receipt.add_argument("--target", action="append", help="optional exact PPU:Site projection")

    rec = psub.add_parser("reconcile", help="read-only Start Outcome Reconciliation")
    _manager(rec)
    which = rec.add_mutually_exclusive_group(required=True)
    which.add_argument("--start-id")
    which.add_argument("--journal", type=Path)

    stop = psub.add_parser("stop", help="STOP_QUEUING: no further attempts; running Jobs finish")
    _manager(stop)
    stop.add_argument("--batch-id", required=True)

    deploy = subs.add_parser("deploy", help="deploy PROFILE via its backend, or 'deploy status'")
    deploy.add_argument("target", nargs="?", default="integration", metavar="PROFILE|status")
    deploy.add_argument("args", nargs=argparse.REMAINDER)
    for name in ("install", "verify", "status", "logs", "restart"):
        cmd = subs.add_parser(name, help=f"{name} via the profile backend "
                              f"({', '.join(operations.SUPPORTED[name])})")
        cmd.add_argument("target", nargs="?", default="integration", metavar="PROFILE")
        cmd.add_argument("args", nargs=argparse.REMAINDER)
    for name in operations.INTEGRATION_ONLY:
        if name != "restart-web":
            cmd = subs.add_parser(name, help="integration-host maintenance",
                                  aliases=["restart-web"] if name == "web-restart" else [])
            cmd.add_argument("args", nargs=argparse.REMAINDER)
    sites = subs.add_parser("bootstrap-sites", help="one-time swpc-z2like Site bootstrap")
    sites.add_argument("target")
    sites.add_argument("args", nargs=argparse.REMAINDER)
    hil = subs.add_parser("hil", help="SWPC engineering Blue Pill A/B + CDC harness")
    hil.add_argument("hil_command", choices=("programming",))
    hil.add_argument("args", nargs=argparse.REMAINDER)
    return parser


def _emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _program(args: argparse.Namespace) -> int:
    url, timeout = args.manager_url, args.timeout
    action = args.program_command
    if action == "submit":
        targets = parse_targets(args.target)
        body, source = programming.build_request(
            icpn=args.icpn, operations=programming.parse_operations(args.operations),
            targets=targets, image=args.image, bundle=args.bundle,
            address=args.address, length=args.length, retry_limit=args.retry_limit,
            stop_after_failed_sites=args.stop_after_failed_sites)
        result, code = programming.submit(url, body, source, args.journal, timeout=timeout)
        if code == EXIT_PASS and not args.no_wait:
            try:
                batch = programming.watch(url, result["batch_id"], wait_timeout=args.wait_timeout,
                                          timeout=timeout, progress=not args.quiet)
            except FleetError as exc:
                # Accepted, but not observable now: the Batch runs on in the
                # Manager. Observe again with `program status`; never resend.
                result["observation"] = f"UNAVAILABLE: {exc}"
                code = EXIT_IN_PROGRESS
            else:
                result["batch"] = programming.summarize_batch(batch)
                code = programming.batch_exit(batch)
        _emit(result)
        return code
    if action == "status":
        batch_id = require_id(args.batch_id, "Batch ID")
        batch = (programming.watch(url, batch_id, wait_timeout=args.wait_timeout,
                                   timeout=timeout, progress=not args.quiet)
                 if args.wait else manager_batch(url, batch_id, timeout=timeout))
        _emit({"schema": "plasma.utility.program-status.v1",
               "batch": programming.summarize_batch(batch)})
        return programming.batch_exit(batch)
    if action == "receipt":
        targets = parse_targets(args.target or [])  # validate before any I/O
        batch = manager_batch(url, args.batch_id, timeout=timeout)
        response, complete = programming.verify_batch_receipt(batch, targets)
        _emit(response)
        return EXIT_PASS if complete else programming.batch_exit(batch) or EXIT_NOT_PASS
    if action == "reconcile":
        journal = programming.Journal.load(args.journal) if args.journal else None
        start_id = require_id(journal.data.get("start_id") if journal else args.start_id, "start_id")
        response, code = programming.reconcile(url, start_id, journal, timeout=timeout)
        _emit(response)
        return code
    response, code = programming.stop_queuing(url, args.batch_id, timeout=timeout)
    _emit(response)
    return code


def _maintenance(args: argparse.Namespace) -> int:
    command = args.command
    if command in operations.INTEGRATION_ONLY or command == "restart-web":
        if command == "update-and-restart" and args.args not in ([], ["integration"]):
            raise operations.OperationError(
                "update-and-restart is an integration-only alias; use 'plasmactl deploy PROFILE'")
        if args.args and command != "update-and-restart":
            raise operations.OperationError(
                f"{command} is integration-only and accepts no profile argument")
        return operations.integration(operations.INTEGRATION_ONLY[command])
    if command == "bootstrap-sites":
        return operations.bootstrap_sites(args.target, args.args)
    if command == "hil":
        return operations.hil_programming(args.args)
    target, rest = args.target, list(args.args)
    if command in ("verify", "logs") and target not in operations.PROFILES:
        # `plasmactl verify fleet` / `plasmactl logs web` are integration targets.
        return operations.run_profile(command, "integration", [target, *rest])
    return operations.run_profile(command, target, rest)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not argv or argv[0] in ("help", "-h", "--help"):
        parser.print_help()
        return EXIT_PASS
    if argv[:2] == ["deploy", "status"]:
        sub = argparse.ArgumentParser(prog="plasmactl deploy status")
        _manager(sub)
        sub.add_argument("--ppu", action="append", required=True,
                         help="repeat to select multiple PPUs")
        ns = sub.parse_args(argv[2:])
        try:
            response, complete = observe_deployments(ns.manager_url, ns.ppu, timeout=ns.timeout)
        except FleetError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
            return EXIT_USAGE
        _emit(response)
        return EXIT_PASS if complete else EXIT_NOT_PASS
    args = parser.parse_args(argv)
    try:
        if args.command == "diagnose":
            targets = parse_targets(args.target or [])  # validate before any I/O
            fleet = manager_fleet(args.manager_url, timeout=args.timeout)
            response, complete = select_fleet(fleet, targets, all_ppus=args.all)
            _emit(response)
            return EXIT_PASS if complete else EXIT_NOT_PASS
        if args.command == "program":
            return _program(args)
        return _maintenance(args)
    except (FleetError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return EXIT_USAGE
    except operations.OperationError as exc:
        print(f"[plasmactl] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
