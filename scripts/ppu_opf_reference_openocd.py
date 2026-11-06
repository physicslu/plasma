"""OPF-4A: verified Bundle v3 OpenOCD reference route into the existing C-3 Worker.

The production Runtime dispatcher below binds its admitted Job to this executor.
The trusted Runtime owns the Job, its deadline, the actual hardware observation
and the exact-ICPN C-3 profile. C-3 remains the sole flash executor and owner
of Site admission, image binding, cancellation, SAFE_OFF and sealing.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from plasma_interfaces.site_worker_c3 import (
    C3FlashProfile, SiteWorkerControlClient, SiteWorkerRefused, run_flash_cycle,
)
from plasma_opf import TimeoutPolicy, parse_programming_selection
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest

import ppu_asset_set
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
    _need(route.transport == "fpga",
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
    # The platform Engine is independently verified by load_engine.
    # Only a native-c Provider carrying executable bytes must bind those
    # Bundle bytes to the installed Engine.
    try:
        manifest = json.loads((staged / "manifest.json").read_bytes())
        packages = {item["id"]: item for item in manifest["packages"]}
        provider = packages[route.provider_package]
        profile_package = packages[route.profile_package]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ReferenceDenied("REFERENCE_MANIFEST_INVALID") from exc
    _need(provider["kind"] in ("native-c", "platform-provider"),
          "REFERENCE_PROVIDER_KIND_UNSUPPORTED")

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

    if provider["kind"] == "native-c":
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

    The Runtime production dispatcher calls this with its pinned Job. The C-3 control
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
            expected_engine_selection_sha256=binding.engine.record_sha256,
            expected_worker_identity=hardware.get("worker_identity"))
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


async def execute_runtime_flash(
    client: SiteWorkerControlClient, *, product_root: Path, request: JobRequest,
    active_asset_set: Mapping[str, Any] | None, job_deadline_monotonic: float,
    runtime_profile: C3FlashProfile, image_root: Path,
) -> dict[str, Any]:
    """Production REST Flash cutover; no direct-C3 fallback.

    The Runtime supplies the Set pinned under its execution lease and the one
    Job deadline (including retries). Select the sole verified Bundle Profile
    and its declared Provider. No Job/Bundle path or hardware claim is used.
    The authenticated root Worker observes its existing Root journal; native
    admission still verifies current PL identity and holds the reload fence.
    """
    try:
        _need(isinstance(active_asset_set, Mapping)
              and active_asset_set.get("state") == "ACTIVE", "OPF_ACTIVE_SET_REQUIRED")
        digest = active_asset_set.get("asset_set_sha256")
        active = ppu_asset_set.read_active(product_root)
        _need(active == dict(active_asset_set), "ACTIVE_SET_MISMATCH")
        ppu_asset_set.verify_staged(product_root, digest)
        staged = product_root / "assets" / "staged" / digest
        manifest = json.loads((staged / "manifest.json").read_bytes())
        profiles = [p for p in manifest["packages"] if p["kind"] == "programming-profile"]
        _need(len(profiles) == 1, "OPF_PROFILE_MISSING_OR_AMBIGUOUS")
        profile = profiles[0]
        handoff = (ppu_asset_set.resolve_staged_fpga_handoff(product_root, digest)
                   if any(p["kind"] == "fpga-image" for p in manifest["packages"]) else None)
        descriptor = json.loads((staged / "payload" / "packages" / profile["id"]
                                 / ppu_provider_contract.DESCRIPTOR).read_bytes())
        timeout_ms = round(request.timeout_s * 1000)
        _need(timeout_ms / 1000.0 == request.timeout_s, "OPF_TIMEOUT_PRECISION_UNSUPPORTED")
        policy = TimeoutPolicy(timeout_ms, 3600000)  # existing C-3 session ceiling
        selection = {"schema": "plasma.opf.programming.v1",
                     "provider": descriptor["provider_package"],
                     "profile": profile["id"], "options": {}}
        engine = ppu_site_engine.load_engine(require_root=True)
        remaining = job_deadline_monotonic - time.monotonic()
        _need(math.isfinite(remaining) and remaining > 0, "JOB_DEADLINE_EXPIRED")
        status = await asyncio.to_thread(client.call, "status", timeout_s=remaining)
        _need(not status.get("not_ready"), "REFERENCE_ENGINE_NOT_READY")
        identity = status.get("identity", {})
        fpga = handoff["fpga_image"] if handoff else None
        # Root/native admission owns same-boot qualification and the reload
        # fence. Ordinary Jobs bind the loaded image and unchanged Worker
        # session; historical qualification metadata is not a new Job gate.
        identity_verified = (
            identity.get("status") == "IMAGE"
            and type(identity.get("image_id")) is str and bool(identity["image_id"])
            and identity.get("boot_id") == Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            and type(identity.get("firmware_sha256")) is str
            and ppu_provider_contract.SHA64.fullmatch(identity["firmware_sha256"]) is not None
            and (fpga is None or identity["image_id"] == fpga["image_id"]))
        _need(identity_verified,
              "OPF_FPGA_IDENTITY_UNVERIFIED")
        # Platform comes from the authenticated installed Worker adapter, not
        # from the Bundle's target declarations. Live C3 Root admission still
        # verifies PL/ABI, ownership and SAFE_OFF before hardware execution.
        hardware = {**status.get("platform", {}), "sites": status["supported_sites"],
                    "loaded_fpga_package": fpga["package_id"] if fpga else None,
                    "driver_abi": f"{engine.adapter_driver}:{engine.driver_abi}",
                    "fpga_identity_proven": identity_verified, "worker_identity": identity}
        return await execute_reference_flash(
            client, product_root=product_root, asset_set_sha256=digest,
            selection=selection, policy=policy, job_id=request.job_id,
            site_id=request.site_id, target=request.target, image=request.image,
            image_root=image_root, hardware=hardware, runtime_profile=runtime_profile,
            job_deadline_monotonic=job_deadline_monotonic, job_timeout_s=request.timeout_s)
    except SiteWorkerRefused as exc:
        raise PlasmaError(ErrorCode.INTERFACE_NOT_CONFIGURED,
                          "OPF_WORKER_OBSERVATION_DENIED:" + exc.code) from exc
    except (ValueError, KeyError, TypeError, OSError, ppu_asset_set.AssetSetError,
            ppu_site_engine.EngineNotReady) as exc:
        raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                          "OPF_FLASH_DENIED:" + str(exc)) from exc
