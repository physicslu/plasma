"""Runtime-side composition of Stage C (no second executor, engine or journal).

One entry point used by the Runtime process (uid plasma):

    C-1 SiteManager.package_action_scope  (Job lease, quiesce, exclusivity)
    -> ppu_asset_execution.dispatch        (Active Set, identity, owner auth)
    -> C-2 ppu_package_launcher executor    (journal, receipt, timeout/cancel)
       with SystemdUnitSpawner             (Package runs as plasma-package)
    -> optional C-3 Site Worker client     (Site Packages only)

The control-plane modules are loaded by path from the installed, root-owned
control-plane directory; nothing is imported from a Bundle. Without a Site
Worker client, Packages that declare Sites stay PACKAGE_SITE_TRANSPORT_NOT_WIRED.
No public API endpoint is added here.
"""
from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path
from typing import Any, Mapping


def _load(control_plane: Path, filename: str):
    src = Path(control_plane) / filename
    if src.is_symlink() or not src.is_file():
        raise RuntimeError(f"PACKAGE_ACTION_CONTROL_PLANE_MISSING:{filename}")
    if str(control_plane) not in sys.path:
        sys.path.insert(0, str(control_plane))
    name = "plasma_package_action_" + filename.replace(".", "_")
    spec = importlib.util.spec_from_file_location(name, src)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class PackageActionRuntime:
    def __init__(self, site_manager: Any, *, control_plane: Path, product_root: Path,
                 state_root: Path, owner_credential: Any, spawner: Any,
                 python_executable: Path, site_worker: Any | None = None) -> None:
        self.site_manager = site_manager
        self.execution = _load(control_plane, "ppu_asset_execution.py")
        self.launcher = _load(control_plane, "ppu_package_launcher.py")
        self.product_root = Path(product_root)
        self.state_root = Path(state_root)
        self.owner_credential = owner_credential
        self.spawner = spawner
        self.python_executable = Path(python_executable)
        self.site_worker = site_worker

    def run(self, request: Any, authorization: Mapping[str, Any], *,
            cancel_event: threading.Event | None = None) -> dict[str, Any]:
        executor = self.launcher.make_package_executor(
            self.product_root, python_executable=self.python_executable,
            state_root=self.state_root, cancel_event=cancel_event,
            site_worker=self.site_worker, spawner=self.spawner)
        return self.execution.dispatch_asset_execution(
            self.product_root, request, authorization=authorization,
            owner_credential=self.owner_credential,
            execution_scope=lambda: self.site_manager.package_action_scope(request.job_id),
            trusted_executors={"python": executor, "native-c": executor})

    def reconcile_on_start(self) -> dict[str, Any]:
        """After a Runtime restart: stop leftover Package units, report the
        journal records that never reached a terminal state. Their hardware
        outcome is unknown; the Site Worker already dropped their sessions."""
        interrupted = self.launcher.interrupted_actions(self.state_root)
        stopped = []
        stop = getattr(self.spawner, "stop_leftover", None)
        if stop is not None:
            stopped = stop()
        return {"interrupted_jobs": interrupted, "stopped_units": stopped}
