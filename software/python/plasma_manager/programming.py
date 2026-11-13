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
4. submits exactly one Job with its exact Job Binding (Resource, Operation,
   range, Image, PPU, Site, ICPN, Profile) to the PPU Gateway ``/api/jobs``;
   the PPU re-verifies the Binding. The formal model is ONE ``programming``
   Job carrying the user's ordered ``operations`` list (erase -> program ->
   verify; any legal selection, all three included): one Job ID, one Site
   lease, one Binding and one receipt. ``read`` is an independent Job whose
   bytes the Manager fetches and re-hashes. ``flash_cycle`` is the legacy
   complete cycle, kept unchanged until the new model is HIL qualified,
5. observes ``/api/status?job=`` and verifies the PPU-echoed Binding, Image
   identity, every listed step's range / readback evidence and SAFE_OFF.

This module is deliberately NOT a deployment coordinator or execution router.
The PPU Bootstrap coordinator stays the only Bundle install/activation
authority, and the PPU Runtime stays the only Job router, lease owner and
SAFE_OFF/SEALED authority. The Manager never retries a write whose outcome is
unknown, never clears SEALED and never loads FPGA. An OUTCOME_UNKNOWN run
latches the PPU alias until an operator explicitly acknowledges reconciliation.

Start Outcome Reconciliation (docs/architecture/
programming-start-reconciliation-v1.md): every Start carries a Manager-issued
``start_id`` (a run's ``plan_id``, or the ID issued for a Batch). The issue and
the admission are journalled before any answer can be lost, so a Console that
never saw the Start answer can ask, read-only, what became of it.
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
RECEIPT_SCHEMA = "plasma.manager.programming-receipt.v3"
# Job kinds with a PPU backend (C-3 OpenOCD) and a receipt contract. A single
# erase / program / verify is never a Job: it is a step of ``programming``.
PROGRAMMING = bundle_v3.PROGRAMMING
RECEIPT_OPERATIONS = frozenset({"flash_cycle", PROGRAMMING, "read"})
READ_OUTPUT_MAX_BYTES = 16 * 1024 * 1024
MAX_READ_OUTPUTS_RETAINED = 8
FLASH_RANGE_FIELDS = ("load_address", "erase_address", "erase_length",
                      "write_address", "verify_address", "readback_address")
START_SCHEMA = "plasma.manager.programming-start-reconciliation.v1"
VOID_TOKEN = "VOID_UNSTARTED_START"
MAX_STARTS_RETAINED = 256
MAX_PENDING_BATCH_STARTS = 16
CONFIRM_TOKEN = "PROGRAM"
ACK_TOKEN = "OUTCOME_UNKNOWN_RECONCILED"
UPLOAD_CHUNK_BYTES = 256 * 1024
PLAN_TTL_S = 30 * 60
MAX_PLANS = 16
#: Bundle v3 and the Resource Set are pure functions of the Route and the
#: bytes, so a Batch walking many Sites behind one Route builds them once.
MAX_BUNDLE_CACHE = 4
MAX_RUNS_RETAINED = 64
JOB_TERMINAL = frozenset({"success", "failed", "error", "cancelled", "timeout", "aborted"})
RUN_TERMINAL = frozenset({"PASS", "FAIL", "OUTCOME_UNKNOWN", "BLOCKED"})

#: Failure domains. What failed decides who is stopped, and an exception
#: type, an HTTP status or a timeout never decides this on its own.
#:  * ``TARGET_NOT_READY``        - this PPU says, readably, that it cannot be
#:                                  operated now. Block this Target.
#:  * ``TARGET_STATE_UNAVAILABLE``- this PPU's own state cannot be read while
#:                                  nothing has been submitted for it. The
#:                                  doubt is local: block this Target.
#:  * ``TARGET_TRANSACTION_UNKNOWN`` - a Job for this PPU may have been
#:                                  submitted and its result is unknown. Latch
#:                                  this PPU; never resend.
#:  * ``SHARED_CONTROL_FAILURE``  - the Manager's own shared safety control is
#:                                  not usable. Nothing further is submitted,
#:                                  for any PPU.
TARGET_NOT_READY = "TARGET_NOT_READY"
TARGET_STATE_UNAVAILABLE = "TARGET_STATE_UNAVAILABLE"
TARGET_TRANSACTION_UNKNOWN = "TARGET_TRANSACTION_UNKNOWN"
SHARED_CONTROL_FAILURE = "SHARED_CONTROL_FAILURE"


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
    operations: list[str] | None
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
        self._bundle_cache: dict[tuple, tuple] = {}
        #: How many times a Bundle / Resource Set was actually built. A Batch
        #: over several Sites of one PPU must not move this more than once.
        self._bundle_builds = 0
        self._runs: dict[str, _Run] = {}
        self._read_outputs: dict[str, bytes] = {}
        # Start admission records (journalled) and the Batch start IDs that
        # may still be admitted (memory only, like plans: a restart ends them).
        self._starts: dict[str, dict[str, Any]] = {}
        self._pending_batch_starts: dict[str, tuple[str, float]] = {}
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
            starts = data.get("starts") if isinstance(data, dict) else None
            for item in starts or []:
                if (type(item["start_id"]) is not str or type(item["ppu_alias"]) is not str
                        or item["kind"] not in ("run", "batch")
                        or item["state"] not in ("ISSUED", "CONSUMED", "VOIDED")):
                    raise ValueError("start record")
                self._starts[item["start_id"]] = dict(item)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("Bundle programming journal is unreadable; refusing to start") from exc

    def _persist_locked(self) -> None:
        if self.journal_path is None:
            return
        runs = sorted(self._runs.values(), key=lambda r: r.created_at)[-MAX_RUNS_RETAINED:]
        starts = sorted(self._starts.values(), key=lambda s: s["issued_at"])
        for stale in starts[:-MAX_STARTS_RETAINED]:
            # A dropped record is never read as "not accepted": an unrecorded
            # start_id reconciles to OUTCOME_UNKNOWN.
            del self._starts[stale["start_id"]]
        payload = {"schema": "plasma.manager.bundle-programming-journal.v1",
                   "runs": [r.as_dict() for r in runs],
                   "starts": starts[-MAX_STARTS_RETAINED:]}
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

    def target_block(self, alias: str, site: int) -> tuple[str, str] | None:
        """Why this Target may not be operated now, and WHOSE failure it is.

        Read-only. The PPU must be reachable, its Site idle with no Job and no
        held execution lease, no run of this PPU active or OUTCOME_UNKNOWN,
        and the Active Asset Set must not require recovery. Any doubt blocks
        it.

        Every answer here is about ONE PPU, and says so. A PPU that readably
        refuses is ``TARGET_NOT_READY``; a PPU whose own state cannot be read
        is ``TARGET_STATE_UNAVAILABLE``, which is still local because nothing
        has been submitted for it. Nothing in this method may conclude that
        the Manager's shared control failed - that judgement belongs to the
        caller that owns the shared control.
        """
        with self._lock:
            if self._unknown_latched(alias) is not None:
                return TARGET_NOT_READY, "OUTCOME_UNKNOWN_UNRESOLVED"
            if self._active_run(alias) is not None:
                return TARGET_NOT_READY, "RUN_IN_PROGRESS"
        try:
            record = self._record(alias)
        except ProgrammingError as exc:
            return TARGET_NOT_READY, exc.code.upper()
        if getattr(record, "lifecycle", None) != "commissioned":
            return TARGET_NOT_READY, "PPU_NOT_ENABLED"
        try:
            if self.coordinator.assets(alias).get("state") == "RECOVERY_REQUIRED":
                return TARGET_NOT_READY, "PPU_RECOVERY_REQUIRED"
            client = self.gateway_client_factory(record.endpoint, self.request_timeout_s)
            self._readiness(client, site, None)
        except _StepFailure as exc:
            return TARGET_NOT_READY, exc.reason
        except Exception as exc:  # noqa: BLE001 - unreadable state is never "released"
            return TARGET_STATE_UNAVAILABLE, f"PPU_STATE_UNREADABLE_{type(exc).__name__}"
        return None

    def retry_block(self, alias: str, site: int) -> str | None:
        """``target_block`` as a bare reason (None: nothing blocks a retry)."""
        verdict = self.target_block(alias, site)
        return None if verdict is None else verdict[1]

    def batch_start_alias(self, start_id: object) -> str | None:
        """The PPU a still-admissible Batch start was issued for.

        The start ID is an idempotency token, not an authority: each Target's
        own authority is verified independently. Resolving the PPU it was
        ISSUED for, rather than reading it off the first Target, keeps a legal
        start legal however the Target Set happens to be ordered.
        """
        with self._lock:
            pending = (self._pending_batch_starts.get(start_id)
                       if type(start_id) is str else None)
            return None if pending is None else pending[0]

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

    def _route_resources(self, route: bundle_v3.ProgrammingRoute, *,
                         image: bytes | None, archive: bytes | None,
                         filename: str | None) -> tuple:
        """Bundle v3, the Resource Set and the Image Asset for one Route.

        All three are pure functions of the Route and the submitted bytes, so
        a Batch that walks several Sites behind the same Route computes them
        once and reuses them. What is reused is the COMPUTATION, never its
        authorisation: the caller still reads the Platform state, the PPU's
        Active Generation and its Resource Identity for every Site, and every
        Site still gets its own plan, Job Binding and Job.
        """
        key = (bundle_v3.sha256_hex(bundle_v3.canonical_json(route.summary())),
               None if archive is None else bundle_v3.sha256_hex(archive),
               None if image is None else bundle_v3.sha256_hex(image),
               filename)
        with self._lock:
            cached = self._bundle_cache.get(key)
        if cached is not None:
            return cached
        resource = bundle_v3.resource_set_descriptor(route)
        resource_sha = bundle_v3.resource_set_sha256(resource)
        built = image_asset = None
        derived = image
        if archive is not None:
            # Bundle source: the user's own canonical Bundle, never rebuilt
            # under another identity and never trusted for its declarations.
            built, derived = bundle_v3.route_bundle_from_archive(route, archive)
        elif image is not None:
            built = bundle_v3.build_user_image_bundle(route, image, filename=filename)
        if derived is not None:
            image_asset = bundle_v3.image_asset_descriptor(resource, derived)
        value = (resource, resource_sha, built, derived, image_asset)
        with self._lock:
            self._bundle_builds += 1
            while len(self._bundle_cache) >= MAX_BUNDLE_CACHE:
                self._bundle_cache.pop(next(iter(self._bundle_cache)))
            self._bundle_cache[key] = value
        return value

    def _parse_request(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Everything a programming request can be judged on by itself.

        No PPU, registry, Route or Bundle is touched here. A Batch has to be
        able to call a request invalid before it reads any Target's readiness,
        so an illegal operations list or an unusable Image is refused even
        when every PPU in the Target Set happens to be unready.
        """
        allowed = {"icpn", "site_id", "operation", "operations", "image_base64",
                   "image_filename", "bundle_base64", "address", "length"}
        if not isinstance(body, Mapping) or not {"icpn", "site_id"} <= set(body) \
                or len({"operation", "operations"} & set(body)) != 1 or set(body) - allowed:
            raise ProgrammingError(400, "invalid_request",
                                   "plan requires icpn, site_id, exactly one of operations "
                                   "(erase/program/verify list) or operation (read, flash_cycle) "
                                   "and its image_base64, bundle_base64 or address/length")
        icpn, site = body["icpn"], body["site_id"]
        operations: list[str] | None = None
        if "operations" in body:
            # The formal model: one programming Job with the user's ordered list.
            try:
                operations = bundle_v3.normalize_operations(body["operations"])
            except bundle_v3.BundleBuildError as exc:
                raise ProgrammingError(
                    422 if str(exc) == "JOB_OPERATIONS_ERASE_VERIFY_UNSUPPORTED" else 400,
                    "operations_invalid",
                    "Erase + Verify without Program is not supported: Verify compares the IC "
                    "with the Programming Image, which an erased IC can never equal"
                    if str(exc) == "JOB_OPERATIONS_ERASE_VERIFY_UNSUPPORTED" else
                    "operations must be a non-empty erase -> program -> verify list "
                    "in that order without repeats") from exc
            operation = PROGRAMMING
        else:
            operation = body["operation"]
            if operation in bundle_v3.SEQUENCE_OPERATIONS:
                raise ProgrammingError(
                    400, "invalid_request",
                    f"{operation} is a step of one programming Job; send operations: "
                    f"[\"{operation}\"] instead of a separate operation")
        if type(icpn) is not str or not icpn.strip() or len(icpn) > 96:
            raise ProgrammingError(400, "invalid_request", "icpn is invalid")
        if type(site) is not int or isinstance(site, bool) or not 1 <= site <= 64:
            raise ProgrammingError(400, "invalid_request", "site_id is invalid")
        # The Operation is the user's choice; the Manager never rewrites it.
        if operations is None and (type(operation) is not str
                                   or operation not in ("read", "flash_cycle")):
            raise ProgrammingError(400, "invalid_request",
                                   "operation must be read or flash_cycle")
        image_operation = (bundle_v3.operations_take_image(operations)
                           if operations is not None
                           else operation in bundle_v3.IMAGE_OPERATIONS)
        label = "+".join(operations) if operations is not None else operation
        image: bytes | None = None
        archive: bytes | None = None
        address = length = None
        if image_operation:
            # Exactly one Programming Source: a Programming Image or a user Bundle.
            sources = {"image_base64", "bundle_base64"} & set(body)
            if len(sources) != 1 or {"address", "length"} & set(body) \
                    or ("bundle_base64" in body and "image_filename" in body):
                raise ProgrammingError(400, "invalid_request",
                                       f"{label} requires exactly one of image_base64 or "
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
                                       f"{label} requires explicit address and length and no image")
            address, length = body["address"], body["length"]
            if any(type(v) is not int or isinstance(v, bool) or v < 0 for v in (address, length)):
                raise ProgrammingError(400, "invalid_request", "address and length must be integers")
        return {"icpn": icpn, "site": site, "operations": operations,
                "operation": operation, "image_operation": image_operation,
                "label": label, "image": image, "archive": archive,
                "address": address, "length": length}

    def validate_specification(self, body: Mapping[str, Any]) -> None:
        """Validate a Batch-level programming specification. Touches no PPU.

        A Batch carries no Site of its own, so a Site in range stands in for
        one. Nothing Site-specific is decided here, and each Target's own Site
        was already validated with the Target Set.
        """
        self._parse_request({**dict(body), "site_id": 1})

    def plan(self, alias: str, body: Mapping[str, Any]) -> dict[str, Any]:
        parsed = self._parse_request(body)
        icpn, site = parsed["icpn"], parsed["site"]
        operations, operation = parsed["operations"], parsed["operation"]
        label, image, archive = parsed["label"], parsed["image"], parsed["archive"]
        address, length = parsed["address"], parsed["length"]
        self._require_commissioned(alias)
        routes = self.routes()
        required = operations or [operation]
        if not bundle_v3.resolve_routes(routes, icpn=icpn.strip(), site=site):
            raise ProgrammingError(422, "programming_route_not_found",
                                   "no Programming Route declares this IC on this Site")
        # The Route is the one whose Profile declares every basic operation of
        # this Job (the legacy flash_cycle Route stays its own Resource Set).
        matches = bundle_v3.resolve_routes(routes, icpn=icpn.strip(), site=site,
                                           operations=required)
        if not matches:
            raise ProgrammingError(
                422, "operation_not_in_profile",
                "no Programming Profile for this IC and Site declares " + ", ".join(required))
        if len(matches) > 1:
            raise ProgrammingError(409, "programming_route_ambiguous",
                                   "more than one Programming Route matches; refusing to guess")
        route = matches[0]
        try:
            resource, resource_sha, built, image, image_asset = self._route_resources(
                route, image=image, archive=archive, filename=body.get("image_filename"))
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
                                   f"{label} needs these Programming Resources already Active; "
                                   "program an Image first")
        try:
            binding = bundle_v3.job_image_binding(
                resource, image_asset, ppu_id=ppu_id, site_id=site, operation=operation,
                address=address, length=length, operations=operations)
        except bundle_v3.BundleBuildError as exc:
            raise ProgrammingError(422, "job_binding_invalid", str(exc)) from exc
        binding_sha = bundle_v3.sha256_hex(bundle_v3.canonical_json(binding))
        plan_id = secrets.token_hex(16)
        payload = {
            "schema": PLAN_SCHEMA, "plan_id": plan_id, "ppu_alias": alias,
            "site_id": site, "operation": operation,
            # The ordered list one programming Job runs (null: read / legacy flash_cycle).
            "operations": operations,
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
                     + [f"{operation.upper()}_JOB", "VERIFY_RECEIPT"]
                     + (["FETCH_READ_OUTPUT"] if operation == "read" else []),
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
                operations=operations, resource_set_sha256=resource_sha, image=image, image_asset=image_asset,
                binding=binding, binding_sha256=binding_sha)
            # The plan_id is the run's start_id: its issue is journalled so a
            # start that never arrives can later be proven "not accepted".
            self._starts[plan_id] = {
                "start_id": plan_id, "kind": "run", "ppu_alias": alias, "site_id": site,
                "ppu_id": ppu_id, "operation": operation, "operations": operations,
                "job_binding_sha256": binding_sha, "state": "ISSUED",
                "run_id": None, "batch_id": None, "issued_at": _now(), "updated_at": _now()}
            try:
                self._persist_locked()
            except BaseException:
                self._plans.pop(plan_id, None)
                self._starts.pop(plan_id, None)
                raise
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
            # Admission is journalled together with the run, before anything
            # is spawned and before the answer (which may be lost) is sent.
            record = self._starts.setdefault(plan.plan_id, {
                "start_id": plan.plan_id, "kind": "run", "ppu_alias": alias,
                "site_id": plan.site, "ppu_id": plan.binding.get("ppu_id"),
                "operation": plan.operation, "operations": plan.operations,
                "job_binding_sha256": plan.binding_sha256, "batch_id": None,
                "issued_at": _now()})
            record.update(state="CONSUMED", run_id=run.run_id, updated_at=_now())
            try:
                self._persist_locked()
            except BaseException:
                # Not journalled: nothing is spawned and no run is kept. The
                # start record stays CONSUMED in memory (reconciles UNKNOWN).
                del self._runs[run.run_id]
                raise
        self.spawn(lambda: self._execute(run, plan))
        return {"ok": True, "run": run.as_dict()}

    # ------------------------------------------------ start outcome reconciliation
    def issue_batch_start(self, alias: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """Issue the start_id one Batch start must carry. Submits nothing."""
        if not isinstance(body, Mapping) or dict(body) != {"kind": "batch"}:
            raise ProgrammingError(400, "invalid_request", "a start ID is issued for kind=batch only")
        self._require_commissioned(alias)
        with self._lock:
            now = self.monotonic()
            for key in [k for k, (_a, at) in self._pending_batch_starts.items()
                        if now - at > PLAN_TTL_S]:
                del self._pending_batch_starts[key]
            while len(self._pending_batch_starts) >= MAX_PENDING_BATCH_STARTS:
                del self._pending_batch_starts[min(
                    self._pending_batch_starts, key=lambda k: self._pending_batch_starts[k][1])]
            start_id = secrets.token_hex(16)
            self._pending_batch_starts[start_id] = (alias, now)
            self._starts[start_id] = {
                "start_id": start_id, "kind": "batch", "ppu_alias": alias, "site_id": None,
                "targets": None,
                "ppu_id": None, "operation": PROGRAMMING, "operations": None,
                "job_binding_sha256": None, "state": "ISSUED",
                "run_id": None, "batch_id": None, "issued_at": _now(), "updated_at": _now()}
            try:
                self._persist_locked()
            except BaseException:
                self._pending_batch_starts.pop(start_id, None)
                self._starts.pop(start_id, None)
                raise
            return {"ok": True, "start": {"start_id": start_id, "kind": "batch",
                                          "ppu_alias": alias, "expires_in_s": PLAN_TTL_S}}

    def _batch_start_startable(self, alias: str, start_id: object) -> bool:
        pending = self._pending_batch_starts.get(start_id) if type(start_id) is str else None
        return (pending is not None and pending[0] == alias
                and self.monotonic() - pending[1] <= PLAN_TTL_S)

    def require_batch_start(self, alias: str, start_id: object) -> None:
        with self._lock:
            if not self._batch_start_startable(alias, start_id):
                raise ProgrammingError(
                    409, "programming_start_not_startable",
                    "this start ID was not issued for this PPU, was already used, was "
                    "voided or expired; nothing was started")

    def consume_batch_start(self, alias: str, start_id: str, batch_id: str,
                            targets: list[dict[str, Any]]) -> None:
        """One start ID admits one Batch; journalled before the Batch exists.

        The record carries the whole Target Set, because that is what was
        admitted. A Batch admitted with some Targets BLOCKED has still
        consumed this ID: those Targets need a NEW start, never a replay.
        """
        with self._lock:
            self.require_batch_start(alias, start_id)
            del self._pending_batch_starts[start_id]
            record = self._starts.setdefault(start_id, {
                "start_id": start_id, "kind": "batch", "ppu_alias": alias, "ppu_id": None,
                "operation": PROGRAMMING, "operations": None, "job_binding_sha256": None,
                "run_id": None, "issued_at": _now()})
            sites = [site for target in targets for site in target["site_ids"]]
            record.update(state="CONSUMED", batch_id=batch_id,
                          targets=[dict(target) for target in targets],
                          site_id=sites[0] if len(sites) == 1 else None,
                          updated_at=_now())
            self._persist_locked()

    def void_start(self, alias: str, start_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """Operator: a start that was never admitted may never be admitted.

        Removes only an unconsumed plan / Batch start ID. It cannot touch a
        run, a Batch, a Job or a PPU, and it refuses an admitted start.
        """
        if not isinstance(body, Mapping) or dict(body) != {"void": VOID_TOKEN}:
            raise ProgrammingError(400, "invalid_request", f"void requires void={VOID_TOKEN}")
        with self._lock:
            record = self._starts.get(start_id)
            if record is None or record["ppu_alias"] != alias:
                raise ProgrammingError(404, "programming_start_not_found",
                                       "no start with this ID is recorded for this PPU")
            admitted = any((run.plan or {}).get("plan_id") == start_id
                           for run in self._runs.values())
            if record["state"] != "ISSUED" or admitted:
                raise ProgrammingError(409, "programming_start_not_voidable",
                                       "only a start that was never admitted can be voided")
            self._plans.pop(start_id, None)
            self._pending_batch_starts.pop(start_id, None)
            record.update(state="VOIDED", updated_at=_now())
            self._persist_locked()
        return self.reconcile_start(alias, start_id)

    def reconcile_start(self, alias: str, start_id: str,
                        find_batch: Callable[[str], dict[str, Any] | None] | None = None,
                        ) -> dict[str, Any]:
        """What became of one Start. Read-only: journal and memory only.

        Never contacts a PPU, never submits, retries or acknowledges. A Site
        being idle or a plan being gone is not evidence here; ``NOT_ACCEPTED``
        needs a journalled issue record that was never consumed AND a start
        that can no longer be admitted. Anything unprovable is OUTCOME_UNKNOWN.
        """
        self._record(alias)
        batch = find_batch(start_id) if find_batch is not None else None
        with self._lock:
            record = self._starts.get(start_id)
            run = next((r for r in self._runs.values()
                        if (r.plan or {}).get("plan_id") == start_id), None)
            view: dict[str, Any] = {
                "schema": START_SCHEMA, "start_id": start_id, "ppu_alias": alias,
                "kind": None, "state": "OUTCOME_UNKNOWN", "reason": None, "outcome": None,
                "identity": None, "run": None, "batch": None, "acknowledged": None,
                "unknown_run_id": None, "expires_in_s": None,
                "read_only": True, "auto_retry": "DISABLED",
            }

            def unknown(reason: str) -> dict[str, Any]:
                view.update(state="OUTCOME_UNKNOWN", reason=reason)
                return {"ok": True, "reconciliation": view}

            if record is not None and record["ppu_alias"] != alias:
                return unknown("START_IDENTITY_MISMATCH")
            if run is not None:
                plan = run.plan or {}
                if run.alias != alias:
                    return unknown("START_IDENTITY_MISMATCH")
                if record is not None and (
                        record["kind"] != "run" or record["state"] != "CONSUMED"
                        or record.get("run_id") != run.run_id
                        or record.get("site_id") != run.site
                        or record.get("job_binding_sha256") != plan.get("job_binding_sha256")):
                    return unknown("JOURNAL_INCONSISTENT")
                binding = plan.get("job_binding") if isinstance(plan.get("job_binding"), dict) else {}
                view.update(kind="run", run=run.as_dict(), outcome=run.outcome, identity={
                    "ppu_alias": run.alias, "site_id": run.site, "ppu_id": binding.get("ppu_id"),
                    "operation": plan.get("operation"), "operations": plan.get("operations"),
                    "job_binding_sha256": plan.get("job_binding_sha256")})
                if run.outcome is None:
                    view.update(state="ACCEPTED_RUNNING", reason="RUN_IN_PROGRESS")
                elif run.outcome == "OUTCOME_UNKNOWN":
                    view.update(reason=run.reason or "RUN_OUTCOME_UNKNOWN",
                                acknowledged=run.acknowledged, unknown_run_id=run.run_id)
                elif run.outcome in ("PASS", "FAIL", "BLOCKED"):
                    view.update(state="TERMINAL_CONFIRMED", reason=run.reason)
                else:
                    return unknown("RUN_OUTCOME_UNRECOGNIZED")
                return {"ok": True, "reconciliation": view}
            if batch is not None:
                targets = batch.get("targets") or []
                aliases = [target["ppu_alias"] for target in targets]
                sites = [site for target in targets for site in target["site_ids"]]
                if alias not in aliases or batch.get("start_id") != start_id:
                    return unknown("START_IDENTITY_MISMATCH")
                if record is not None and (
                        record["kind"] != "batch" or record["state"] != "CONSUMED"
                        or record.get("batch_id") != batch.get("batch_id")
                        or record.get("targets") != targets):
                    return unknown("JOURNAL_INCONSISTENT")
                attempts = [attempt for unit in batch.get("units") or []
                            for attempt in unit.get("attempts") or []]
                view.update(kind="batch", batch=batch, outcome=batch.get("outcome"), identity={
                    "ppu_alias": alias, "site_id": sites[0] if len(sites) == 1 else None,
                    "targets": targets, "ppu_id": None,
                    "operation": PROGRAMMING, "operations": batch.get("operations"),
                    "job_binding_sha256": (attempts[-1].get("job_binding_sha256")
                                           if attempts else None)})
                outcome = batch.get("outcome")
                if outcome is None:
                    view.update(state="ACCEPTED_RUNNING", reason="BATCH_IN_PROGRESS")
                elif outcome == "OUTCOME_UNKNOWN":
                    current = batch.get("current_run")
                    view.update(reason=batch.get("reason") or "BATCH_OUTCOME_UNKNOWN")
                    if isinstance(current, dict) and current.get("outcome") == "OUTCOME_UNKNOWN":
                        view.update(acknowledged=bool(current.get("acknowledged")),
                                    unknown_run_id=current.get("run_id"))
                elif outcome in ("PASS", "FAIL", "PARTIAL", "BLOCKED"):
                    view.update(state="TERMINAL_CONFIRMED", reason=batch.get("reason"))
                else:
                    return unknown("BATCH_OUTCOME_UNRECOGNIZED")
                return {"ok": True, "reconciliation": view}
            if record is None:
                return unknown("START_NOT_RECORDED")
            view.update(kind=record["kind"], identity={
                "ppu_alias": record["ppu_alias"], "site_id": record.get("site_id"),
                "targets": record.get("targets"),
                "ppu_id": record.get("ppu_id"), "operation": record.get("operation"),
                "operations": record.get("operations"),
                "job_binding_sha256": record.get("job_binding_sha256")})
            if record["state"] == "VOIDED":
                view.update(state="NOT_ACCEPTED", reason="START_VOIDED_BEFORE_ADMISSION")
            elif record["state"] == "CONSUMED":
                # Admitted, but the run / Batch record is gone: never "not run".
                return unknown("ADMITTED_RECORD_MISSING")
            else:
                now = self.monotonic()
                plan_held = self._plans.get(start_id)
                left = None
                if record["kind"] == "run" and plan_held is not None and plan_held.alias == alias:
                    left = PLAN_TTL_S - (now - plan_held.created_monotonic)
                elif record["kind"] == "batch" and self._batch_start_startable(alias, start_id):
                    left = PLAN_TTL_S - (now - self._pending_batch_starts[start_id][1])
                if left is not None and left >= 0:
                    # A delayed Start request could still be admitted.
                    view.update(state="ACCEPTANCE_PENDING", reason="START_STILL_ADMISSIBLE",
                                expires_in_s=int(left))
                else:
                    view.update(state="NOT_ACCEPTED",
                                reason="START_NEVER_ADMITTED_AND_NO_LONGER_ADMISSIBLE")
            return {"ok": True, "reconciliation": view}

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
            self._verify(run, plan, job, client)
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
            "site_id": run.site, "timeout_s": 180.0,
            "target": plan.route.icpn, "provider": plan.route.provider_id,
            "profile": plan.route.profile_id, "job_binding": plan.binding,
            # A programming Job is addressed by its list, never by one operation.
            **({"operation": plan.operation} if plan.operations is None
               else {"operations": plan.operations}),
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

    # --------------------------------------------------------------- read output
    def _read_output_path(self, run_id: str) -> Path | None:
        if self.journal_path is None:
            return None
        return self.journal_path.with_name("programming-read-outputs") / f"{run_id}.bin"

    def _store_read_output(self, run: _Run, data: bytes) -> None:
        self._read_outputs[run.run_id] = data
        while len(self._read_outputs) > MAX_READ_OUTPUTS_RETAINED:
            del self._read_outputs[next(iter(self._read_outputs))]
        path = self._read_output_path(run.run_id)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, 0o600)
            os.replace(name, path)
        except BaseException:
            Path(name).unlink(missing_ok=True)
            raise
        kept = sorted(path.parent.glob("*.bin"), key=lambda item: item.stat().st_mtime)
        for stale in kept[:-MAX_READ_OUTPUTS_RETAINED]:
            stale.unlink(missing_ok=True)

    def _fetch_read_output(self, client: Any, job: Mapping[str, Any], *, length: int,
                           sha256: object) -> tuple[bytes | None, str | None]:
        """Fetch the Job's one output file through the PPU Gateway and prove it.

        Reading the file is repeatable and changes nothing on the PPU; any
        doubt about its bytes is a FAIL of the read, never a guess.
        """
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        files = result.get("output_files")
        if not (isinstance(files, list) and len(files) == 1 and type(files[0]) is str):
            return None, "READ_OUTPUT_MISSING"
        name = files[0].rsplit("/", 1)[-1]
        try:
            status, _headers, body = client.relay(
                "GET", f"/api/jobs/{quote(str(job.get('job_id')), safe='')}/files/"
                       f"{quote(name, safe='')}",
                headers={"Accept": "application/octet-stream"}, body=None,
                timeout_s=self.request_timeout_s, max_response_bytes=READ_OUTPUT_MAX_BYTES)
        except Exception:  # noqa: BLE001 - a read-only fetch; the Job itself is over
            return None, "READ_OUTPUT_FETCH_FAILED"
        if status != 200:
            return None, f"READ_OUTPUT_HTTP_{status}"
        if len(body) != length or bundle_v3.sha256_hex(body) != sha256:
            return None, "READ_OUTPUT_INTEGRITY_MISMATCH"
        return bytes(body), None

    def read_output(self, alias: str, run_id: str) -> tuple[bytes, dict[str, Any]]:
        """The verified bytes of a PASS read run, re-hashed before every download."""
        with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.alias != alias:
                raise ProgrammingError(404, "programming_run_not_found",
                                       "programming run was not found")
            receipt = run.receipt if isinstance(run.receipt, dict) else {}
            output = receipt.get("read_output")
            if run.outcome != "PASS" or not isinstance(output, dict):
                raise ProgrammingError(409, "read_output_unavailable",
                                       "only a PASS Read Memory run has a downloadable output")
            data = self._read_outputs.get(run_id)
        if data is None:
            path = self._read_output_path(run_id)
            try:
                data = path.read_bytes() if path is not None else None
            except OSError:
                data = None
        if (data is None or len(data) != output.get("bytes")
                or bundle_v3.sha256_hex(data) != output.get("sha256")):
            raise ProgrammingError(410, "read_output_unavailable",
                                   "the Read Memory output is no longer retained; read again")
        return data, dict(output)

    def _verify(self, run: _Run, plan: _Plan, job: dict[str, Any], client: Any = None) -> None:
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        details = result.get("details") if isinstance(result.get("details"), dict) else {}
        # The Job kind's own evidence block: flash_cycle / programming / read.
        evidence = details.get(plan.operation) if isinstance(details.get(plan.operation), dict) else {}
        flash = evidence if plan.operation == "flash_cycle" else {}
        steps = evidence.get("steps") if isinstance(evidence.get("steps"), dict) else {}
        echo = job.get("job_binding") if isinstance(job.get("job_binding"), dict) else {}
        binding = plan.binding
        expected_sha = None if plan.image is None else bundle_v3.sha256_hex(plan.image)
        expected_size = None if plan.image is None else len(plan.image)
        # The Job Binding range is the write window; flash_base is only the
        # bank start. The PPU reports the range it actually executed.
        unit = plan.route.flash_profile["erase_granularity"]
        job_range = binding["range"]
        address, length = job_range["address"], job_range["length"]
        erase_length = -(-length // unit) * unit
        operations = plan.operations
        expected_range: dict[str, Any] | None = None
        observed_range: dict[str, Any] | None = None
        if plan.operation == "flash_cycle":
            expected_range = {
                "load_address": address, "erase_address": address,
                "erase_length": erase_length,
                "write_address": address, "verify_address": address,
                "readback_address": address}
            observed_range = {key: flash.get(key) for key in FLASH_RANGE_FIELDS}

        def step(name: str) -> dict[str, Any]:
            return steps.get(name) if isinstance(steps.get(name), dict) else {}

        # Expected (Manager plan) / Observed (PPU) per listed step.
        expected_steps: dict[str, Any] | None = None
        observed_steps: dict[str, Any] | None = None
        if operations is not None:
            expected_steps, observed_steps = {}, {}
            if "erase" in operations:
                expected_steps["erase"] = {"erase_address": address, "erase_length": erase_length}
                if operations == ["erase"]:
                    expected_steps["erase"].update(blank_verified=True, bytes_verified=length)
                observed_steps["erase"] = {k: step("erase").get(k) for k in expected_steps["erase"]}
            if "program" in operations:
                expected_steps["program"] = {"write_address": address, "bytes_written": length,
                                             "image_sha256": expected_sha}
                observed_steps["program"] = {k: step("program").get(k)
                                             for k in expected_steps["program"]}
            if "verify" in operations:
                expected_steps["verify"] = {"verify_address": address, "bytes_verified": length,
                                            "readback_sha256": expected_sha}
                observed_steps["verify"] = {k: step("verify").get(k)
                                            for k in expected_steps["verify"]}
        read_output: dict[str, Any] | None = None
        read_error: str | None = None
        read_bytes: bytes | None = None
        read_range_ok = True
        if plan.operation == "read":
            read_range_ok = (evidence.get("read_address") == address
                             and evidence.get("read_length") == length
                             and evidence.get("bytes_read") == length
                             and type(evidence.get("sha256")) is str)
            if (read_range_ok and evidence.get("safe_off") is True
                    and evidence.get("result") == "PASS" and job.get("state") == "success"):
                read_bytes, read_error = self._fetch_read_output(
                    client, job, length=length, sha256=evidence.get("sha256"))
            else:
                read_error = "READ_OUTPUT_NOT_FETCHED"
            read_output = {"address": address, "bytes": length,
                           "sha256": evidence.get("sha256"),
                           "filename": f"read-{plan.route.icpn}-0x{address:08x}-{length}.bin",
                           "available": read_bytes is not None}
        if plan.operation == "flash_cycle":
            readback_sha, bytes_verified = flash.get("readback_sha256"), flash.get("bytes_verified")
        elif operations is not None and "verify" in operations:
            readback_sha = step("verify").get("readback_sha256")
            bytes_verified = step("verify").get("bytes_verified")
        else:
            readback_sha = bytes_verified = None
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "job_id": job.get("job_id"), "job_state": job.get("state"),
            "site_id": job.get("site_id"), "operation": job.get("operation"),
            "operations": operations,
            "observed_operations": (evidence.get("operations") if operations is not None
                                    else None),
            "target": plan.route.icpn, "ppu_id": binding["ppu_id"],
            "expected_image_sha256": expected_sha, "expected_image_size": expected_size,
            "observed_image_sha256": result.get("image_sha256"),
            "observed_image_size": result.get("image_size"),
            "readback_sha256": readback_sha,
            "bytes_verified": bytes_verified,
            "expected_flash_range": expected_range, "observed_flash_range": observed_range,
            "expected_steps": expected_steps, "observed_steps": observed_steps,
            "range": dict(job_range), "read_output": read_output,
            "expected_resource_set_sha256": plan.resource_set_sha256,
            "observed_resource_set_sha256": echo.get("resource_set_sha256"),
            "expected_job_binding_sha256": plan.binding_sha256,
            "observed_job_binding_sha256": echo.get("job_binding_sha256"),
            "expected_image_asset_sha256": binding["image_asset_sha256"],
            "observed_image_asset_sha256": echo.get("image_asset_sha256"),
            "active_asset_set_sha256": echo.get("asset_set_sha256"),
            "active_generation": echo.get("generation"),
            "resource_reuse": not plan.payload["activation_required"],
            "safe_off": evidence.get("safe_off"), "flash_result": evidence.get("result"),
            "attempts": result.get("attempts"), "error": result.get("error"),
            "elapsed_ms": result.get("elapsed_ms"),
        }
        # An erase-only / read Job carries no Image: the PPU reports none.
        image_ok = (result.get("image_sha256") == expected_sha
                    and (result.get("image_size") == expected_size
                         if plan.image is not None else not result.get("image_size")))
        # SAFE_OFF first so an unsafe end state is always the reported reason.
        checks = [
            (evidence.get("safe_off") is True, "SAFE_OFF_NOT_VERIFIED"),
            (plan.operation in RECEIPT_OPERATIONS, "OPERATION_RECEIPT_UNSUPPORTED"),
            (job.get("state") == "success" and result.get("state") == "success", "JOB_NOT_SUCCESS"),
            (job.get("site_id") == run.site and job.get("operation") == plan.operation,
             "JOB_IDENTITY_MISMATCH"),
            (echo.get("job_binding_sha256") == plan.binding_sha256
             and echo.get("resource_set_sha256") == plan.resource_set_sha256
             and echo.get("image_asset_sha256") == binding["image_asset_sha256"]
             and echo.get("operation") == plan.operation
             and echo.get("operations") == operations
             and echo.get("range") == job_range
             and echo.get("site_id") == run.site
             and echo.get("ppu_id") == binding["ppu_id"], "JOB_BINDING_NOT_CONFIRMED"),
            (image_ok, "IMAGE_IDENTITY_MISMATCH"),
            (result.get("attempts") == 1, "JOB_ATTEMPTS_NOT_ONE"),
        ]
        if plan.operation == "flash_cycle":
            checks += [
                (flash.get("result") == "PASS", "FLASH_CYCLE_NOT_PASS"),
                (flash.get("readback_sha256") == expected_sha, "READBACK_SHA256_MISMATCH"),
                (flash.get("bytes_verified") == expected_size, "VERIFIED_BYTES_MISMATCH"),
                (observed_range == expected_range, "FLASH_RANGE_MISMATCH"),
            ]
        elif operations is not None:
            checks += [
                (evidence.get("result") == "PASS", "PROGRAMMING_NOT_PASS"),
                # Exactly the planned list ran: nothing skipped, nothing added.
                (evidence.get("operations") == operations and set(steps) == set(operations),
                 "OPERATIONS_MISMATCH"),
                *[(observed_steps[name] == expected_steps[name],
                   f"{name.upper()}_EVIDENCE_MISMATCH") for name in operations],
            ]
        else:
            checks += [
                (evidence.get("result") == "PASS", "READ_NOT_PASS"),
                (read_range_ok, "READ_RANGE_MISMATCH"),
                (read_error is None, read_error or "READ_OUTPUT_MISSING"),
            ]
        failed = [reason for ok, reason in checks if not ok]
        outcome = "PASS" if not failed else "FAIL"
        if outcome == "PASS" and read_bytes is not None:
            try:
                self._store_read_output(run, read_bytes)
            except OSError:
                outcome, failed = "FAIL", ["READ_OUTPUT_STORE_FAILED"]
                receipt["read_output"]["available"] = False
        elif read_output is not None:
            read_output["available"] = False
        if plan.operation == "read":
            self._step(run, "FETCH_READ_OUTPUT",
                       "PASS" if read_output and read_output["available"] else "FAIL",
                       bytes=length, sha256=evidence.get("sha256"))
        self._step(run, "VERIFY_RECEIPT", outcome, failed_checks=failed)
        self._update(run, state="finished", outcome=outcome,
                     reason=None if not failed else failed[0], receipt=receipt)
