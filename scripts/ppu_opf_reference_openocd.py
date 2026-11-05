"""OPF-4A: verified Bundle v3 OpenOCD reference route into the existing C-3 Worker.

This is an opt-in integration seam, NOT the production Runtime dispatcher.
The trusted Runtime owns the Job, its deadline, the actual hardware observation
and the exact-ICPN C-3 profile. C-3 remains the sole flash executor and owner
of Site admission, image binding, cancellation, SAFE_OFF and sealing.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from plasma_interfaces.site_worker_c3 import (
    C3FlashProfile, SiteWorkerControlClient, run_flash_cycle,
)
from plasma_opf import TimeoutPolicy, parse_programming_selection

import ppu_opf_site_session
import ppu_provider_contract
import ppu_site_engine


PROFILE_FILE = "data/plasma-flash-profile.json"
PROFILE_SCHEMA = "plasma.ppu.openocd-flash-profile.v1"


class ReferenceDenied(ValueError):
    """Reference admission failed; error codes contain no Bundle-supplied values."""


def _need(condition: bool, code: str) -> None:
    if not condition:
        raise ReferenceDenied(code)


@dataclass(frozen=True)
class ReferenceBinding:
    route: ppu_provider_contract.ProviderRoute
    profile: C3FlashProfile
    engine: ppu_site_engine.EngineSelection
    profile_sha256: str


def qualify_reference(
    *, product_root: Path, asset_set_sha256: str,
    selection: Mapping[str, Any], policy: TimeoutPolicy, target: str,
    site_id: int, image_size: int, hardware: Mapping[str, Any],
    runtime_profile: C3FlashProfile,
    engine_record: Path = ppu_site_engine.ENGINE_SELECTION,
    engine_base: Path = ppu_site_engine.ENGINE_BASE,
    require_root: bool = True,
) -> ReferenceBinding:
    """Bind immutable Provider/Profile files to the installed selected engine.

    The Bundle does *not* supply a command, a host path or an execution grant.
    The selected engine is independently checked by the existing root-owned
    engine-selection verifier. The actual C-3 Worker enforces its own ABI and
    FPGA identity on session admission and execution.
    """
    selected = parse_programming_selection(selection, policy=policy)
    route = ppu_provider_contract.resolve(
        product_root, asset_set_sha256=asset_set_sha256, target=target,
        provider=selected.provider, profile=selected.profile,
        operation="flash_cycle", site_id=site_id, image_size=image_size,
        hardware=hardware, options=selected.options)
    _need(route.transport == "fpga" and route.fpga_package is not None,
          "REFERENCE_TRANSPORT_UNSUPPORTED")
    # No option is silently ignored. Clock and adapter choices belong to the
    # trusted engine-selection record, not untrusted Bundle options.
    _need(route.options_json == b"{}", "REFERENCE_OPTIONS_UNSUPPORTED")
    _need(isinstance(runtime_profile, C3FlashProfile)
          and runtime_profile.icpn == target, "REFERENCE_TARGET_MISMATCH")

    try:
        engine = ppu_site_engine.load_engine(
            record=engine_record, base=engine_base, require_root=require_root)
    except ppu_site_engine.EngineNotReady as exc:
        raise ReferenceDenied("REFERENCE_ENGINE_NOT_READY:" + exc.code) from exc
    _need(route.driver_abi == f"{engine.adapter_driver}:{engine.driver_abi}",
          "REFERENCE_DRIVER_ABI_MISMATCH")

    staged = product_root / "assets" / "staged" / asset_set_sha256
    # Provider resolution already verifies *all* staged files against the
    # canonical Bundle manifest. Bind the executable bytes to the selected
    # engine too, rather than accepting only an ABI string as proof.
    try:
        manifest = json.loads((staged / "manifest.json").read_bytes())
        packages = {item["id"]: item for item in manifest["packages"]}
        provider = packages[route.provider_package]
        profile_package = packages[route.profile_package]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ReferenceDenied("REFERENCE_MANIFEST_INVALID") from exc
    _need(provider["kind"] == "native-c", "REFERENCE_PROVIDER_KIND_UNSUPPORTED")

    def exact_file(package: Mapping[str, Any], suffix: str) -> tuple[bytes, str]:
        name = f"payload/packages/{package['id']}/{suffix}"
        entries = [entry for entry in package["files"] if entry["path"] == name]
        _need(len(entries) == 1, "REFERENCE_PACKAGE_FILE_MISSING")
        entry = entries[0]
        try:
            raw = (staged / name).read_bytes()
        except OSError as exc:
            raise ReferenceDenied("REFERENCE_PACKAGE_FILE_UNREADABLE") from exc
        digest = hashlib.sha256(raw).hexdigest()
        _need(len(raw) == entry["size"] and digest == entry["sha256"],
              "REFERENCE_PACKAGE_FILE_CHANGED")
        return raw, digest

    _, binary_sha = exact_file(provider, "bin/openocd")
    _need(binary_sha == engine.openocd_sha256, "REFERENCE_ENGINE_BINARY_MISMATCH")
    _need(any(entry["path"] == f"payload/packages/{provider['id']}/bin/openocd"
              and entry["executable"] is True for entry in provider["files"]),
          "REFERENCE_ENGINE_NOT_EXECUTABLE")

    profile_raw, profile_sha = exact_file(profile_package, PROFILE_FILE)
    _need(len(profile_raw) <= 8192, "REFERENCE_PROFILE_INVALID")
    try:
        profile = json.loads(profile_raw)
    except (ValueError, UnicodeError) as exc:
        raise ReferenceDenied("REFERENCE_PROFILE_INVALID") from exc
    _need(type(profile) is dict
          and set(profile) == {"schema", *runtime_profile.to_wire()}
          and profile.get("schema") == PROFILE_SCHEMA,
          "REFERENCE_PROFILE_INVALID")
    _need({key: value for key, value in profile.items() if key != "schema"}
          == runtime_profile.to_wire(), "REFERENCE_PROFILE_RUNTIME_MISMATCH")
    return ReferenceBinding(route, runtime_profile, engine, profile_sha)


async def execute_reference_flash(
    client: SiteWorkerControlClient, *, product_root: Path,
    asset_set_sha256: str, selection: Mapping[str, Any], policy: TimeoutPolicy,
    job_id: str, site_id: int, target: str, image: bytes,
    image_root: Path, hardware: Mapping[str, Any],
    runtime_profile: C3FlashProfile, job_deadline_monotonic: float,
    job_timeout_s: float,
    engine_record: Path = ppu_site_engine.ENGINE_SELECTION,
    engine_base: Path = ppu_site_engine.ENGINE_BASE,
    require_root: bool = True,
) -> dict[str, Any]:
    """Run the *existing* native ABI-v5 flash cycle through C-3; no Provider subprocess.

    The Runtime production dispatcher does not call this yet. The C-3 control
    socket, staging, profile binding, readback checking and close/SAFE_OFF
    handling remain exactly the same as the pre-OPF Runtime flash path.
    """
    _need(type(image) is bytes and len(image) > 0, "REFERENCE_IMAGE_INVALID")
    selected = parse_programming_selection(selection, policy=policy)
    _need(type(job_timeout_s) in (int, float)
          and math.isfinite(job_timeout_s)
          and job_timeout_s == selected.timeout_ms / 1000.0
          and type(job_deadline_monotonic) in (int, float)
          and math.isfinite(job_deadline_monotonic),
          "REFERENCE_JOB_DEADLINE_MISMATCH")
    binding = qualify_reference(
        product_root=product_root, asset_set_sha256=asset_set_sha256,
        selection=selection, policy=policy, target=target, site_id=site_id,
        image_size=len(image), hardware=hardware, runtime_profile=runtime_profile,
        engine_record=engine_record, engine_base=engine_base, require_root=require_root)

    worker_receipt: ppu_opf_site_session.BoundSession | None = None

    def open_session() -> dict[str, Any]:
        nonlocal worker_receipt
        bound = ppu_opf_site_session.open_provider_job_session(
            client, product_root=product_root, asset_set_sha256=asset_set_sha256,
            selection=selection, policy=policy, job_id=job_id, target=target,
            operation="flash_cycle", site_id=site_id, image_size=len(image),
            hardware=hardware, job_deadline_monotonic=job_deadline_monotonic,
            job_timeout_s=job_timeout_s,
            expected_engine_selection_sha256=binding.engine.record_sha256)
        if bound.route != binding.route:
            client.call("close_session", session_id=bound.session_id)
            raise ReferenceDenied("REFERENCE_ROUTE_CHANGED")
        worker_receipt = bound
        return {"session_id": bound.session_id}

    result = await run_flash_cycle(
        client, job_id=job_id, site_id=site_id, profile=binding.profile,
        image=image, image_root=image_root, max_runtime_s=math.ceil(job_timeout_s),
        session_factory=open_session)
    _need(worker_receipt is not None, "WORKER_ENGINE_RECEIPT_MISSING")
    return {**result, "opf_provider_package": binding.route.provider_package,
            "opf_profile_package": binding.route.profile_package,
            "opf_asset_set_sha256": binding.route.asset_set_sha256,
            "opf_profile_sha256": binding.profile_sha256,
            "opf_driver_abi": binding.route.driver_abi,
            "opf_openocd_sha256": binding.engine.openocd_sha256,
            "opf_engine_selection_sha256": binding.engine.record_sha256,
            "opf_worker_engine_selection_sha256": worker_receipt.worker_engine_selection_sha256,
            "opf_worker_epoch": worker_receipt.worker_epoch}
