"""Console-driven Bundle programming: Manager-side composition only.

Owner Gate 1 (2026-11-09): a Console user selects IC, image, PPU and Site;
the Manager then

1. resolves a committed Programming Route (Provider + Profile Packages),
2. builds the canonical Bundle v3 with the shared ``plasma_opf.bundle_v3``
   writer,
3. compares the Programming Resource Set the PPU derived from its own
   verified Active Set (OFE-1B; never the Manager's claim) with the Route's
   Resource Set. Same Resources: B1/B2/B3 are skipped and only the Job Image
   travels. Different or unprovable-but-replaceable Resources: the EXISTING
   Manager Bootstrap B1 upload, B2 admission and B3 ``activate``
   (``fpga_load=false``) run through ``ManagerBootstrapCoordinator`` which
   issues the device-bound owner authorizations,
   A user may instead supply their own canonical Bundle v3 (Bundle source).
   It is admitted only when its Programming Resources are byte-identical to
   the committed Route and the shared writer reproduces its exact bytes
   (``bundle_v3.route_bundle_from_archive``); from there it takes the SAME
   Resource Reuse / B1-B3 / Job path as an Image source,
4. submits exactly one Job with the user-selected Operation and its exact
   Job Binding (Resource, Operation, range, Image, PPU, Site, ICPN, Profile)
   to the PPU Gateway ``/api/jobs``; the PPU re-verifies the Binding,
5. observes ``/api/status?job=`` and verifies the PPU-echoed Binding,
   Image identity, readback SHA256, verified bytes and SAFE_OFF.

This module is deliberately NOT a deployment coordinator or execution router.
The PPU Bootstrap coordinator stays the only Bundle install/activation
authority, and the PPU Runtime stays the only Job router, lease owner and
SAFE_OFF/SEALED authority. The Manager never retries a write whose outcome is
unknown, never clears SEALED and never loads FPGA. An OUTCOME_UNKNOWN run
latches the PPU alias until an operator explicitly acknowledges reconciliation.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import secrets
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote

from plasma_opf import bundle_v3

ROUTES_ENV = "PLASMA_PROGRAMMING_ROUTES_ROOT"
ROUTES_RELATIVE = Path("data/opf/programming-routes")
RUN_SCHEMA = "plasma.manager.bundle-programming-run.v1"
PLAN_SCHEMA = "plasma.manager.bundle-programming-plan.v3"
RECEIPT_SCHEMA = "plasma.manager.programming-receipt.v2"
# Only flash_cycle has a qualified PPU backend (C-3 OpenOCD) and receipt contract.
RECEIPT_OPERATIONS = frozenset({"flash_cycle"})
FLASH_RANGE_FIELDS = ("load_address", "erase_address", "erase_length",
                      "write_address", "verify_address", "readback_address")
CONFIRM_TOKEN = "PROGRAM"
ACK_TOKEN = "OUTCOME_UNKNOWN_RECONCILED"
UPLOAD_CHUNK_BYTES = 256 * 1024
PLAN_TTL_S = 30 * 60
MAX_PLANS = 16
MAX_RUNS_RETAINED = 64
JOB_TERMINAL = frozenset({"success", "failed", "error", "cancelled", "timeout", "aborted"})
RUN_TERMINAL = frozenset({"PASS", "FAIL", "OUTCOME_UNKNOWN", "BLOCKED"})


class ProgrammingError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message

    def payload(self) -> dict[str, Any]:
        return {"ok": False, "error": {"code": self.code, "message": self.message}}


class _StepFailure(Exception):
    """Definitive, safe failure: the device state is known (no unknown write)."""

    def __init__(self, reason: str, outcome: str = "FAIL") -> None:
        super().__init__(reason)
        self.reason = reason
        self.outcome = outcome


class _OutcomeUnknown(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def default_routes_root() -> Path | None:
    """Explicit route root, else the shared Runtime Evidence Root contract.

    Never derived from this module's location (an installed wheel is not a data
    directory); ``None`` makes Programming Routes explicitly unavailable.
    """
    configured = os.environ.get(ROUTES_ENV, "").strip()
    if configured:
        return Path(configured)
    from plasma_web.runtime_evidence_root import default_runtime_evidence_root

    root = default_runtime_evidence_root()
    return None if root is None else root / ROUTES_RELATIVE


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _Plan:
    plan_id: str
    alias: str
    site: int
    created_monotonic: float
    bundle: bundle_v3.ProgrammingBundle | None
    route: bundle_v3.ProgrammingRoute
    payload: dict[str, Any]
    operation: str
    resource_set_sha256: str
    image: bytes | None
    image_asset: dict[str, Any] | None
    binding: dict[str, Any]
    binding_sha256: str


@dataclass
class _Run:
    run_id: str
    alias: str
    site: int
    plan: dict[str, Any]
    state: str = "accepted"
    outcome: str | None = None
    reason: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    steps: list[dict[str, Any]] = field(default_factory=list)
    activation: dict[str, Any] = field(default_factory=dict)
    job: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None
    job_submission_count: int = 0
    acknowledged: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": RUN_SCHEMA, "run_id": self.run_id, "ppu_alias": self.alias,
            "site_id": self.site, "plan": self.plan, "state": self.state,
            "outcome": self.outcome, "reason": self.reason,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "steps": list(self.steps), "activation": dict(self.activation),
            "job": self.job, "receipt": self.receipt,
            "job_submission_count": self.job_submission_count,
            "auto_retry": "DISABLED", "acknowledged": self.acknowledged,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "_Run":
        run = cls(run_id=str(data["run_id"]), alias=str(data["ppu_alias"]),
                  site=int(data["site_id"]), plan=dict(data.get("plan") or {}))
        for name in ("state", "outcome", "reason", "created_at", "updated_at",
                     "job", "receipt"):
            setattr(run, name, data.get(name))
        run.steps = list(data.get("steps") or [])
        run.activation = dict(data.get("activation") or {})
        run.job_submission_count = int(data.get("job_submission_count") or 0)
        run.acknowledged = bool(data.get("acknowledged"))
        return run


def _strict_base64(value: object, field: str = "image") -> bytes:
    if type(value) is not str or not value:
        raise ProgrammingError(400, f"{field}_invalid", f"{field}_base64 is required")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise ProgrammingError(400, f"{field}_invalid",
                               f"{field}_base64 is not strict base64") from exc


class BundleProgrammingWorkflow:
    def __init__(
        self,
        *,
        coordinator: Any,
        registry: Any,
        gateway_client_factory: Callable[[str, float], Any],
        gate: Any,
        request_timeout_s: float,
        routes_root: Path | None = None,
        journal_path: Path | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        spawn: Callable[[Callable[[], None]], None] | None = None,
        deployment_deadline_s: float = 300.0,
        job_deadline_s: float = 300.0,
        poll_interval_s: float = 1.0,
    ) -> None:
        self.coordinator = coordinator
        self.registry = registry
        self.gateway_client_factory = gateway_client_factory
        self.gate = gate
        self.request_timeout_s = request_timeout_s
        self.routes_root = routes_root
        self.journal_path = journal_path
        self.sleep = sleep
        self.monotonic = monotonic
        self.spawn = spawn or (lambda target: threading.Thread(
            target=target, name="plasma-bundle-programming", daemon=True).start())
        self.deployment_deadline_s = deployment_deadline_s
        self.job_deadline_s = job_deadline_s
        self.poll_interval_s = poll_interval_s
        self._lock = threading.RLock()
        self._plans: dict[str, _Plan] = {}
        self._runs: dict[str, _Run] = {}
        self._load_journal()

    # ------------------------------------------------------------------ journal
    def _load_journal(self) -> None:
        if self.journal_path is None or not self.journal_path.exists():
            return
        try:
            data = json.loads(self.journal_path.read_text(encoding="utf-8"))
            runs = data.get("runs") if isinstance(data, dict) else None
            for item in runs or []:
                run = _Run.from_dict(item)
                if run.outcome is None:
                    # Manager stopped mid-run: device-side outcome is unknown.
                    run.state = "finished"
                    run.outcome = "OUTCOME_UNKNOWN"
                    run.reason = "MANAGER_RESTARTED_DURING_RUN"
                self._runs[run.run_id] = run
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("Bundle programming journal is unreadable; refusing to start") from exc

    def _persist_locked(self) -> None:
        if self.journal_path is None:
            return
        runs = sorted(self._runs.values(), key=lambda r: r.created_at)[-MAX_RUNS_RETAINED:]
        payload = {"schema": "plasma.manager.bundle-programming-journal.v1",
                   "runs": [r.as_dict() for r in runs]}
        parent = self.journal_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{self.journal_path.name}.", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, 0o600)
            os.replace(name, self.journal_path)
        except BaseException:
            Path(name).unlink(missing_ok=True)
            raise

    def _update(self, run: _Run, **changes: Any) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(run, key, value)
            run.updated_at = _now()
            self._persist_locked()

    def _step(self, run: _Run, name: str, result: str, **detail: Any) -> None:
        with self._lock:
            run.steps.append({"step": name, "result": result, "at": _now(), **detail})
            run.updated_at = _now()
            self._persist_locked()

    # ------------------------------------------------------------------ helpers
    def _record(self, alias: str):
        record = self.registry.record_by_alias(alias)
        if record is None:
            raise ProgrammingError(404, "ppu_not_found", "configured PPU alias was not found")
        return record

    def _require_commissioned(self, alias: str):
        record = self._record(alias)
        if getattr(record, "lifecycle", None) != "commissioned":
            raise ProgrammingError(409, "ppu_not_enabled",
                                   "PPU must complete Validate & Enable before programming")
        return record

    def routes(self) -> tuple[bundle_v3.ProgrammingRoute, ...]:
        try:
            root = self.routes_root if self.routes_root is not None else default_routes_root()
            if root is None:
                raise bundle_v3.BundleBuildError("ROUTE_ROOT_UNAVAILABLE")
            return bundle_v3.load_routes(root)
        except (bundle_v3.BundleBuildError, ValueError) as exc:
            raise ProgrammingError(503, "programming_routes_unavailable",
                                   f"Programming Routes are unavailable: {exc}") from exc

    def _gateway_get(self, client: Any, path: str) -> dict[str, Any]:
        status, _headers, body = client.relay(
            "GET", path, headers={"Accept": "application/json"}, body=None,
            timeout_s=self.request_timeout_s, max_response_bytes=1024 * 1024)
        if status != 200:
            raise _StepFailure(f"GATEWAY_READ_HTTP_{status}")
        value = json.loads(body)
        if not isinstance(value, dict):
            raise _StepFailure("GATEWAY_RESPONSE_INVALID")
        return value

    def _readiness(self, client: Any, site: int, target: str | None) -> dict[str, Any]:
        health = self._gateway_get(client, "/api/health/ready")
        status = self._gateway_get(client, f"/api/status?site={site}")
        ppu = status.get("ppu") if isinstance(status.get("ppu"), dict) else {}
        lease = ppu.get("execution") if isinstance(ppu.get("execution"), dict) else {}
        activation = ppu.get("runtime_activation")
        sites = status.get("sites")
        if not (isinstance(sites, list) and len(sites) == 1 and isinstance(sites[0], dict)):
            raise _StepFailure("PPU_STATUS_UNTRUSTED")
        row = sites[0]
        ready = (health.get("ok") is True and health.get("execution") == "ready"
                 and lease.get("busy") is False and lease.get("active_job_count") == 0
                 and (not isinstance(activation, dict) or activation.get("active") is False)
                 and row.get("site_id") == site and row.get("enabled") is True
                 and row.get("state") == "idle" and row.get("current_job_id") is None
                 and row.get("queued_jobs") in (0, None))
        if not ready:
            raise _StepFailure("SITE_NOT_READY_OR_BUSY")
        if target is not None and (row.get("interface") != "openocd" or row.get("target") != target):
            raise _StepFailure("SITE_TARGET_NOT_FROM_ACTIVE_SET")
        return {"ppu_id": ppu.get("ppu_id"), "site_id": site, "state": "idle",
                "target": row.get("target"),
                "active_resources": ppu.get("active_resources")}

    def _unknown_latched(self, alias: str) -> _Run | None:
        for run in self._runs.values():
            if run.alias == alias and run.outcome == "OUTCOME_UNKNOWN" and not run.acknowledged:
                return run
        return None

    def _active_run(self, alias: str) -> _Run | None:
        for run in self._runs.values():
            if run.alias == alias and run.outcome is None:
                return run
        return None

    # --------------------------------------------------------------------- API
    def list_routes(self) -> dict[str, Any]:
        return {"ok": True, "routes": [r.summary() for r in self.routes()]}

    def _ppu_resources(self, alias: str, site: int) -> tuple[str, dict[str, Any]]:
        """PPU id + the Resource identity the PPU derived from its Active Set."""
        record = self._record(alias)
        try:
            client = self.gateway_client_factory(record.endpoint, self.request_timeout_s)
            status = self._gateway_get(client, f"/api/status?site={site}")
        except Exception as exc:  # noqa: BLE001 - read-only; never guess a reuse decision
            raise ProgrammingError(503, "ppu_resource_identity_unknown",
                                   "PPU Resource identity could not be read; nothing was changed") from exc
        ppu = status.get("ppu") if isinstance(status.get("ppu"), dict) else {}
        report = ppu.get("active_resources")
        ppu_id = ppu.get("ppu_id")
        if not isinstance(report, dict) or report.get("state") == "UNSUPPORTED":
            raise ProgrammingError(409, "ppu_runtime_resource_identity_unsupported",
                                   "PPU Runtime does not report a verified Resource identity (OFE-1B)")
        if type(ppu_id) is not str or not ppu_id:
            raise ProgrammingError(503, "ppu_resource_identity_unknown", "PPU identity is missing")
        return ppu_id, report

    def plan(self, alias: str, body: Mapping[str, Any]) -> dict[str, Any]:
        allowed = {"icpn", "site_id", "operation", "image_base64", "image_filename",
                   "bundle_base64", "address", "length"}
        if not isinstance(body, Mapping) or not {"icpn", "site_id", "operation"} <= set(body) \
                or set(body) - allowed:
            raise ProgrammingError(400, "invalid_request",
                                   "plan requires icpn, site_id, operation and the Operation's "
                                   "image_base64, bundle_base64 or address/length")
        icpn, site, operation = body["icpn"], body["site_id"], body["operation"]
        if type(icpn) is not str or not icpn.strip() or len(icpn) > 96:
            raise ProgrammingError(400, "invalid_request", "icpn is invalid")
        if type(site) is not int or isinstance(site, bool) or not 1 <= site <= 64:
            raise ProgrammingError(400, "invalid_request", "site_id is invalid")
        # The Operation is the user's choice; the Manager never rewrites it.
        if type(operation) is not str or operation not in bundle_v3.OPERATIONS:
            raise ProgrammingError(400, "invalid_request",
                                   f"operation must be one of {', '.join(bundle_v3.OPERATIONS)}")
        image_operation = operation in bundle_v3.IMAGE_OPERATIONS
        image: bytes | None = None
        archive: bytes | None = None
        address = length = None
        if image_operation:
            # Exactly one Programming Source: a Programming Image or a user Bundle.
            sources = {"image_base64", "bundle_base64"} & set(body)
            if len(sources) != 1 or {"address", "length"} & set(body) \
                    or ("bundle_base64" in body and "image_filename" in body):
                raise ProgrammingError(400, "invalid_request",
                                       f"{operation} requires exactly one of image_base64 or "
                                       "bundle_base64 and takes its range from the Image")
            if "bundle_base64" in body:
                archive = _strict_base64(body["bundle_base64"], "bundle")
                if len(archive) > bundle_v3.MAX_BUNDLE_ARCHIVE_BYTES:
                    raise ProgrammingError(413, "bundle_too_large",
                                           "Bundle exceeds the Console upload limit")
            else:
                image = _strict_base64(body["image_base64"])
                if not 0 < len(image) <= bundle_v3.MAX_IMAGE_BYTES:
                    raise ProgrammingError(413, "image_too_large",
                                           "image exceeds the Console upload limit")
        else:
            if {"image_base64", "image_filename", "bundle_base64"} & set(body) \
                    or not {"address", "length"} <= set(body):
                raise ProgrammingError(400, "invalid_request",
                                       f"{operation} requires explicit address and length and no image")
            address, length = body["address"], body["length"]
            if any(type(v) is not int or isinstance(v, bool) or v < 0 for v in (address, length)):
                raise ProgrammingError(400, "invalid_request", "address and length must be integers")
        self._require_commissioned(alias)
        matches = bundle_v3.resolve_routes(self.routes(), icpn=icpn.strip(), site=site)
        if not matches:
            raise ProgrammingError(422, "programming_route_not_found",
                                   "no Programming Route declares this IC on this Site")
        if len(matches) > 1:
            raise ProgrammingError(409, "programming_route_ambiguous",
                                   "more than one Programming Route matches; refusing to guess")
        route = matches[0]
        if operation not in route.capabilities["operations"]:
            raise ProgrammingError(422, "operation_not_in_profile",
                                   f"Programming Profile {route.profile_id} does not declare {operation}")
        built = image_asset = None
        try:
            resource = bundle_v3.resource_set_descriptor(route)
            resource_sha = bundle_v3.resource_set_sha256(resource)
            if archive is not None:
                # Bundle source: the user's own canonical Bundle, never rebuilt
                # under another identity and never trusted for its declarations.
                built, image = bundle_v3.route_bundle_from_archive(route, archive)
            elif image is not None:
                built = bundle_v3.build_user_image_bundle(
                    route, image, filename=body.get("image_filename"))
            if image is not None:
                image_asset = bundle_v3.image_asset_descriptor(resource, image)
        except bundle_v3.BundleBuildError as exc:
            code = ("bundle_resource_not_qualified"
                    if str(exc) == "BUNDLE_RESOURCE_NOT_ROUTE" else "bundle_incompatible")
            raise ProgrammingError(422, code, str(exc)) from exc
        platform = self.coordinator.status(alias)
        pairing = platform.get("pairing") or {}
        if pairing.get("paired") is not True or pairing.get("device_match") is not True:
            raise ProgrammingError(409, "bootstrap_pairing_required",
                                   "Platform maintenance pairing is required before programming")
        runtime = (platform.get("bootstrap") or {}).get("runtime") or {}
        if runtime.get("state") != "runtime_active":
            raise ProgrammingError(409, "ppu_runtime_not_active", "PPU Runtime is not active")
        active = self.coordinator.assets(alias)
        if active.get("state") == "RECOVERY_REQUIRED":
            raise ProgrammingError(409, "ppu_recovery_required",
                                   "PPU Active Asset Set requires explicit recovery")
        ppu_id, report = self._ppu_resources(alias, site)
        if report.get("state") == "VERIFIED":
            if not (active.get("state") == "ACTIVE"
                    and report.get("asset_set_sha256") == active.get("asset_set_sha256")):
                raise ProgrammingError(409, "active_set_report_inconsistent",
                                       "PPU Runtime and Bootstrap report different Active Sets")
            resource_reuse = report.get("resource_set_sha256") == resource_sha
        elif report.get("state") == "UNAVAILABLE":
            # No provable Resource identity (e.g. EMPTY or a non-canonical Set):
            # never skip deployment on a guess.
            resource_reuse = False
        else:
            raise ProgrammingError(409, "ppu_runtime_resource_identity_unsupported",
                                   "PPU Resource identity report is not recognized")
        activation_required = not resource_reuse
        if activation_required and built is None:
            raise ProgrammingError(409, "resource_activation_requires_image",
                                   f"{operation} needs these Programming Resources already Active; "
                                   "program an Image first")
        try:
            binding = bundle_v3.job_image_binding(
                resource, image_asset, ppu_id=ppu_id, site_id=site, operation=operation,
                address=address, length=length)
        except bundle_v3.BundleBuildError as exc:
            raise ProgrammingError(422, "job_binding_invalid", str(exc)) from exc
        binding_sha = bundle_v3.sha256_hex(bundle_v3.canonical_json(binding))
        plan_id = secrets.token_hex(16)
        payload = {
            "schema": PLAN_SCHEMA, "plan_id": plan_id, "ppu_alias": alias,
            "site_id": site, "operation": operation,
            "source": ("bundle" if archive is not None
                       else "image" if image is not None else "range"),
            "route": route.summary(),
            "bundle": None if built is None else built.summary(),
            "resource": {
                "resource_set_sha256": resource_sha,
                "ppu_reported": {k: report.get(k) for k in (
                    "state", "asset_set_sha256", "generation", "resource_set_sha256")},
                "reuse": resource_reuse,
            },
            "image_asset": None if image_asset is None else {
                "image_asset_sha256": bundle_v3.image_asset_sha256(image_asset),
                "sha256": image_asset["sha256"], "size": image_asset["size"],
                "load_address": image_asset["load_address"], "format": image_asset["format"]},
            "job_binding": binding, "job_binding_sha256": binding_sha,
            "active_asset_set": {"state": active.get("state"),
                                 "asset_set_sha256": active.get("asset_set_sha256")},
            "activation_required": activation_required,
            "fpga_load": False,
            "steps": (["B1_UPLOAD", "B2_ADMIT", "B3_ACTIVATE"] if activation_required
                      else ["RESOURCE_REUSE"])
                     + [f"{operation.upper()}_JOB", "VERIFY_RECEIPT"],
            "catalog_gate": "NOT_USED",
            "confirm_required": CONFIRM_TOKEN,
        }
        with self._lock:
            now = self.monotonic()
            for key in [k for k, p in self._plans.items() if now - p.created_monotonic > PLAN_TTL_S]:
                del self._plans[key]
            while len(self._plans) >= MAX_PLANS:
                del self._plans[min(self._plans, key=lambda k: self._plans[k].created_monotonic)]
            self._plans[plan_id] = _Plan(
                plan_id, alias, site, now, built, route, payload, operation=operation,
                resource_set_sha256=resource_sha, image=image, image_asset=image_asset,
                binding=binding, binding_sha256=binding_sha)
        return {"ok": True, "plan": payload}

    def start(self, alias: str, body: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(body, Mapping) or set(body) != {"plan_id", "confirm"}:
            raise ProgrammingError(400, "invalid_request", "run requires only plan_id and confirm")
        if body["confirm"] != CONFIRM_TOKEN:
            raise ProgrammingError(400, "confirmation_required",
                                   "explicit programming confirmation is required")
        self._require_commissioned(alias)
        with self._lock:
            plan = self._plans.get(body["plan_id"]) if type(body["plan_id"]) is str else None
            if (plan is None or plan.alias != alias
                    or self.monotonic() - plan.created_monotonic > PLAN_TTL_S):
                raise ProgrammingError(404, "programming_plan_not_found",
                                       "programming plan (Bundle) is missing or expired; prepare again")
            latched = self._unknown_latched(alias)
            if latched is not None:
                raise ProgrammingError(409, "programming_outcome_unknown_unresolved",
                                       f"run {latched.run_id} ended OUTCOME_UNKNOWN; reconcile and acknowledge first")
            if self._active_run(alias) is not None:
                raise ProgrammingError(409, "programming_run_in_progress",
                                       "another programming run is in progress on this PPU")
            # One plan, one run: a consumed plan can never be re-submitted.
            del self._plans[plan.plan_id]
            run = _Run(run_id=secrets.token_hex(16), alias=alias, site=plan.site,
                       plan=plan.payload)
            self._runs[run.run_id] = run
            self._persist_locked()
        self.spawn(lambda: self._execute(run, plan))
        return {"ok": True, "run": run.as_dict()}

    def run_status(self, alias: str, run_id: str) -> dict[str, Any]:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.alias != alias:
                raise ProgrammingError(404, "programming_run_not_found", "programming run was not found")
            return {"ok": True, "run": run.as_dict()}

    def acknowledge(self, alias: str, run_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(body, Mapping) or set(body) != {"acknowledge"} or body["acknowledge"] != ACK_TOKEN:
            raise ProgrammingError(400, "invalid_request",
                                   f"acknowledge requires acknowledge={ACK_TOKEN}")
        with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.alias != alias:
                raise ProgrammingError(404, "programming_run_not_found", "programming run was not found")
            if run.outcome != "OUTCOME_UNKNOWN":
                raise ProgrammingError(409, "programming_run_not_unknown",
                                       "only OUTCOME_UNKNOWN runs require acknowledgement")
            run.acknowledged = True
            run.updated_at = _now()
            self._persist_locked()
            return {"ok": True, "run": run.as_dict()}

    # ---------------------------------------------------------------- execution
    def _execute(self, run: _Run, plan: _Plan) -> None:
        try:
            record = self._record(run.alias)
            client = self.gateway_client_factory(record.endpoint, self.request_timeout_s)
            # LOM-P2A-2 G13: Job submission is signed under the enrolled controller.
            signer = getattr(self.coordinator, "gateway_signer", None)
            if signer is not None and hasattr(client, "write_signer"):
                client.write_signer = signer(run.alias)
            self._update(run, state="preflight")
            self._readiness(client, run.site, None)
            self._step(run, "PREFLIGHT", "PASS")
            activated = plan.payload["activation_required"]
            if activated:
                self._activate(run, plan)
            active = self.coordinator.assets(run.alias)
            expected_set = (plan.bundle.archive_sha256 if activated
                            else plan.payload["active_asset_set"]["asset_set_sha256"])
            if not (active.get("state") == "ACTIVE"
                    and active.get("asset_set_sha256") == expected_set):
                raise _StepFailure("ACTIVE_SET_MISMATCH_AFTER_ACTIVATION" if activated
                                   else "ACTIVE_SET_CHANGED_SINCE_PLAN")
            self._update(run, state="submitting")
            ready = self._readiness(client, run.site, plan.route.icpn)
            # The PPU itself must prove the Resources the Job is bound to.
            report = ready.get("active_resources")
            if not (isinstance(report, dict) and report.get("state") == "VERIFIED"
                    and report.get("asset_set_sha256") == expected_set
                    and report.get("resource_set_sha256") == plan.resource_set_sha256
                    and ready.get("ppu_id") == plan.binding["ppu_id"]):
                raise _StepFailure("RESOURCE_IDENTITY_NOT_CONFIRMED")
            if not activated:
                self._step(run, "RESOURCE_REUSE", "PPU_VERIFIED",
                           asset_set_sha256=expected_set,
                           resource_set_sha256=plan.resource_set_sha256,
                           generation=report.get("generation"))
            job_id = self._submit_once(run, plan, client)
            self._update(run, state="running")
            job = self._poll_job(run, client, job_id)
            self._verify(run, plan, job)
        except _OutcomeUnknown as exc:
            self._update(run, state="finished", outcome="OUTCOME_UNKNOWN", reason=exc.reason)
        except _StepFailure as exc:
            self._update(run, state="finished", outcome=exc.outcome, reason=exc.reason)
        except ProgrammingError as exc:
            self._update(run, state="finished", outcome="BLOCKED", reason=exc.code)
        except Exception as exc:  # noqa: BLE001 - any unexpected error is reported, never retried
            self._update(run, state="finished", outcome="OUTCOME_UNKNOWN",
                         reason=f"UNEXPECTED_{type(exc).__name__}")

    def _activate(self, run: _Run, plan: _Plan) -> None:
        alias, archive = run.alias, plan.bundle.archive
        digest = plan.bundle.archive_sha256
        if not self.gate.try_begin_platform_launch(alias):
            raise _StepFailure("PPU_CONTROL_PLANE_BUSY", outcome="BLOCKED")
        try:
            self._update(run, state="activating")
            try:
                status, created = self.coordinator.create_upload(
                    alias, {"size": len(archive), "sha256": digest})
                upload = created.get("upload") if isinstance(created, dict) else None
                upload_id = upload.get("upload_id") if isinstance(upload, dict) else None
                if status not in (200, 201) or type(upload_id) is not str:
                    raise _StepFailure("B1_UPLOAD_REJECTED")
                for offset in range(0, len(archive), UPLOAD_CHUNK_BYTES):
                    part = archive[offset:offset + UPLOAD_CHUNK_BYTES]
                    status, receipt = self.coordinator.append_chunk(alias, upload_id, {
                        "offset": offset, "data_base64": base64.b64encode(part).decode("ascii"),
                        "sha256": bundle_v3.sha256_hex(part)})
                    got = receipt.get("upload") if isinstance(receipt, dict) else None
                    if status != 200 or not isinstance(got, dict) or got.get("received_bytes") != offset + len(part):
                        raise _StepFailure("B1_CHUNK_REJECTED")
                status, committed = self.coordinator.commit_upload(alias, upload_id)
                got = committed.get("upload") if isinstance(committed, dict) else None
                if status != 200 or not isinstance(got, dict) or got.get("state") != "committed" \
                        or got.get("sha256") != digest:
                    raise _StepFailure("B1_COMMIT_REJECTED")
                self._step(run, "B1_UPLOAD", "PASS", upload_id=upload_id, size=len(archive))
                status, admitted = self.coordinator.start_deployment(
                    alias, {"kind": "bundle", "upload_id": upload_id, "archive_sha256": digest})
                b2 = admitted.get("deployment") if isinstance(admitted, dict) else None
                if status not in (200, 202) or not isinstance(b2, dict) or b2.get("state") != "admitted" \
                        or type(b2.get("transaction_id")) is not str:
                    raise _StepFailure("B2_ADMISSION_REJECTED")
                admission_tx = b2["transaction_id"]
                self._step(run, "B2_ADMIT", "PASS", transaction_id=admission_tx)
            except _StepFailure:
                raise
            except Exception as exc:  # B1/B2 never activate anything: definitive failure.
                raise _StepFailure(f"B1_B2_FAILED_{type(exc).__name__}") from exc
            # After this point a failure is never definitive: B3 may have started.
            try:
                status, queued = self.coordinator.start_deployment(alias, {
                    "kind": "bundle", "upload_id": upload_id, "archive_sha256": digest,
                    "admission_transaction_id": admission_tx, "mode": "activate",
                    "fpga_load": False})
            except Exception as exc:
                raise _OutcomeUnknown("B3_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT") from exc
            b3 = queued.get("deployment") if isinstance(queued, dict) else None
            if status not in (200, 202) or not isinstance(b3, dict) or type(b3.get("transaction_id")) is not str:
                raise _OutcomeUnknown("B3_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT")
            b3_tx = b3["transaction_id"]
            self._update(run, activation={"upload_id": upload_id, "admission_transaction_id": admission_tx,
                                          "b3_transaction_id": b3_tx, "mode": "activate",
                                          "fpga_load": False})
            self._step(run, "B3_SUBMIT", "QUEUED", transaction_id=b3_tx)
        finally:
            self.gate.end_platform_launch(alias)
        deadline = self.monotonic() + self.deployment_deadline_s
        while True:
            try:
                deployment = ((self.coordinator.status(alias).get("bootstrap") or {})
                              .get("deployment") or {})
            except Exception as exc:
                raise _OutcomeUnknown("B3_STATE_UNKNOWN_DO_NOT_RESUBMIT") from exc
            if deployment.get("transaction_id") != b3_tx:
                raise _OutcomeUnknown("B3_TRANSACTION_IDENTITY_UNKNOWN")
            state = deployment.get("state")
            if state == "succeeded":
                result = deployment.get("result")
                if not isinstance(result, dict) or result.get("result") != "PASS":
                    raise _OutcomeUnknown("B3_SUCCESS_EVIDENCE_MISSING")
                self._step(run, "B3_ACTIVATE", "PASS", transaction_id=b3_tx)
                return
            if state in ("failed",):
                raise _StepFailure("B3_FAILED")
            if state not in ("queued", "running"):
                raise _OutcomeUnknown(f"B3_STATE_{str(state).upper()}")
            if self.monotonic() >= deadline:
                raise _OutcomeUnknown("B3_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT")
            self.sleep(self.poll_interval_s)

    def _submit_once(self, run: _Run, plan: _Plan, client: Any) -> str:
        # Job Image source (OFE-1B): the user's Operation + exact Binding; the
        # Image travels once with the Job, never as a new Resource Bundle.
        payload: dict[str, Any] = {
            "site_id": run.site, "operation": plan.operation, "timeout_s": 180.0,
            "target": plan.route.icpn, "provider": plan.route.provider_id,
            "profile": plan.route.profile_id, "job_binding": plan.binding,
        }
        if plan.image is not None:
            payload["image_asset"] = plan.image_asset
            payload["asset_base64"] = base64.b64encode(plan.image).decode("ascii")
        if not self.gate.try_begin_managed_write(run.alias):
            raise _StepFailure("PPU_PLATFORM_MAINTENANCE_STARTING", outcome="BLOCKED")
        try:
            self._update(run, job_submission_count=1)
            try:
                status, _headers, body = client.relay(
                    "POST", "/api/jobs",
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                    body=json.dumps(payload, sort_keys=True).encode("utf-8"),
                    timeout_s=max(self.request_timeout_s, 18.0), max_response_bytes=65536)
            except Exception as exc:
                raise _OutcomeUnknown("JOB_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT") from exc
        finally:
            self.gate.end_managed_write(run.alias)
        if status != 202:
            if 400 <= status < 500:
                raise _StepFailure(f"JOB_SUBMISSION_REJECTED_HTTP_{status}")
            raise _OutcomeUnknown(f"JOB_SUBMISSION_HTTP_{status}_DO_NOT_RESUBMIT")
        try:
            job = json.loads(body).get("job")
            job_id = job["job_id"]
            if type(job_id) is not str or not job_id:
                raise ValueError
        except Exception as exc:
            raise _OutcomeUnknown("JOB_ID_UNKNOWN_DO_NOT_RESUBMIT") from exc
        self._update(run, job={"job_id": job_id, "state": job.get("state")})
        self._step(run, f"{plan.operation.upper()}_SUBMIT", "ACCEPTED", job_id=job_id)
        return job_id

    def _poll_job(self, run: _Run, client: Any, job_id: str) -> dict[str, Any]:
        deadline = self.monotonic() + self.job_deadline_s
        while True:
            try:
                job = self._gateway_get(client, "/api/status?job=" + quote(job_id, safe="")).get("job")
            except Exception as exc:
                raise _OutcomeUnknown("JOB_STATUS_UNKNOWN_DO_NOT_RESUBMIT") from exc
            if not isinstance(job, dict) or job.get("job_id") != job_id:
                raise _OutcomeUnknown("JOB_STATUS_IDENTITY_UNKNOWN")
            progress = {k: job.get(k) for k in ("job_id", "state", "stage", "progress_percent",
                                                "bytes_done", "bytes_total")}
            self._update(run, job=progress)
            if job.get("state") in JOB_TERMINAL:
                return job
            if job.get("state") not in ("queued", "running") or self.monotonic() >= deadline:
                raise _OutcomeUnknown("JOB_RESULT_UNKNOWN_DO_NOT_RESUBMIT")
            self.sleep(self.poll_interval_s)

    def _verify(self, run: _Run, plan: _Plan, job: dict[str, Any]) -> None:
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        details = result.get("details") if isinstance(result.get("details"), dict) else {}
        flash = details.get("flash_cycle") if isinstance(details.get("flash_cycle"), dict) else {}
        echo = job.get("job_binding") if isinstance(job.get("job_binding"), dict) else {}
        binding = plan.binding
        expected_sha = None if plan.image is None else bundle_v3.sha256_hex(plan.image)
        expected_size = None if plan.image is None else len(plan.image)
        # The Job Binding range is the write window; flash_base is only the
        # bank start. The PPU reports the range it actually executed.
        unit = plan.route.flash_profile["erase_granularity"]
        job_range = binding["range"]
        expected_range = {
            "load_address": job_range["address"], "erase_address": job_range["address"],
            "erase_length": -(-job_range["length"] // unit) * unit,
            "write_address": job_range["address"], "verify_address": job_range["address"],
            "readback_address": job_range["address"]}
        observed_range = {key: flash.get(key) for key in FLASH_RANGE_FIELDS}
        # Expected (Manager plan) / Observed (PPU) / Readback are kept distinct.
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "job_id": job.get("job_id"), "job_state": job.get("state"),
            "site_id": job.get("site_id"), "operation": job.get("operation"),
            "target": plan.route.icpn, "ppu_id": binding["ppu_id"],
            "expected_image_sha256": expected_sha, "expected_image_size": expected_size,
            "observed_image_sha256": result.get("image_sha256"),
            "observed_image_size": result.get("image_size"),
            "readback_sha256": flash.get("readback_sha256"),
            "bytes_verified": flash.get("bytes_verified"),
            "expected_flash_range": expected_range, "observed_flash_range": observed_range,
            "expected_resource_set_sha256": plan.resource_set_sha256,
            "observed_resource_set_sha256": echo.get("resource_set_sha256"),
            "expected_job_binding_sha256": plan.binding_sha256,
            "observed_job_binding_sha256": echo.get("job_binding_sha256"),
            "expected_image_asset_sha256": binding["image_asset_sha256"],
            "observed_image_asset_sha256": echo.get("image_asset_sha256"),
            "active_asset_set_sha256": echo.get("asset_set_sha256"),
            "active_generation": echo.get("generation"),
            "resource_reuse": not plan.payload["activation_required"],
            "safe_off": flash.get("safe_off"), "flash_result": flash.get("result"),
            "attempts": result.get("attempts"), "error": result.get("error"),
            "elapsed_ms": result.get("elapsed_ms"),
        }
        # SAFE_OFF first so an unsafe end state is always the reported reason.
        checks = [
            (flash.get("safe_off") is True, "SAFE_OFF_NOT_VERIFIED"),
            (plan.operation in RECEIPT_OPERATIONS, "OPERATION_RECEIPT_UNSUPPORTED"),
            (job.get("state") == "success" and result.get("state") == "success", "JOB_NOT_SUCCESS"),
            (job.get("site_id") == run.site and job.get("operation") == plan.operation,
             "JOB_IDENTITY_MISMATCH"),
            (echo.get("job_binding_sha256") == plan.binding_sha256
             and echo.get("resource_set_sha256") == plan.resource_set_sha256
             and echo.get("image_asset_sha256") == binding["image_asset_sha256"]
             and echo.get("operation") == plan.operation
             and echo.get("range") == job_range
             and echo.get("site_id") == run.site
             and echo.get("ppu_id") == binding["ppu_id"], "JOB_BINDING_NOT_CONFIRMED"),
            (result.get("image_sha256") == expected_sha
             and result.get("image_size") == expected_size, "IMAGE_IDENTITY_MISMATCH"),
            (result.get("attempts") == 1, "JOB_ATTEMPTS_NOT_ONE"),
            (flash.get("result") == "PASS", "FLASH_CYCLE_NOT_PASS"),
            (flash.get("readback_sha256") == expected_sha, "READBACK_SHA256_MISMATCH"),
            (flash.get("bytes_verified") == expected_size, "VERIFIED_BYTES_MISMATCH"),
            (observed_range == expected_range, "FLASH_RANGE_MISMATCH"),
        ]
        failed = [reason for ok, reason in checks if not ok]
        outcome = "PASS" if not failed else "FAIL"
        self._step(run, "VERIFY_RECEIPT", outcome, failed_checks=failed)
        self._update(run, state="finished", outcome=outcome,
                     reason=None if not failed else failed[0], receipt=receipt)
