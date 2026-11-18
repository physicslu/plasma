"""Adapter exposing the REAL LOM-P2A-2 engine under the P2A-0 model's interface.

``test_lom_p2a2_reference_equivalence.py`` re-runs every P2A-0 reference case
(``test_lom_p2a0_enrollment_spec.py``) with ``m`` bound to this module, so the
same 35+ scenarios exercise ``scripts/ppu_controller.py`` with real atomic
files (temp+fsync+rename) in a temporary directory, the real SD ticket parser
and the real client crypto of ``scripts/ppu_local_enrollment.py``. Only the PPU
safety observation is the model's ``SafetyState`` (adapted read-only).
"""
from __future__ import annotations

import importlib.util
import json
import secrets  # noqa: F401  (re-exported for the reference tests)
import sys
import tempfile
from pathlib import Path
from typing import Any

from .lom_p2a0_reference_model import (  # noqa: F401  (re-exported)
    CONTROLLER_STATES,
    ENROLLMENT_STATES,
    SafetyState,
)

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, file_name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file_name)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


controller = _load("plasma_ppu_controller", "ppu_controller.py")
proto = controller.proto

SCHEMA = proto.SCHEMA
TICKET_SCHEMA = proto.TICKET_SCHEMA
TICKET_FILE = proto.TICKET_FILE
MAX_TICKET_FILE_BYTES = proto.MAX_TICKET_FILE_BYTES
ENROLLMENT_WINDOW_S = proto.ENROLLMENT_WINDOW_S
MAX_CLAIM_FAILURES = proto.MAX_CLAIM_FAILURES
LEDGER_CAPACITY = proto.LEDGER_CAPACITY
MODE_NORMAL = proto.MODE_NORMAL
MODE_RECOVERY_ONLY = proto.MODE_RECOVERY_ONLY
ERROR_CODES = controller.SPEC_ERROR_CODES
NORMAL_WRITES = controller.NORMAL_WRITES
RECOVERY_ACTIONS = controller.RECOVERY_ACTIONS
CRASH_POINTS = controller.CRASH_POINTS
SpecError = controller.ControllerError
Crash = controller.Crash
make_ticket_file = proto.make_ticket_file
ticket_id = proto.ticket_id
ticket_key = proto.ticket_key
claim_mac = proto.claim_mac


class _BootDir:
    """dict-like view of the boot-partition directory used by the model tests."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory
        directory.mkdir(parents=True, exist_ok=True)

    def __setitem__(self, name: str, raw: bytes) -> None:
        (self.dir / name).write_bytes(raw)

    def __contains__(self, name: str) -> bool:
        return (self.dir / name).exists()

    def pop(self, name: str, default: Any = None) -> Any:
        path = self.dir / name
        if not path.exists():
            return default
        raw = path.read_bytes()
        path.unlink()
        return raw


class Disk:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="lom-p2a2-")
        root = Path(self._tmp.name)
        self.store = controller.ControllerStore(root / "state")
        self.boot_partition = _BootDir(root / "boot")

    @property
    def records(self) -> dict[str, Any]:
        return self.store.snapshot()

    def get(self, key: str) -> Any:
        value = self.store.get(key)
        return json.loads(json.dumps(value)) if value is not None else None

    def put(self, key: str, value: Any) -> None:
        self.store.put(key, value)

    def delete(self, key: str) -> None:
        self.store.delete(key)


class _Probe:
    def __init__(self, state: SafetyState) -> None:
        self.state = state

    def active_operations(self) -> list[str]:
        return self.state.active_operations()

    def seals(self) -> list[int]:
        return sorted(self.state.seals)

    def unknown_outcomes(self) -> list[str]:
        return sorted(self.state.unknown_outcomes)

    def active_set_recovery_required(self) -> bool:
        return self.state.active_set_state == "RECOVERY_REQUIRED"

    def extra_blockers(self) -> list[str]:
        return []

    def diagnose_site(self, site: int) -> dict[str, Any]:
        return {"site": site, "sealed": site in self.state.seals}

    def recover_site(self, site: int, *, operator: str) -> dict[str, Any]:
        marker = self.state.seals.pop(site)     # stands in for the Embedded procedure
        self.state.recovery_evidence.append(f"site{site}.sealed archived: {marker}")
        return {"result": "RECOVERED", "site": site}


class _FailingBootPartition(controller.BootPartition):
    def delete(self) -> None:
        raise OSError("boot partition is read-only")


class PPU:
    def __init__(self, disk: Disk, safety: SafetyState, *, device_id: str, boot_id: str,
                 now: float = 0.0, crash_at: str | None = None,
                 boot_partition_delete_fails: bool = False) -> None:
        if boot_id not in safety.boot_ids:
            safety.boot_ids.append(boot_id)
        self.engine = controller.EnrollmentEngine(
            disk.store, _Probe(safety), device_id=device_id, boot_id=boot_id, crash_at=crash_at)
        partition_cls = _FailingBootPartition if boot_partition_delete_fails else controller.BootPartition
        self.engine.boot_consume(partition_cls(disk.boot_partition.dir), now)

    @property
    def crash_at(self) -> str | None:
        return self.engine.crash_at

    @crash_at.setter
    def crash_at(self, value: str | None) -> None:
        self.engine.crash_at = value

    @property
    def events(self) -> list[str]:
        return self.engine.events

    def controller(self) -> dict[str, Any] | None:
        return self.engine.store.get("controller")

    def controller_state(self) -> str:
        return self.engine.controller_state()

    def enrollment_state(self, now: float) -> str:
        return self.engine.enrollment_state(now)

    def engineering_arm(self, now: float, *, authorized: bool) -> str:
        return self.engine.engineering_arm(now, authorized=authorized)

    def challenge(self, now: float) -> dict[str, Any]:
        return self.engine.challenge(now)

    def claim(self, request: dict[str, Any], now: float) -> dict[str, Any]:
        return self.engine.claim(request, now)

    def authorize(self, credential: str, operation: str) -> str:
        return self.engine.authorize(credential, operation)

    def recover_site(self, credential: str, site: int, *, explicit_request: bool) -> None:
        self.engine.recover_site(credential, site, explicit_request=explicit_request)

    def reconcile(self, credential: str, txn: str, decision: str, evidence: str, *,
                  explicit_request: bool) -> None:
        self.engine.reconcile(credential, txn, decision, evidence, explicit_request=explicit_request)

    def recovery_complete(self, credential: str, *, observed_device_id: str) -> str:
        return self.engine.recovery_complete(credential, observed_device_id=observed_device_id)


def client_claim(ppu: PPU, ticket: str, now: float, *, label: str = "station-b",
                 controller_nonce: str | None = None) -> tuple[dict[str, Any], str, str]:
    """What the Manager client does, with the real protocol module."""
    challenge = ppu.challenge(now)
    cn = controller_nonce or secrets.token_hex(16)
    key = proto.ticket_key(ticket)
    response = ppu.claim(proto.claim_request(key, challenge, controller_nonce=cn, label=label), now)
    credential = proto.unwrap_credential(key, nonce=response["wrap_nonce"], controller_nonce=cn,
                                         generation=response["generation"],
                                         wrapped=response["wrapped_credential"])
    return response, credential, cn
