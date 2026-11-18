"""PLASMA unified CLI, first deployable read-only diagnostic slice."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .api import FleetError, manager_batch, manager_fleet
from .targets import Target, parse_targets


def select_fleet(fleet: dict, targets: tuple[Target, ...], *, all_ppus: bool) -> tuple[dict, bool]:
    """Present exact observed data, never interpret mock/host data as HIL PASS."""
    if all_ppus:
        return {
            "schema": "plasma.utility.diagnose.v1",
            "observed_at": fleet.get("observed_at"),
            "summary": fleet.get("summary"),
            "degraded": fleet.get("degraded"),
            "ppus": fleet["ppus"],
        }, True
    available: dict[str, dict] = {}
    for item in fleet["ppus"]:
        if not isinstance(item, dict) or not isinstance(item.get("alias"), str):
            raise FleetError("Manager Fleet contains invalid PPU observation")
        alias = item["alias"]
        if alias in available:
            raise FleetError("Manager Fleet contains duplicate PPU aliases")
        available[alias] = item
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



def verify_batch_receipt(batch: dict, targets: tuple[Target, ...]) -> tuple[dict, bool]:
    """Inspect Manager-reported Batch results; not independent hardware HIL."""
    units = batch.get("units")
    declared = batch.get("targets")
    if not isinstance(units, list) or not isinstance(declared, list) or not units:
        raise FleetError("Manager Batch is missing canonical targets or Site units")
    declared_keys = set()
    for target in declared:
        if not isinstance(target, dict):
            raise FleetError("Manager Batch Target Set is malformed")
        alias, sites = target.get("ppu_alias"), target.get("site_ids")
        if not isinstance(alias, str) or not isinstance(sites, list):
            raise FleetError("Manager Batch Target Set is malformed")
        for site in sites:
            key = alias, site
            if type(site) is not int or site < 1 or key in declared_keys:
                raise FleetError("Manager Batch has invalid or duplicate Site targets")
            declared_keys.add(key)
    indexed = {}
    for unit in units:
        if not isinstance(unit, dict):
            raise FleetError("Manager Batch contains malformed Site units")
        alias, site = unit.get("ppu_alias"), unit.get("site_id")
        if not isinstance(alias, str) or type(site) is not int or site < 1:
            raise FleetError("Manager Batch contains invalid Site identity")
        key = alias, site
        if key in indexed:
            raise FleetError("Manager Batch contains duplicate Site units")
        indexed[key] = unit
    if set(indexed) != declared_keys:
        raise FleetError("Manager Batch Target Set and Site units disagree")
    selected = (
        [(target.ppu_alias, site_id) for target in targets for site_id in target.site_ids]
        if targets else [(u["ppu_alias"], u["site_id"]) for u in units]
    )
    if any(key not in indexed for key in selected):
        raise FleetError("Requested Site is absent from this Batch")
    projected = [
        {"ppu_alias": alias, "site_id": site,
         "status": indexed[(alias, site)].get("status"),
         "outcome": indexed[(alias, site)].get("outcome"),
         "reason": indexed[(alias, site)].get("reason"),
         "attempts": indexed[(alias, site)].get("attempts")}
        for alias, site in selected
    ]
    complete = batch.get("outcome") == "PASS" and all(
        unit.get("outcome") == "PASS" for unit in units
    )
    return {
        "schema": "plasma.utility.test-receipt.v1",
        "batch_id": batch["batch_id"],
        "batch_state": batch.get("state"),
        "batch_outcome": batch.get("outcome"),
        "manager_reported_pass": complete,
        "evidence_kind": "MANAGER_REPORTED_BATCH_ONLY",
        "sites": projected,
    }, complete


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plasmactl")
    subs = parser.add_subparsers(dest="command", required=True)
    diagnose = subs.add_parser("diagnose", help="read-only Manager Fleet / PPU-Site observations")
    diagnose.add_argument("--manager-url", default="http://127.0.0.1:18280")
    choice = diagnose.add_mutually_exclusive_group(required=True)
    choice.add_argument("--target", action="append", metavar="PPU:SITE[,SITE...]", help="repeat for different PPUs")
    choice.add_argument("--all", action="store_true", help="observe all registered PPUs")
    diagnose.add_argument("--timeout", type=float, default=5.0)
    test = subs.add_parser("test", help="inspect existing test results; never execute hardware")
    tests = test.add_subparsers(dest="test_command", required=True)
    receipt = tests.add_parser("receipt", help="verify Manager-reported programming Batch outcome")
    receipt.add_argument("--manager-url", default="http://127.0.0.1:18280")
    receipt.add_argument("--batch-id", required=True)
    receipt.add_argument("--target", action="append", help="optional exact PPU:Site projection")
    receipt.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)
    try:
        targets = parse_targets(args.target or [])
        if args.command == "diagnose":
            fleet = manager_fleet(args.manager_url, timeout=args.timeout)
            response, complete = select_fleet(fleet, targets, all_ppus=args.all)
        else:
            batch = manager_batch(args.manager_url, args.batch_id, timeout=args.timeout)
            response, complete = verify_batch_receipt(batch, targets)
    except (FleetError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
