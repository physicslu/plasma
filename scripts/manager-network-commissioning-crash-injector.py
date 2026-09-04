#!/usr/bin/env python3
"""Test-only Plasma Manager launcher that crashes after a durable commissioning state.

This script is not part of the product runtime. It monkey-patches only the test
process so the real NetworkCommissioningStore.put() first completes its atomic
journal write, then the process is terminated with SIGKILL at a named durable
boundary. Restart acceptance must use the unmodified production Manager.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Crash-inject Plasma Manager after a durable commissioning state")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--crash-after-state",
        required=True,
        choices=("identity_verified", "activation_committed"),
    )
    args = parser.parse_args()

    repo = _repo_root()
    python_root = repo / "software/python"
    sys.path.insert(0, str(python_root))

    from plasma_manager.config import load_manager_config
    from plasma_manager.network_commissioning import NetworkCommissioningStore
    from plasma_manager import server

    original_put = NetworkCommissioningStore.put
    target_state = args.crash_after_state

    def crash_after_durable_put(self, record):
        persisted = original_put(self, record)
        if getattr(record, "state", None) == target_state:
            print(f"PLASMA_MANAGER_CRASH_INJECTED_AFTER={target_state}", flush=True)
            os.kill(os.getpid(), signal.SIGKILL)
        return persisted

    NetworkCommissioningStore.put = crash_after_durable_put
    server.serve(load_manager_config(args.config.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
