"""Host-only fixture: a real Manager HTTP server holding journalled Read runs.

Started by ``read-binary-bff-manager-http.test.mjs``. It serves the real
``BootstrapPlasmaManagerHandler`` over the real ``BundleProgrammingWorkflow``
(standard library only). No PPU exists here: any Gateway or Coordinator use
raises, so a download can only ever come from retained bytes.

Prints one JSON line (port and run facts) and serves until stdin closes.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))

from plasma_manager.bootstrap_server import BootstrapPlasmaManagerHandler  # noqa: E402
from plasma_manager.config import ManagerConfig  # noqa: E402
from plasma_manager.programming import BundleProgrammingWorkflow, _Run  # noqa: E402
from plasma_manager.registry import PPURegistryStore  # noqa: E402
from plasma_manager.server import PPUOperationGate  # noqa: E402

ALIAS = "z2"
ADDRESS, LENGTH = 0x08000000, 65536
FILENAME = f"read-STM32F103C8T6-0x{ADDRESS:08x}-{LENGTH}.bin"
DATA = (bytes(range(256)) * 256)[:LENGTH]
RUNS = {"ok": "a" * 32, "missing": "b" * 32, "mismatch": "c" * 32, "failed": "d" * 32}


class NoPpu:
    """Any attribute use means something tried to reach a PPU."""

    def __getattr__(self, name):
        raise AssertionError(f"fixture has no PPU: {name}")


def no_gateway(_endpoint, _timeout):
    raise AssertionError("fixture has no PPU Gateway")


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="plasma-read-output-"))
    registry = PPURegistryStore((), root / "registry.json")
    registry.add(alias=ALIAS, endpoint="http://192.168.2.99:18080")
    workflow = BundleProgrammingWorkflow(
        coordinator=NoPpu(), registry=registry, gateway_client_factory=no_gateway,
        gate=PPUOperationGate(), request_timeout_s=5.0,
        journal_path=root / "bundle-programming-runs.json")
    digest = hashlib.sha256(DATA).hexdigest()
    for kind, run_id in RUNS.items():
        failed = kind == "failed"
        run = _Run(run_id=run_id, alias=ALIAS, site=2, plan={"operation": "read"},
                   state="completed", outcome="FAIL" if failed else "PASS",
                   job_submission_count=1,
                   receipt={"read_output": {
                       "address": ADDRESS, "bytes": LENGTH, "sha256": digest,
                       "filename": FILENAME, "available": not failed}})
        workflow._runs[run_id] = run
        if kind == "ok":
            workflow._store_read_output(run, DATA)
        elif kind == "mismatch":
            # Retained bytes whose SHA-256 is not the receipt's.
            workflow._store_read_output(run, bytes([DATA[0] ^ 0xFF]) + DATA[1:])

    handler = BootstrapPlasmaManagerHandler
    handler.config = ManagerConfig(registry_state_path=root / "registry.json")
    handler.registry_store = registry
    handler.bootstrap_coordinator = NoPpu()
    handler.operation_gate = PPUOperationGate()
    handler.programming_workflow = workflow
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(json.dumps({"port": server.server_address[1], "runs": RUNS, "sha256": digest,
                      "bytes": LENGTH, "filename": FILENAME}), flush=True)
    sys.stdin.read()
    server.shutdown()


if __name__ == "__main__":
    main()
