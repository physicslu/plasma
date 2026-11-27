from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field, replace
from functools import partial
from typing import Any

from plasma_core.config import PlasmaConfig, SiteConfig
from plasma_core.enums import JobState, Operation, SiteState
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.job_logging import OutputManager, ServerEventLogger, atomic_write_json
from plasma_core.models import JobRequest, JobResult, iso_now
from plasma_core.protocol import PROTOCOL_VERSION
from plasma_opf.site_safety import site_safety_class
from plasma_interfaces.base import BaseInterface
from plasma_interfaces.fpga import FPGAInterface
from plasma_interfaces.mock import MockActivityTracker, MockInterface
from plasma_interfaces.openocd import OpenOCDInterface
from plasma_interfaces.package_provider import PackageProviderInterface, TrustedProviderAction
from plasma_opf import bundle_v3

from .execution_router import RoutedProgrammingHandler, SiteExecutionRouter
from .job_manager import JobRegistry, JobRuntime
from .runtime_control import RuntimeQuiesceGate
from .site_worker import SiteWorker
from .time_sync import ChronyTimeSync

InterfaceFactory = Callable[[SiteConfig], BaseInterface]
# OFE-1B Job Image source (Gateway-validated, PPU re-verified at admission).
JOB_BINDING_KEYS = frozenset({"job_binding", "job_image_asset"})


def _m0_timing(event: str, **fields: Any) -> None:
    """Optional PPU-side diagnostic, never a safety or Job decision."""
    if os.environ.get("PLASMA_M0_TIMING") != "1":
        return
    try:
        sys.stderr.write("PLASMA_M0 " + json.dumps(
            {"event": event, "pid": os.getpid(),
             "thread_id": threading.get_ident(), "monotonic_ns": time.monotonic_ns(),
             **fields},
            sort_keys=True, separators=(",", ":"),
        ) + "\n")
    except (OSError, TypeError, ValueError):
        pass


@dataclass(slots=True)
class PPUExecutionLease:
    """Active execution ownership for one physical PPU.

    A logical owner may run multiple Site Jobs concurrently. A different owner
    is rejected until every Job currently owned by the lease is terminal.
    """

    owner_kind: str
    owner_id: str
    job_ids: set[str] = field(default_factory=set)

    def snapshot(self) -> dict[str, Any]:
        return {
            "busy": True,
            "owner_kind": self.owner_kind,
            "owner_id": self.owner_id,
            "active_job_count": len(self.job_ids),
            # The local Site Worker (C-3) admits a Runtime Site Job session
            # only for a Job that currently holds this lease.
            "job_ids": sorted(self.job_ids),
        }


RESERVATION_FILE = "ppu-resource-reservation.json"
RESERVATION_TTL_S = 90
#: U8: a Batch Reservation pins the loaded-image identity the root Site Worker
#: reports from the Root journal (status, image, session, boot and image digest
#: fields); the Runtime user cannot read the journal. Only the journal file's
#: own digest is left out: it is not part of the loaded image's identity.
FPGA_IDENTITY_VOLATILE = frozenset({"journal_sha256"})
class SiteManager:
    """Own the Programming Sites local to exactly one physical PPU."""

    def __init__(
        self,
        config: PlasmaConfig,
        interface_factory: InterfaceFactory | None = None,
        mock_tracker: MockActivityTracker | None = None,
        active_asset_set_reader: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.output = OutputManager(config.server.output_root)
        self.server_log = ServerEventLogger(config.server.log_root)
        self.registry = JobRegistry()
        self._active_asset_set_reader = active_asset_set_reader
        # Wired by the trusted PPU PackageActionRuntime, never from a Job or ZIP.
        # OFE-1B: PPU-derived Resource identity of the Active Set (same wiring rule).
        self._active_resource_resolver: Callable[[], dict[str, Any]] | None = None
        self._semaphore = asyncio.Semaphore(config.server.max_concurrent_jobs)
        self._site_configs = {site.id: site for site in config.sites}
        self.interfaces: dict[int, BaseInterface] = {}
        self.provider_interfaces: dict[int, PackageProviderInterface] = {}
        self.execution_routers: dict[int, SiteExecutionRouter] = {}
        self.workers: dict[int, SiteWorker] = {}
        self._execution_lock = threading.RLock()
        self._execution_lease: PPUExecutionLease | None = None
        self._runtime_epoch = uuid.uuid4().hex
        # Batch Resource Reservation: one record, guarded by _execution_lock,
        # persisted so a Runtime restart cannot forget an unproven Batch.
        self._reservation_path = config.server.output_root / RESERVATION_FILE
        self._reservation: dict[str, Any] | None = self._load_reservation()
        self._delegated_package_jobs: set[str] = set()
        self._runtime_quiesce = RuntimeQuiesceGate()
        self._time_sync = ChronyTimeSync()
        # Production Stage C wiring supplies the root Site Worker status.
        self._site_worker_status_reader: Callable[[], dict[str, Any]] | None = None
        self._started = False

        for site in config.sites:
            if not site.enabled:
                continue
            interface = (
                interface_factory(site)
                if interface_factory
                else self._default_interface(site, mock_tracker)
            )
            self.interfaces[site.id] = interface
            package_interface = None
            if site.interface != "mock":
                package_interface = PackageProviderInterface()
                self.provider_interfaces[site.id] = package_interface
            router = SiteExecutionRouter(site, interface, package_interface)
            self.execution_routers[site.id] = router
            handler = RoutedProgrammingHandler(interface, router)
            self.workers[site.id] = SiteWorker(
                site,
                handler,
                self.output,
                config.server.log_root,
                self._semaphore,
                config.server.max_queue_depth_per_site,
            )

    @staticmethod
    def _default_interface(
        site: SiteConfig,
        tracker: MockActivityTracker | None,
    ) -> BaseInterface:
        if site.interface == "mock":
            return MockInterface.from_options(site.mock, tracker=tracker)
        if site.interface == "openocd":
            return OpenOCDInterface(site.openocd)
        if site.interface == "fpga":
            return FPGAInterface(site.id, site.register_base)
        raise PlasmaError(ErrorCode.CONFIG_INVALID, f"unsupported interface: {site.interface}")

    async def start(self) -> list[str]:
        if self._started:
            return []
        recovered = self.output.recover_incomplete()
        for worker in self.workers.values():
            worker.start()
        self._started = True
        self.server_log.event(
            "INFO",
            "site_manager_started",
            ppu_id=self.config.ppu.id,
            facility_id=self.config.ppu.facility_id,
            enabled_sites=sorted(self.workers),
            recovered_jobs=recovered,
        )
        return recovered

    async def shutdown(self) -> None:
        if not self._started:
            return
        for runtime in self.registry.all():
            if not runtime.state.terminal:
                worker = self.workers.get(runtime.request.site_id)
                if worker:
                    worker.cancel(runtime)
        await asyncio.gather(*(worker.stop() for worker in self.workers.values()))
        self._started = False
        self.server_log.event(
            "INFO",
            "site_manager_stopped",
            ppu_id=self.config.ppu.id,
            facility_id=self.config.ppu.facility_id,
        )

    def _resolve_site(self, site_id: int) -> SiteWorker:
        config = self._site_configs.get(site_id)
        if config is None:
            raise PlasmaError(ErrorCode.SITE_INVALID, f"site does not exist: SITE{site_id}")
        if not config.enabled:
            raise PlasmaError(ErrorCode.SITE_DISABLED, f"site is disabled: SITE{site_id}")
        return self.workers[site_id]

    @staticmethod
    def _validate_execution_owner(value: Any, field_name: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 256:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                f"{field_name} must be a non-empty string of at most 256 characters",
            )
        return value

    @classmethod
    def _execution_owner(cls, request: JobRequest) -> tuple[str, str]:
        explicit_kind = request.metadata.get("execution_owner_kind")
        explicit_id = request.metadata.get("execution_owner_id")
        if (explicit_kind is None) != (explicit_id is None):
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "execution_owner_kind and execution_owner_id must be supplied together",
            )
        if explicit_kind is not None and explicit_id is not None:
            return (
                cls._validate_execution_owner(explicit_kind, "execution_owner_kind"),
                cls._validate_execution_owner(explicit_id, "execution_owner_id"),
            )

        batch_id = request.metadata.get("batch_id")
        if batch_id is not None:
            return "batch", cls._validate_execution_owner(batch_id, "batch_id")

        if request.client_id in {"plasma-web", "plasma-web-engineering"}:
            return "rest_job", cls._validate_execution_owner(request.job_id, "job_id")

        return "client", cls._validate_execution_owner(request.client_id, "client_id")

    def _reserve_execution_job(self, request: JobRequest) -> tuple[str, str]:
        owner_kind, owner_id = self._execution_owner(request)
        acquired = False
        conflict: PPUExecutionLease | None = None
        with self._execution_lock:
            reservation = self._reservation_now()
            token = request.metadata.get("resource_reservation_token")
            if token is not None and reservation is None:
                raise PlasmaError(ErrorCode.PPU_BUSY, "PPU Resource Reservation expired")
            if reservation is not None:
                if reservation["state"] != "ACTIVE":
                    raise self._reservation_busy("PPU Resource Reservation is "
                                                 + reservation["state"], reservation)
                if ((owner_kind, owner_id) != ("rest_client", reservation["owner_id"])
                        or token != reservation["token"]):
                    raise PlasmaError(ErrorCode.PPU_BUSY,
                                      "PPU Resource Reservation belongs to another execution")
                reservation["job_ids"].add(request.job_id)
            if self._runtime_quiesce.active():
                raise PlasmaError(
                    ErrorCode.PPU_BUSY,
                    "PPU is quiesced for controlled runtime activation",
                    recoverable=True,
                    context={"runtime_activation": self._runtime_quiesce.snapshot()},
                )
            lease = self._execution_lease
            if lease is not None and (lease.owner_kind, lease.owner_id) != (owner_kind, owner_id):
                conflict = PPUExecutionLease(
                    owner_kind=lease.owner_kind,
                    owner_id=lease.owner_id,
                    job_ids=set(lease.job_ids),
                )
            else:
                if lease is None:
                    lease = PPUExecutionLease(owner_kind=owner_kind, owner_id=owner_id)
                    self._execution_lease = lease
                    acquired = True
                lease.job_ids.add(request.job_id)

        if conflict is not None:
            self.server_log.event(
                "WARNING",
                "ppu_execution_lease_conflict",
                ppu_id=self.config.ppu.id,
                facility_id=self.config.ppu.facility_id,
                active_owner_kind=conflict.owner_kind,
                active_owner_id=conflict.owner_id,
                requested_owner_kind=owner_kind,
                requested_owner_id=owner_id,
                requested_job_id=request.job_id,
            )
            raise PlasmaError(
                ErrorCode.PPU_BUSY,
                "PPU is owned by another active execution",
                recoverable=True,
                context={
                    "ppu_id": self.config.ppu.id,
                    "facility_id": self.config.ppu.facility_id,
                    "active_owner_kind": conflict.owner_kind,
                    "active_owner_id": conflict.owner_id,
                    "requested_owner_kind": owner_kind,
                    "requested_owner_id": owner_id,
                },
            )

        if acquired:
            self.server_log.event(
                "INFO",
                "ppu_execution_lease_acquired",
                ppu_id=self.config.ppu.id,
                facility_id=self.config.ppu.facility_id,
                owner_kind=owner_kind,
                owner_id=owner_id,
            )
        return owner_kind, owner_id

    def acquire_runtime_quiesce(self, ttl_s: int) -> dict[str, Any]:
        with self._execution_lock:
            if self._execution_lease is not None or self._reservation_now() is not None:
                raise PlasmaError(
                    ErrorCode.PPU_BUSY,
                    "PPU execution is active; runtime activation cannot quiesce",
                    recoverable=True,
                    context={"execution": (self._execution_lease.snapshot()
                                             if self._execution_lease else None),
                             "resource_reservation": self.resource_reservation_snapshot()},
                )
            lease = self._runtime_quiesce.acquire(ttl_s)
            self.server_log.event(
                "INFO",
                "runtime_activation_quiesced",
                ppu_id=self.config.ppu.id,
                facility_id=self.config.ppu.facility_id,
                ttl_s=ttl_s,
            )
            return {
                **lease,
                "ppu_id": self.config.ppu.id,
                "facility_id": self.config.ppu.facility_id,
            }

    def acquire_asset_set_quiesce(self) -> dict[str, Any]:
        """Held Runtime authority used only via the private Unix control socket.

        The same _execution_lock serializes job reservations against the
        quiesce transition, including queued and cancelling jobs.
        """
        with self._execution_lock:
            if self._execution_lease is not None or self._reservation_now() is not None:
                raise PlasmaError(
                    ErrorCode.PPU_BUSY,
                    "PPU execution active; cannot hold Asset Set activation",
                    recoverable=True,
                    context={"execution": (self._execution_lease.snapshot()
                                             if self._execution_lease else None),
                             "resource_reservation": self.resource_reservation_snapshot()},
                )
            lease = self._runtime_quiesce.acquire_held()
            self.server_log.event(
                "INFO", "asset_set_runtime_quiesced",
                ppu_id=self.config.ppu.id,
                facility_id=self.config.ppu.facility_id,
            )
            return {
                **lease,
                "ppu_id": self.config.ppu.id,
                "facility_id": self.config.ppu.facility_id,
                "active_job_count": 0,
            }

    def release_runtime_quiesce(self, token: str) -> None:
        with self._execution_lock:
            self._runtime_quiesce.release(token)
            self.server_log.event(
                "INFO",
                "runtime_activation_quiesce_released",
                ppu_id=self.config.ppu.id,
                facility_id=self.config.ppu.facility_id,
            )

    def runtime_quiesce_snapshot(self) -> dict[str, Any]:
        with self._execution_lock:
            return {
                **self._runtime_quiesce.snapshot(),
                "ppu_id": self.config.ppu.id,
                "facility_id": self.config.ppu.facility_id,
            }

    # -- Batch Resource Reservation ------------------------------------
    # ACTIVE: the Batch owner holds the PPU between its Jobs (Job, B3 quiesce,
    #   Package Action and other owners are refused).
    # EXPIRED: TTL passed while a reserved Job is still active; the owner's
    #   claim has ended (no new Job, no Check), every exclusion stays.
    # RECOVERY_REQUIRED: SAFE_OFF of a reserved Job is not proven by this
    #   PPU's own Job results, the reserved identity changed, or the Runtime
    #   restarted with a record on disk. Persisted; cleared only by
    #   ``recover_resource_reservation`` on the local Runtime control socket.
    # Safe release (owner Release, or TTL with nothing active) requires that
    # proof for every reserved Job: TTL and an empty lease are never SAFE_OFF.

    def _load_reservation(self) -> dict[str, Any] | None:
        try:
            raw = json.loads(self._reservation_path.read_text(encoding="utf-8"))
            reason = raw.get("reason") if raw.get("state") == "RECOVERY_REQUIRED" else None
        except FileNotFoundError:
            return None
        except (OSError, ValueError, AttributeError):
            raw, reason = {}, "RESERVATION_STATE_UNREADABLE"
        record = self._recovery_record(raw if isinstance(raw, dict) else {},
                                       reason if type(reason) is str else "RUNTIME_RESTARTED")
        self._persist_reservation(record)
        return record

    def _recovery_record(self, base: dict[str, Any], reason: str,
                         unproven: list[str] | None = None) -> dict[str, Any]:
        keep = {key: base.get(key) for key in (
            "ppu_id", "owner_id", "asset_set_sha256", "generation", "resource_set_sha256")
            if base.get(key) is not None}
        reserved_epoch = base.get("reserved_epoch") or base.get("epoch")
        if type(reserved_epoch) is str:
            keep["reserved_epoch"] = reserved_epoch
        if unproven is None:
            prior = base.get("unproven_job_ids")
            unproven = [job for job in prior if type(job) is str] if isinstance(prior, list) else []
        return {**keep, "state": "RECOVERY_REQUIRED", "reason": reason[:80],
                "unproven_job_ids": sorted(unproven)[:64],
                "recovery_id": uuid.uuid4().hex, "job_ids": set()}

    def _persist_reservation(self, record: dict[str, Any] | None) -> None:
        """Durable PPU state; a failed write is logged, the memory state still blocks."""
        try:
            if record is None:
                self._reservation_path.unlink(missing_ok=True)
            else:
                atomic_write_json(self._reservation_path, {
                    key: (sorted(value) if isinstance(value, set) else value)
                    for key, value in record.items() if key not in ("deadline", "token")})
        except OSError as exc:
            self.server_log.event("ERROR", "ppu_resource_reservation_persist_failed",
                                  ppu_id=self.config.ppu.id, error=type(exc).__name__)
            if record is not None and record["state"] == "ACTIVE":
                raise PlasmaError(ErrorCode.PPU_BUSY,
                                  "PPU Resource Reservation could not be made durable") from None

    def _guard_reserved_fpga_identity(self, job_id: str, identity: Any) -> None:
        """U8: one loaded FPGA image for the whole Batch Reservation.

        The Reservation's first Job pins the identity the root Site Worker
        reports; every later Job of that Reservation must report the same one
        before any Site session. A change (e.g. a Root image load between two
        Jobs) isolates the PPU exactly like a changed Resource identity.
        A Job outside a Reservation is not affected.
        """
        observed = ({key: value for key, value in identity.items()
                     if key not in FPGA_IDENTITY_VOLATILE}
                    if isinstance(identity, dict) else None)
        with self._execution_lock:
            record = self._reservation_now()
            if record is None or record["state"] != "ACTIVE" or job_id not in record["job_ids"]:
                return
            pinned = record.get("fpga_identity")
            if pinned is None:
                if (not observed or type(observed.get("image_id")) is not str
                        or not all(type(v) is str and v for v in observed.values())):
                    raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                                      "RESERVED_FPGA_IDENTITY_UNVERIFIABLE")
                record["fpga_identity"] = observed
                self._persist_reservation(record)
                return
            if observed == pinned:
                return
            self._reservation = self._recovery_record(
                record, "RESERVED_FPGA_IDENTITY_CHANGED",
                sorted(job for job in record["job_ids"] if not self._job_safe_off_proven(job)))
            self._persist_reservation(self._reservation)
            reservation = self._reservation
        self.server_log.event("ERROR", "ppu_reserved_fpga_identity_changed",
                              ppu_id=self.config.ppu.id, job_id=job_id,
                              pinned_image_id=pinned.get("image_id"),
                              observed_image_id=(observed or {}).get("image_id"))
        raise self._reservation_busy("reserved FPGA identity changed", reservation)

    def _job_safe_off_proven(self, job_id: str) -> bool:
        """This PPU's own terminal Job result proves the Site is safe."""
        try:
            runtime = self.registry.get(job_id)
        except PlasmaError:
            return False
        if not runtime.state.terminal or runtime.result is None:
            return False
        if runtime.attempt == 0:
            return True  # no interface attempt: hardware never touched
        result = runtime.result
        evidence = [item for item in result.details.values() if isinstance(item, dict)]
        if any(item.get("safe_off") is True for item in evidence):
            return True
        context = result.error.context if result.error is not None else {}
        if not isinstance(context, dict) or context.get("outcome_unknown"):
            return False
        worker = context.get("site_worker_result")
        # Identity from this Job's own terminal result, never from the code text.
        operation = getattr(result.operation, "value", result.operation)
        return ((isinstance(worker, dict) and worker.get("safe_off") is True)
                or context.get("safe_off") is True
                or (result.job_id == job_id
                    and site_safety_class(context, job_id=job_id, site_id=result.site_id,
                                          operation=operation) is not None))

    def _reserved_jobs_active(self, record: dict[str, Any]) -> bool:
        lease = self._execution_lease
        return lease is not None and bool(record["job_ids"] & lease.job_ids)

    def _settle_reservation(self, record: dict[str, Any], cause: str) -> dict[str, Any] | None:
        """No reserved Job active: safe release only with SAFE_OFF proof for each.

        ``cause`` is RELEASE or RESERVATION_EXPIRED; the logged and recorded
        reason states whether the proof held.
        """
        unproven = sorted(job for job in record["job_ids"] if not self._job_safe_off_proven(job))
        reason = cause + ("_SAFE_OFF_NOT_PROVEN" if unproven else "_SAFE_OFF_PROVEN")
        if unproven:
            self._reservation = self._recovery_record(record, reason, unproven)
        else:
            self._reservation = None
        self._persist_reservation(self._reservation)
        self.server_log.event(
            "WARNING" if unproven else "INFO",
            "ppu_resource_reservation_recovery_required" if unproven
            else "ppu_resource_reservation_released",
            ppu_id=self.config.ppu.id, owner_id=record.get("owner_id"), reason=reason,
            unproven_job_count=len(unproven))
        return self._reservation

    def _reservation_now(self) -> dict[str, Any] | None:
        """Only called under _execution_lock; applies TTL without dropping safety."""
        record = self._reservation
        if record is None or record["state"] == "RECOVERY_REQUIRED":
            return record
        if record["state"] == "ACTIVE" and time.monotonic() >= record["deadline"]:
            record["state"] = "EXPIRED"
            self._persist_reservation(record)
        if record["state"] == "EXPIRED" and not self._reserved_jobs_active(record):
            return self._settle_reservation(record, "RESERVATION_EXPIRED")
        return record

    def _reservation_busy(self, message: str, record: dict[str, Any]) -> PlasmaError:
        return PlasmaError(ErrorCode.PPU_BUSY, message, recoverable=True,
                           context={"resource_reservation": self._reservation_view(record)})

    def _reservation_view(self, record: dict[str, Any] | None) -> dict[str, Any]:
        if record is None:
            return {"state": "NONE", "ppu_id": self.config.ppu.id, "epoch": self._runtime_epoch}
        view = {key: record[key] for key in (
            "state", "ppu_id", "owner_id", "epoch", "asset_set_sha256", "generation",
            "resource_set_sha256", "reason", "recovery_id", "reserved_epoch") if key in record}
        view["epoch"] = self._runtime_epoch
        if isinstance(record.get("fpga_identity"), dict):
            view["fpga_image_id"] = record["fpga_identity"].get("image_id")
        if record["state"] == "RECOVERY_REQUIRED":
            view["unproven_job_ids"] = list(record["unproven_job_ids"])
        elif record["state"] == "ACTIVE":
            view["ttl_remaining_s"] = max(0.0, record["deadline"] - time.monotonic())
        return view

    def resource_reservation(self, action: str, *, owner_id: str, token: str | None = None,
                             expected: dict[str, Any] | None = None) -> dict[str, Any]:
        """PPU authority shared with Job admission and B3 Runtime quiesce."""
        self._validate_execution_owner(owner_id, "owner_id")
        if type(action) is not str or action not in {"acquire", "check", "release"}:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "invalid reservation action")
        with self._execution_lock:
            current = self._reservation_now()
            if action == "acquire":
                if current is not None:
                    raise self._reservation_busy("PPU Resource Reservation is "
                                                 + current["state"], current)
                if self._runtime_quiesce.active():
                    raise PlasmaError(ErrorCode.PPU_BUSY, "PPU Resource Reservation unavailable")
                lease = self._execution_lease
                if lease is not None and (lease.owner_kind, lease.owner_id) != ("rest_client", owner_id):
                    raise PlasmaError(ErrorCode.PPU_BUSY, "PPU has another execution owner")
                if type(expected) is not dict or set(expected) != {
                    "ppu_id", "asset_set_sha256", "generation", "resource_set_sha256"}:
                    raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "reservation identity is invalid")
                if (type(expected["ppu_id"]) is not str or not expected["ppu_id"]
                        or type(expected["generation"]) is not int
                        or expected["generation"] < 0
                        or any(type(expected[key]) is not str or
                               re.fullmatch(r"[0-9a-f]{64}", expected[key]) is None
                               for key in ("asset_set_sha256", "resource_set_sha256"))):
                    raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "reservation identity is invalid")
                identity = self._resolve_active_resources()  # full content verification stays PPU-owned
                observed = {"ppu_id": self.config.ppu.id,
                            "asset_set_sha256": identity["asset_set_sha256"],
                            "generation": identity["generation"],
                            "resource_set_sha256": identity["resource_set_sha256"]}
                if observed != expected:
                    raise PlasmaError(ErrorCode.PPU_BUSY, "reservation Resource identity changed")
                current = {**observed, "state": "ACTIVE", "owner_id": owner_id,
                           "token": uuid.uuid4().hex, "epoch": self._runtime_epoch,
                           "deadline": time.monotonic() + RESERVATION_TTL_S, "job_ids": set()}
                self._persist_reservation(current)  # refuses unless durable
                self._reservation = current
            else:
                if (current is None or current["state"] != "ACTIVE"
                        or current["owner_id"] != owner_id
                        or type(token) is not str or token != current["token"]):
                    raise (self._reservation_busy("PPU Resource Reservation is "
                                                  + current["state"], current)
                           if current is not None and current["state"] != "ACTIVE" else
                           PlasmaError(ErrorCode.PPU_BUSY,
                                       "reservation expired or owner/token changed"))
                if action == "release":
                    lease = self._execution_lease
                    if lease is not None and lease.job_ids:
                        raise PlasmaError(ErrorCode.PPU_BUSY, "active Jobs prevent reservation release")
                    settled = self._settle_reservation(current, "RELEASE")
                    if settled is not None:
                        raise self._reservation_busy("SAFE_OFF not proven; recovery required",
                                                     settled)
                    return {"state": "RELEASED", "ppu_id": self.config.ppu.id,
                            "epoch": self._runtime_epoch}
                try:  # full PPU content verification on every Check
                    identity = self._resolve_active_resources()
                except PlasmaError:
                    identity = None
                if (identity is None
                        or identity["asset_set_sha256"] != current["asset_set_sha256"]
                        or identity["generation"] != current["generation"]
                        or identity["resource_set_sha256"] != current["resource_set_sha256"]):
                    # An unverifiable or changed identity under a Reservation
                    # is an anomaly: isolate, never silently re-open B3.
                    self._reservation = self._recovery_record(
                        current, "RESERVED_RESOURCE_IDENTITY_CHANGED" if identity
                        else "RESERVED_RESOURCE_IDENTITY_UNVERIFIABLE",
                        sorted(job for job in current["job_ids"]
                               if not self._job_safe_off_proven(job)))
                    self._persist_reservation(self._reservation)
                    raise self._reservation_busy("reserved Resource identity changed",
                                                 self._reservation)
                current["deadline"] = time.monotonic() + RESERVATION_TTL_S
            return {"state": "ACTIVE", "ppu_id": current["ppu_id"],
                    "owner_id": current["owner_id"], "token": current["token"],
                    "epoch": current["epoch"], "asset_set_sha256": current["asset_set_sha256"],
                    "generation": current["generation"],
                    "resource_set_sha256": current["resource_set_sha256"],
                    "ttl_s": RESERVATION_TTL_S}

    def recover_resource_reservation(self, recovery_id: str) -> dict[str, Any]:
        """Explicit local recovery (Runtime control socket only, never HTTP).

        The operator confirms the reserved Sites are physically safe; the PPU
        only checks that nothing is executing and that the recovery_id is the
        current one, so a stale or blind request cannot clear a newer record.
        """
        with self._execution_lock:
            record = self._reservation_now()
            if (record is None or record["state"] != "RECOVERY_REQUIRED"
                    or type(recovery_id) is not str or recovery_id != record["recovery_id"]):
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT,
                                  "no matching Resource Reservation recovery")
            if self._execution_lease is not None:
                raise PlasmaError(ErrorCode.PPU_BUSY, "PPU execution is active; recovery refused")
            self._reservation = None
            self._persist_reservation(None)
        self.server_log.event("WARNING", "ppu_resource_reservation_recovered",
                              ppu_id=self.config.ppu.id, recovery_id=recovery_id,
                              reason=record["reason"], owner_id=record.get("owner_id"))
        return self.resource_reservation_snapshot()

    def resource_reservation_snapshot(self) -> dict[str, Any]:
        with self._execution_lock:
            return self._reservation_view(self._reservation_now())

    def pre_start_time_sync(self, *, owner_id: str, token: str | None,
                            threshold_ms: int, budget_ms: int) -> dict[str, Any]:
        """Serialize a bounded clock correction against all PPU admissions.

        A Batch may use only its own Resource Reservation before its first
        Job. The same lock protects reservation, Job lease and B3 quiesce;
        holding it through chronyc closes the check-to-adjust race.
        """
        started = time.monotonic()
        self._validate_execution_owner(owner_id, "owner_id")
        if type(threshold_ms) is not int or not 1 <= threshold_ms <= 1000:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "invalid time sync threshold")
        if type(budget_ms) is not int or not 100 <= budget_ms <= 5000:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "invalid time sync budget")
        with self._execution_lock:
            reservation = self._reservation_now()
            busy = (self._runtime_quiesce.active() or self._execution_lease is not None
                    or any(not job.state.terminal for job in self.registry.all()))
            if reservation is not None:
                busy = busy or (reservation["state"] != "ACTIVE"
                                or reservation["owner_id"] != owner_id
                                or token != reservation["token"]
                                or bool(reservation["job_ids"]))
            elif token is not None:
                busy = True
            if not busy and (self._site_worker_status_reader is not None
                             or any(site.interface != "mock" for site in self._site_configs.values()
                                    if site.enabled)):
                # Root admission records and Site sessions are owned by the
                # separate privileged Worker, not inferred from an idle REST
                # queue. An unreadable Worker is an unverified owner.
                try:
                    worker = (self._site_worker_status_reader()
                              if self._site_worker_status_reader is not None else None)
                    busy = (not isinstance(worker, dict)
                            or not isinstance(worker.get("sessions"), list)
                            or bool(worker["sessions"])
                            or not isinstance(worker.get("sealed_sites"), list)
                            or bool(worker["sealed_sites"])
                            or not isinstance(worker.get("admission_record_sites"), list)
                            or bool(worker["admission_record_sites"])
                            or worker.get("not_ready") is not None)
                except Exception:  # noqa: BLE001 - unknown Root ownership is busy
                    busy = True
            if busy:
                return {"ppu_id": self.config.ppu.id, "status": "SKIPPED_BUSY",
                        "source": "chronyd", "service": "chrony",
                        "before_offset_ms": None, "after_offset_ms": None,
                        "uncertainty_ms": None, "adjustment_performed": False,
                        "warning_code": "PPU_BUSY_OR_ROOT_OWNERSHIP_UNVERIFIED",
                        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                        "observed_at_utc": iso_now()}
            result = self._time_sync.execute(ppu_id=self.config.ppu.id,
                                             threshold_ms=threshold_ms,
                                             budget_ms=budget_ms)
            self.server_log.event(
                "INFO" if result["status"] in {"SYNCED", "CORRECTED"} else "WARNING",
                "pre_start_time_sync", ppu_id=self.config.ppu.id,
                owner_id=owner_id, status=result["status"],
                warning_code=result["warning_code"],
                adjustment_performed=result["adjustment_performed"])
            return result

    def _release_execution_job(self, job_id: str) -> None:
        released: tuple[str, str] | None = None
        with self._execution_lock:
            lease = self._execution_lease
            if lease is None or job_id not in lease.job_ids:
                return
            lease.job_ids.discard(job_id)
            self._delegated_package_jobs.discard(job_id)
            if not lease.job_ids:
                released = (lease.owner_kind, lease.owner_id)
                self._execution_lease = None
        if released is not None:
            self.server_log.event(
                "INFO",
                "ppu_execution_lease_released",
                ppu_id=self.config.ppu.id,
                facility_id=self.config.ppu.facility_id,
                owner_kind=released[0],
                owner_id=released[1],
            )

    @contextmanager
    def package_action_scope(self, job_id: str) -> Iterator[dict[str, Any]]:
        """PPU-exclusive Job lease for ONE authorized Package Action.

        The ``execution_scope`` adapter for ``ppu_asset_execution.dispatch``.
        It uses the same execution lock, lease and Runtime quiesce as Site
        programming Jobs: it raises PPU_BUSY instead of yielding while any
        Job or quiesce is active, and while held every other Job, a second
        Package Action and Runtime/Asset Set quiesce are refused. Yields the
        authorized ``job_id`` and all enabled one-based Site IDs; it never
        grants hardware access by itself.
        """
        if not isinstance(job_id, str) or re.fullmatch(r"[0-9a-f]{32}", job_id) is None:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "package action job_id must be 32 lowercase hex")
        if not self._started:
            raise PlasmaError(ErrorCode.INTERNAL_ERROR, "site manager is not started")
        with self._execution_lock:
            if self._runtime_quiesce.active():
                raise PlasmaError(
                    ErrorCode.PPU_BUSY, "PPU is quiesced for controlled runtime activation",
                    recoverable=True, context={"runtime_activation": self._runtime_quiesce.snapshot()},
                )
            reservation = self._reservation_now()
            if reservation is not None:
                raise self._reservation_busy("PPU Resource Reservation is "
                                             + reservation["state"], reservation)
            if self._execution_lease is not None:
                raise PlasmaError(
                    ErrorCode.PPU_BUSY, "PPU execution is active; Package Action cannot start",
                    recoverable=True, context={"execution": self._execution_lease.snapshot()},
                )
            self._execution_lease = PPUExecutionLease(
                owner_kind="package_action", owner_id=job_id, job_ids={job_id},
            )
        self.server_log.event(
            "INFO", "ppu_execution_lease_acquired",
            ppu_id=self.config.ppu.id, facility_id=self.config.ppu.facility_id,
            owner_kind="package_action", owner_id=job_id,
        )
        try:
            yield {"job_id": job_id, "owner_kind": "package_action",
                   "site_ids": sorted(self.workers)}
        finally:
            self._release_execution_job(job_id)

    @contextmanager
    def programming_package_scope(self, job_id: str, site_id: int) -> Iterator[dict[str, Any]]:
        """Borrow the existing Programming Job lease for a signed Package.

        This is not a second lease or owner: the C-3 Worker sees this
        short-lived delegation only while the exact parent Job remains active.
        """
        with self._execution_lock:
            lease = self._execution_lease
            job = self.registry.get(job_id)
            if (lease is None or lease.owner_kind == "package_action"
                    or job_id not in lease.job_ids
                    or job_id in self._delegated_package_jobs
                    or site_id not in self.workers
                    or job.request.site_id != site_id
                    or not isinstance(job.trusted_provider, TrustedProviderAction)
                    or job.state is not JobState.RUNNING):
                raise PlasmaError(ErrorCode.PPU_BUSY, "PROGRAMMING_PACKAGE_LEASE_DENIED")
            self._delegated_package_jobs.add(job_id)
        try:
            yield {"job_id": job_id, "site_ids": [site_id]}
        finally:
            with self._execution_lock:
                self._delegated_package_jobs.discard(job_id)

    def execution_lease_snapshot(self) -> dict[str, Any]:
        with self._execution_lock:
            lease = self._execution_lease
            if lease is None:
                return {
                    "busy": False,
                    "owner_kind": None,
                    "owner_id": None,
                    "active_job_count": 0,
                }
            return {**lease.snapshot(),
                    "delegated_package_job_ids": sorted(self._delegated_package_jobs)}

    def _resolve_active_resources(self) -> dict[str, Any]:
        """PPU-derived Resource identity; any resolver failure fails closed."""
        if self._active_resource_resolver is None:
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                              "JOB_RESOURCE_IDENTITY_NOT_WIRED")
        try:
            identity = self._active_resource_resolver()
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                              "JOB_RESOURCE_IDENTITY_UNAVAILABLE:" + str(exc)[:160]) from exc
        try:
            digest = bundle_v3.resource_set_sha256(identity["resource_set"])
        except (bundle_v3.BundleBuildError, KeyError, TypeError) as exc:
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                              "JOB_RESOURCE_IDENTITY_INVALID") from exc
        if (identity.get("state") != "VERIFIED"
                or identity.get("resource_set_sha256") != digest
                or type(identity.get("asset_set_sha256")) is not str
                or type(identity.get("generation")) is not int):
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                              "JOB_RESOURCE_IDENTITY_INVALID")
        return identity

    def _admit_job_binding(self, request: JobRequest, pinned: Any) -> dict[str, Any]:
        """OFE-1B Job Image admission inside the existing PPU execution lease.

        The PPU re-derives the Resource Set from its own pinned Active Set and
        accepts only the exact Binding of (Resource, Operation, range, Image,
        this PPU, Site, ICPN, Profile). The Manager's Resource claim is only
        compared, never trusted. Execution authority stays with the route.
        """
        meta = request.metadata
        binding, asset = meta.get("job_binding"), meta.get("job_image_asset")
        operations = None
        if request.operation is Operation.PROGRAMMING:
            # The ordered list is part of the Binding identity; it is
            # re-validated here and never taken from anywhere else.
            try:
                operations = bundle_v3.normalize_operations(
                    binding.get("operations") if type(binding) is dict else None)
            except bundle_v3.BundleBuildError as exc:
                raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                                  f"JOB_BINDING_DENIED:{exc}") from exc
            image_operation = bundle_v3.operations_take_image(operations)
        else:
            image_operation = request.operation.value in bundle_v3.IMAGE_OPERATIONS
        if (request.max_retries != 0 or request.image_ref is not None
                or type(binding) is not dict
                or type(meta.get("provider")) is not str
                or type(meta.get("profile")) is not str
                or (image_operation and (type(asset) is not dict or not request.image))
                or (not image_operation and (asset is not None or request.image))):
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "JOB_BINDING_NOT_QUALIFIED")
        if type(pinned) is not dict or pinned.get("state") != "ACTIVE":
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "JOB_RESOURCE_NOT_ACTIVE")
        identity = self._resolve_active_resources()
        if (identity["asset_set_sha256"] != pinned.get("asset_set_sha256")
                or identity["generation"] != pinned.get("generation")):
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                              "JOB_RESOURCE_ACTIVE_SET_CHANGED")
        resource = identity["resource_set"]
        kinds = {p["kind"]: p["id"] for p in resource["packages"]}
        if (meta["provider"] != kinds.get("platform-provider")
                or meta["profile"] != kinds.get("programming-profile")):
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "JOB_RESOURCE_PACKAGE_MISMATCH")
        if request.target != resource["constraints"]["icpn"]:
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "JOB_TARGET_MISMATCH")
        job_range = binding.get("range") if type(binding.get("range")) is dict else {}
        address = None if image_operation else job_range.get("address")
        length = None if image_operation else job_range.get("length")
        try:
            image = (bundle_v3.verify_image_asset(asset, request.image, resource)
                     if image_operation else None)
            binding_sha256 = bundle_v3.verify_job_binding(
                binding, resource, image, ppu_id=self.config.ppu.id,
                site_id=request.site_id, operation=request.operation.value,
                address=address, length=length, operations=operations)
        except bundle_v3.BundleBuildError as exc:
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                              f"JOB_BINDING_DENIED:{exc}") from exc
        if request.operation is Operation.READ:
            sections = request.map_data.get("sections") if isinstance(request.map_data, dict) else None
            if (not isinstance(sections, list) or len(sections) != 1
                    or not isinstance(sections[0], dict)
                    or sections[0].get("address") != binding["range"]["address"]
                    or sections[0].get("length") != binding["range"]["length"]):
                raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "JOB_RANGE_MISMATCH")
        return {
            "schema": bundle_v3.JOB_BINDING_SCHEMA,
            "job_binding_sha256": binding_sha256,
            "resource_set_sha256": identity["resource_set_sha256"],
            "image_asset_sha256": binding["image_asset_sha256"],
            "operation": binding["operation"], "range": dict(binding["range"]),
            **({} if operations is None else {"operations": list(operations)}),
            "ppu_id": binding["ppu_id"], "site_id": binding["site_id"],
            "icpn": binding["icpn"], "profile": binding["profile"],
            "asset_set_sha256": identity["asset_set_sha256"],
            "generation": identity["generation"],
        }

    def active_resources_snapshot(self) -> dict[str, Any]:
        """Read-only PPU-derived Resource identity for the Manager reuse decision."""
        if self._active_resource_resolver is None:
            return {"state": "UNSUPPORTED"}
        try:
            identity = self._resolve_active_resources()
        except PlasmaError as exc:
            return {"state": "UNAVAILABLE", "reason": exc.message[:200]}
        resource = identity["resource_set"]
        kinds = {p["kind"]: p["id"] for p in resource["packages"]}
        return {
            "state": "VERIFIED",
            "asset_set_sha256": identity["asset_set_sha256"],
            "generation": identity["generation"],
            "resource_set_sha256": identity["resource_set_sha256"],
            "provider": kinds["platform-provider"], "profile": kinds["programming-profile"],
            "icpn": resource["constraints"]["icpn"],
            "operations": list(resource["constraints"]["operations"]),
        }

    def enqueue(self, request: JobRequest, *,
                trusted_provider: TrustedProviderAction | None = None) -> asyncio.Future[JobResult]:
        if not self._started:
            raise PlasmaError(ErrorCode.INTERNAL_ERROR, "site manager is not started")
        request.validate()
        if request.operation in {Operation.STATUS, Operation.CANCEL}:
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "status/cancel are control operations")
        worker = self._resolve_site(request.site_id)
        site_config = self._site_configs[request.site_id]
        # Trusted root-only Package selection is bound to the exact Programming
        # Job; public metadata cannot impersonate Package Provider authority.
        if trusted_provider is not None:
            if (not isinstance(trusted_provider, TrustedProviderAction)
                    or site_config.interface == "mock"
                    or request.site_id not in self.provider_interfaces
                    or request.job_id != trusted_provider.asset_request.job_id
                    or request.site_id != trusted_provider.route.site_id
                    or request.target != trusted_provider.route.target
                    or request.metadata.get("provider") != trusted_provider.route.provider_package
                    or request.metadata.get("profile") != trusted_provider.route.profile_package
                    or request.operation.value != trusted_provider.route.operation
                    or request.max_retries != 0):
                raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "PROVIDER_JOB_NOT_AUTHORIZED")
        elif request.metadata.get("provider") is not None:
            interface = self.interfaces[request.site_id]
            # Provider and Profile are part of a Job Binding's own identity, so
            # an interface that admits Bindings may carry them -- the Binding is
            # still re-verified under the Job lease before anything executes.
            admits_binding = (getattr(interface, "CONSUMES_JOB_BINDING", False)
                              and bool(JOB_BINDING_KEYS.intersection(request.metadata)))
            if not admits_binding:
                raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                                  "PROVIDER_JOB_NOT_AUTHORIZED")
        if request.target is None and site_config.interface != "mock":
            # IC selection is a Job input, not persistent Site configuration.
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "target (exact ICPN) is required for a real-hardware Job",
                context={"site_id": request.site_id},
            )
        if worker.queue.full():
            raise PlasmaError(
                ErrorCode.SITE_BUSY,
                f"SITE{request.site_id} queue is full",
                recoverable=True,
            )

        enqueue_started = (time.monotonic()
                           if os.environ.get("PLASMA_M0_TIMING") == "1" else None)
        # Reserve before reading Active identity or resolving a hardware route.
        # The same lease excludes activation/FPGA reload through every queued
        # Job, retry and cancellation cleanup, across the whole PPU.
        runtime = self.registry.create(request)
        # Observation only: per-step admission durations (ms) for this Job.
        timing: dict[str, float] = {}
        clock = time.monotonic()

        def lap(name: str) -> None:
            nonlocal clock
            now = time.monotonic()
            timing[name + "_ms"] = round((now - clock) * 1000.0, 1)
            clock = now

        try:
            owner_kind, owner_id = self._reserve_execution_job(request)
            lap("reserve")
            # Pin the trusted Active Set when the Runtime composition provides it.
            pinned = deepcopy(self._active_asset_set_reader()) if self._active_asset_set_reader else {
                "state": "EMPTY", "asset_set_sha256": None, "ready": False,
            }
            lap("active_set")
            bundle_keys = {
                "bundle_asset_set_sha256", "bundle_asset_package_id",
                "bundle_asset_sha256",
            }
            selected = bundle_keys.intersection(request.metadata)
            binding_selected = bool(JOB_BINDING_KEYS.intersection(request.metadata))
            if selected:
                raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                                  "JOB_IMAGE_SOURCE_NOT_EXCLUSIVE")
            if binding_selected:
                runtime.job_binding = self._admit_job_binding(request, pinned)
                runtime.fpga_identity_guard = partial(
                    self._guard_reserved_fpga_identity, request.job_id)
                lap("job_binding")
            request = self.execution_routers[request.site_id].admit(
                request, trusted_provider=trusted_provider)
            lap("route_admit")
            if trusted_provider is not None:
                if (pinned.get("state") != "ACTIVE"
                        or pinned.get("asset_set_sha256") != trusted_provider.route.asset_set_sha256):
                    raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "PROVIDER_ACTIVE_SET_MISMATCH")
            runtime.request = request
            runtime.active_asset_set = pinned
            runtime.trusted_provider = trusted_provider
            self.output.write_state(request.job_id, worker._state_payload(runtime))
            lap("write_state")
            runtime.admission_timing_ms = timing
            worker.enqueue(runtime)
        except Exception:
            self.registry.discard(request.job_id)
            with self._execution_lock:  # refused before enqueue: never ran
                if self._reservation is not None:
                    self._reservation["job_ids"].discard(request.job_id)
            self._release_execution_job(request.job_id)
            raise
        runtime.future.add_done_callback(
            lambda _future, job_id=request.job_id: self._release_execution_job(job_id)
        )
        if enqueue_started is not None:
            _m0_timing("ppu_enqueue", job_id=request.job_id,
                       site_id=request.site_id,
                       duration_ms=round((time.monotonic() - enqueue_started) * 1000, 3),
                       admission_timing_ms=timing)
        self.server_log.event(
            "INFO",
            "job_queued",
            ppu_id=self.config.ppu.id,
            facility_id=self.config.ppu.facility_id,
            job_id=request.job_id,
            site_id=request.site_id,
            operation=request.operation.value,
            execution_owner_kind=owner_kind,
            execution_owner_id=owner_id,
            admission_timing_ms=timing,
        )
        return runtime.future

    async def submit(self, request: JobRequest) -> JobResult:
        return await self.enqueue(request)

    def cancel(self, job_id: str) -> dict[str, Any]:
        runtime = self.registry.get(job_id)
        worker = self._resolve_site(runtime.request.site_id)
        already_terminal = runtime.state.terminal
        worker.cancel(runtime)
        runtime.updated_at = iso_now()
        self.server_log.event(
            "INFO",
            "job_cancel_requested",
            ppu_id=self.config.ppu.id,
            facility_id=self.config.ppu.facility_id,
            job_id=job_id,
            site_id=runtime.request.site_id,
            already_terminal=already_terminal,
        )
        return {
            "job_id": job_id,
            "accepted": not already_terminal,
            "state": runtime.state.value,
            "cancel_requested": runtime.cancel_requested,
        }

    def ppu_snapshot(self) -> dict[str, Any]:
        ppu = self.config.ppu
        return {
            "ppu_id": ppu.id,
            "facility_id": ppu.facility_id,
            "model": ppu.model,
            "display_name": ppu.display_name,
            "site_count": self.config.site_count,
            "enabled_site_count": self.config.enabled_site_count,
            "execution": self.execution_lease_snapshot(),
            "resource_reservation": self.resource_reservation_snapshot(),
            "runtime_activation": self.runtime_quiesce_snapshot(),
            "capabilities": {
                "max_supported_sites": self.config.server.max_supported_sites,
                "operations": [
                    Operation.ERASE.value,
                    Operation.PROGRAM.value,
                    Operation.VERIFY.value,
                    Operation.READ.value,
                ],
            },
        }

    def _latest_job_summary(self, site_id: int) -> dict[str, Any] | None:
        """Return a browser-safe latest-job summary without result files or raw metadata."""
        for runtime in reversed(self.registry.all()):
            if runtime.request.site_id != site_id:
                continue
            return {
                "job_id": runtime.request.job_id,
                "operation": runtime.request.operation.value,
                "state": runtime.state.value,
                "stage": runtime.stage,
                "stage_state": runtime.stage_state,
                "stage_states": dict(runtime.stage_states),
                "progress_percent": runtime.progress_percent,
                "created_at": runtime.created_at,
                "started_at": runtime.started_at,
                "updated_at": runtime.updated_at,
                "cancel_requested": runtime.cancel_requested,
            }
        return None

    def status(
        self,
        *,
        site_id: int | None = None,
        job_id: str | None = None,
        protocol_version: str = PROTOCOL_VERSION,
    ) -> dict[str, Any]:
        if protocol_version != PROTOCOL_VERSION:
            raise PlasmaError(
                ErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
                f"unsupported protocol version: {protocol_version!r}",
            )
        # Observe the entire site-scoped status, not only its Resource read.
        status_started = (time.monotonic()
                          if site_id is not None and os.environ.get("PLASMA_M0_TIMING") == "1"
                          else None)
        if job_id:
            return {"job": self.registry.get(job_id).snapshot(protocol_version)}
        site_ids = [site_id] if site_id is not None else sorted(self._site_configs)
        sites: list[dict[str, Any]] = []
        for current_id in site_ids:
            config = self._site_configs.get(current_id)
            if config is None:
                raise PlasmaError(ErrorCode.SITE_INVALID, f"site does not exist: SITE{current_id}")
            worker = self.workers.get(current_id)
            sites.append(
                {
                    "site_id": current_id,
                    "enabled": config.enabled,
                    "state": worker.state.value if worker else SiteState.DISABLED.value,
                    "current_job_id": (
                        worker.current.request.job_id if worker and worker.current else None
                    ),
                    "latest_job": self._latest_job_summary(current_id),
                    "queued_jobs": worker.queue.qsize() if worker else 0,
                    "interface": config.interface if config.enabled else None,
                    "target": (worker.current.request.target if worker and worker.current else None),
                }
            )
        ppu = self.ppu_snapshot()
        if site_id is not None:
            # Site-scoped status (Manager readiness) carries the PPU-derived
            # Resource identity; unscoped UI polling does not pay for it.
            resources_started = time.monotonic() if status_started is not None else None
            try:
                ppu["active_resources"] = self.active_resources_snapshot()
            finally:
                if resources_started is not None:
                    _m0_timing("ppu_site_resources", site_id=site_id,
                               duration_ms=round((time.monotonic() - resources_started) * 1000, 3))
        if site_id is not None and status_started is not None:
            _m0_timing("ppu_site_status", site_id=site_id,
                       duration_ms=round((time.monotonic() - status_started) * 1000, 3))
        return {
            "ppu": ppu,
            "sites": sites,
        }
