#!/usr/bin/env python3
"""Single typed Asset Execution Layer for Python, Native C and FPGA.

This module is a common *trusted runtime dispatch seam*, NOT a new
Installer/Executor/Root entry. No uploaded file is imported or executed.
A product Runtime must supply independently qualified executor adapters
and an owner/Job lease; missing components fail closed.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

SHA64 = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
VERSION = re.compile(r"[A-Za-z0-9_.+-]{1,128}\Z")
ACTION = "execute"
EXECUTORS = {
    "python": "trusted-python-runtime",
    "native-c": "trusted-native-runtime",
    "fpga-image": "existing-protected-fpga-loader",
}


class AssetExecutionDenied(ValueError):
    pass


@dataclass(frozen=True)
class AssetExecutionRequest:
    asset_set_sha256: str
    package_id: str
    package_version: str
    package_kind: str
    package_identity_sha256: str
    action: str = ACTION


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise AssetExecutionDenied(code)


def _trusted_module(filename: str):
    # Load ONLY the factory-installed control plane, never an arbitrary
    # module or filename derived from a Bundle or an HTTP request.
    src = Path(__file__).with_name(filename)
    _require(not src.is_symlink() and src.is_file(),
             "ASSET_EXECUTION_CONTROL_MODULE_UNTRUSTED")
    spec = importlib.util.spec_from_file_location(
        "plasma_asset_exec_" + filename.replace(".", "_"), src,
    )
    _require(spec is not None and spec.loader is not None,
             "ASSET_EXECUTION_CONTROL_MODULE_UNTRUSTED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def prepare_asset_execution(
    product_root: Path, policy_path: Path, request: AssetExecutionRequest,
) -> dict[str, Any]:
    """Plan an action only from ONE verified Active Asset Set and live grant.

    Same controls for Python, Native C and FPGA. A PASS is authorization
    to *request* dispatch to a qualified Executor, not a license to launch
    arbitrary installed Python/C or access FPGA Manager.
    """
    _require(isinstance(request, AssetExecutionRequest)
             and type(request.asset_set_sha256) is str
             and SHA64.fullmatch(request.asset_set_sha256)
             and type(request.package_identity_sha256) is str
             and SHA64.fullmatch(request.package_identity_sha256)
             and type(request.package_id) is str
             and NAME.fullmatch(request.package_id)
             and type(request.package_version) is str
             and VERSION.fullmatch(request.package_version)
             and type(request.package_kind) is str
             and request.package_kind in EXECUTORS
             and request.action == ACTION,
             "ASSET_EXECUTION_REQUEST_DENIED")
    assets = _trusted_module("ppu_asset_set.py")
    active = assets.read_active(product_root)
    _require(active["state"] == "ACTIVE"
             and active["asset_set_sha256"] == request.asset_set_sha256,
             "ASSET_EXECUTION_ACTIVE_SET_MISMATCH")
    verified = assets.verify_staged(product_root, request.asset_set_sha256)
    staged = product_root / "assets" / "staged" / verified["asset_set_sha256"]
    manifest = assets._json_file(staged / "manifest.json")
    matches = [
        p for p in manifest["packages"]
        if p.get("id") == request.package_id
        and p.get("kind") == request.package_kind
        and p.get("version") == request.package_version
    ]
    _require(len(matches) == 1, "ASSET_EXECUTION_PACKAGE_NOT_FOUND")
    selected = matches[0]
    descriptor = {
        "id": selected["id"],
        "kind": selected["kind"],
        "version": selected["version"],
        "requires": selected["requires"],
        "files": sorted(
            [{
                "path": f["path"], "sha256": f["sha256"],
                "size": f["size"], "executable": f["executable"],
            } for f in selected["files"]],
            key=lambda f: f["path"],
        ),
    }
    actual_identity = hashlib.sha256(json.dumps(
        descriptor, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    _require(actual_identity == request.package_identity_sha256,
             "ASSET_EXECUTION_PACKAGE_IDENTITY_MISMATCH")
    # Current Master authorization must still be valid, even if an older
    # B2 receipt was once PASS and the B3 ZIP was correctly staged.
    authority = _trusted_module("ppu_bundle_authority.py")
    try:
        authorized = authority.approve_identity(
            archive_sha256=request.asset_set_sha256,
            source_commit=manifest["source_commit"],
            purpose=manifest["purpose"],
            target=manifest["target"],
            package_kinds=[p["kind"] for p in manifest["packages"]],
            policy_path=policy_path,
        )
    except authority.BundleAuthorityDenied as exc:
        raise AssetExecutionDenied("ASSET_EXECUTION_MASTER_AUTHORITY_DENIED") from exc
    return {
        "schema": "plasma.ppu.asset-execution-plan.v1",
        "status": "AUTHORIZED_NOT_EXECUTED",
        "asset_set_sha256": request.asset_set_sha256,
        "package_id": request.package_id,
        "package_version": request.package_version,
        "package_kind": request.package_kind,
        "package_identity_sha256": actual_identity,
        "action": request.action,
        "trusted_executor": EXECUTORS[request.package_kind],
        "relative_files": [f["path"] for f in descriptor["files"]],
        "dependencies": list(selected["requires"]),
        "master_authority": {
            "publisher": authorized["publisher"],
            "master_generation": authorized["master_generation"],
            "archive_sha256": authorized["archive_sha256"],
            "policy_sha256": authorized["policy_sha256"],
        },
        "hardware_admission": "NOT_RUN",
        "asset_executed": False,
        "fpga_loaded": False,
        "ready": False,
    }



def validate_fpga_b3_receipt(
    product_root: Path, plan: Mapping[str, Any], receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind a #1261 B3 result to a previously authorized FPGA Package plan.

    This is read-only receipt reconciliation. It does NOT initiate an FPGA
    load, validate physical readback independently, or mark a Site READY.
    The existing B3 Coordinator/Root Guard remain the only execution owner.
    """
    _require(isinstance(plan, Mapping)
             and plan.get("schema") == "plasma.ppu.asset-execution-plan.v1"
             and plan.get("status") == "AUTHORIZED_NOT_EXECUTED"
             and plan.get("package_kind") == "fpga-image"
             and plan.get("action") == ACTION
             and type(plan.get("asset_set_sha256")) is str
             and SHA64.fullmatch(plan["asset_set_sha256"]),
             "ASSET_EXECUTION_B3_PLAN_INVALID")
    digest = plan["asset_set_sha256"]
    _require(isinstance(receipt, Mapping)
             and receipt.get("schema") == "plasma.ppu.b3-deployment-receipt.v2"
             and receipt.get("result") == "PASS"
             and receipt.get("stage") == "bundle_install_and_fpga_load"
             and receipt.get("archive_sha256") == digest
             and receipt.get("fpga") == "LOADED"
             and receipt.get("runtime_site_readmission") == "REQUIRED"
             and receipt.get("dut") == "NOT_RUN",
             "ASSET_EXECUTION_B3_RECEIPT_MISMATCH")
    active = receipt.get("active_asset_set")
    loaded = receipt.get("fpga_load")
    transaction = receipt.get("transaction")
    _require(isinstance(active, Mapping)
             and active.get("asset_set_sha256") == digest
             and type(active.get("generation")) is int
             and active["generation"] > 0
             and isinstance(loaded, Mapping)
             and loaded.get("requested") is True
             and loaded.get("result") == "fpga_loaded"
             and loaded.get("identity") == "IDENTITY_PASS"
             and loaded.get("auto_restore") is False
             and isinstance(transaction, Mapping)
             and transaction.get("state") == "fpga_loaded",
             "ASSET_EXECUTION_B3_RECEIPT_MISMATCH")
    # Re-derive the handoff from the immutable staged inventory, rather than
    # trusting an image ID, BIN filename or SHA echoed by a Console receipt.
    assets = _trusted_module("ppu_asset_set.py")
    handoff = assets.resolve_staged_fpga_handoff(product_root, digest)
    image = handoff["fpga_image"]
    _require(image["package_id"] == plan.get("package_id")
             and image["package_version"] == plan.get("package_version")
             and loaded.get("fpga_image_id") == image["image_id"]
             and loaded.get("fpga_bin_sha256") == image["bin_sha256"]
             and loaded.get("fpga_manifest_sha256") == image["manifest_sha256"],
             "ASSET_EXECUTION_B3_IMAGE_MISMATCH")
    return {
        "schema": "plasma.ppu.fpga-b3-receipt-binding.v1",
        "status": "RECEIPT_MATCHED_ONLY",
        "asset_set_sha256": digest,
        "package_identity_sha256": plan["package_identity_sha256"],
        "fpga_image_id": image["image_id"],
        "runtime_site_readmission": "REQUIRED",
        "hardware_evidence": "NOT_INDEPENDENTLY_VERIFIED",
        "ready": False,
    }


def dispatch_asset_execution(
    product_root: Path,
    policy_path: Path,
    request: AssetExecutionRequest,
    *,
    execution_scope: Callable[[], AbstractContextManager] | None = None,
    trusted_executors: Mapping[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Common typed entry, with NO default runnable/FPGA executor.

    Caller-owned Runtime execution_scope must pin Site/PPU ownership
    throughout selected executor operation. FPGA executor additionally
    enforces hardware quiescence, Root source pin, Golden and FPGA Manager
    checks; no Bundle can name arbitrary executables or commands.
    """
    if execution_scope is None or not callable(execution_scope):
        raise AssetExecutionDenied("ASSET_EXECUTION_RUNTIME_SCOPE_REQUIRED")
    if trusted_executors is None or not isinstance(trusted_executors, Mapping):
        raise AssetExecutionDenied("ASSET_EXECUTION_TRUSTED_EXECUTOR_REQUIRED")
    _require(isinstance(request, AssetExecutionRequest)
             and request.package_kind in EXECUTORS,
             "ASSET_EXECUTION_REQUEST_DENIED")
    executor = trusted_executors.get(request.package_kind)
    if not callable(executor):
        raise AssetExecutionDenied("ASSET_EXECUTION_TRUSTED_EXECUTOR_REQUIRED")
    # Every check takes place INSIDE the trusted runtime lease: no time gap
    # where a different Asset Set can become active before adapter delivery.
    with execution_scope():
        plan = prepare_asset_execution(product_root, policy_path, request)
        result = executor(plan)
        _require(isinstance(result, Mapping)
                 and result.get("asset_set_sha256") == plan["asset_set_sha256"]
                 and result.get("package_identity_sha256") == plan["package_identity_sha256"]
                 and result.get("package_kind") == plan["package_kind"],
                 "ASSET_EXECUTION_EXECUTOR_RECEIPT_UNTRUSTED")
        return {
            "schema": "plasma.ppu.asset-dispatch-receipt.v1",
            "asset_set_sha256": plan["asset_set_sha256"],
            "package_identity_sha256": plan["package_identity_sha256"],
            "package_kind": plan["package_kind"],
            "action": plan["action"],
            "executor_result": dict(result),
            # No fabricated status: a callback may still report NOT_RUN.
        }
