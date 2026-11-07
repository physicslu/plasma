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
import asyncio
from functools import partial
from pathlib import Path
from typing import Any, Mapping

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest
from plasma_interfaces.package_provider import PackageProviderInterface, TrustedProviderAction


def from_config(site_manager: Any, config_path: Path) -> "PackageActionRuntime":
    """Production wiring from ``plasma.ppu.package-actions-config.v1`` JSON.

    Package processes run as ``package_user`` through the fixed-purpose unit
    helper; the Site Worker client is used only when its control socket is set.
    """
    import json
    import pwd
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    keys = {"schema", "control_plane", "product_root", "state_root", "python",
            "package_user", "helper_socket", "site_worker_control_socket"}
    if not isinstance(cfg, dict) or set(cfg) != keys or cfg["schema"] != "plasma.ppu.package-actions-config.v1":
        raise RuntimeError("PACKAGE_ACTIONS_CONFIG_INVALID")
    control_plane = Path(cfg["control_plane"])
    launcher = _load(control_plane, "ppu_package_launcher.py")
    helper = _load(control_plane, "ppu_package_unit_helper.py")
    spawner = launcher.SystemdUnitSpawner(
        package_uid=pwd.getpwnam(cfg["package_user"]).pw_uid,
        systemctl=helper.HelperSystemctl(Path(cfg["helper_socket"])))
    site_worker = None
    if cfg["site_worker_control_socket"]:
        worker = _load(control_plane, "ppu_site_worker.py")
        site_worker = worker.SiteWorkerClient(Path(cfg["site_worker_control_socket"]))
    return PackageActionRuntime(site_manager, control_plane=control_plane,
                                product_root=Path(cfg["product_root"]), state_root=Path(cfg["state_root"]),
                                owner_credential=None, spawner=spawner,
                                python_executable=Path(cfg["python"]), site_worker=site_worker)


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
                 python_executable: Path, site_worker: Any | None = None,
                 hardware_observer: Any | None = None) -> None:
        self.site_manager = site_manager
        self.execution = _load(control_plane, "ppu_asset_execution.py")
        self.launcher = _load(control_plane, "ppu_package_launcher.py")
        self.provider_contract = _load(control_plane, "ppu_provider_contract.py")
        self.hardware_observer = hardware_observer
        self.product_root = Path(product_root)
        self.control_plane = Path(control_plane)
        from plasma_interfaces.openocd import OpenOCDInterface

        reference = _load(control_plane, "ppu_opf_reference_openocd.py")
        for interface in getattr(site_manager, "interfaces", {}).values():
            if isinstance(interface, OpenOCDInterface) and interface.site_worker_ready:
                interface.opf_flash_executor = partial(
                    reference.execute_runtime_flash, product_root=self.product_root)
                interface.opf_flash_preflight = partial(
                    reference.preflight_runtime_flash, product_root=self.product_root)
        # Pin the configured Asset Set at Job admission. Never infer a product
        # directory from the host or re-check PL hardware for ordinary Jobs.
        if (hasattr(site_manager, "_active_asset_set_reader")
                and site_manager._active_asset_set_reader is None):
            site_manager._active_asset_set_reader = (
                lambda: _load(control_plane, "ppu_asset_set.py").read_active(self.product_root)
            )
        # Bundle Programming Asset is selected only inside SiteManager's existing Job lease.
        # The trusted control-plane resolver revalidates Active Set + B3 files.
        if (hasattr(site_manager, "_bundle_firmware_resolver")
                and site_manager._bundle_firmware_resolver is None):
            active_helper = _load(control_plane, "ppu_asset_set.py")
            site_manager._bundle_firmware_resolver = partial(
                active_helper.resolve_active_firmware, self.product_root)
        self.state_root = Path(state_root)
        self.owner_credential = owner_credential
        self.spawner = spawner
        self.python_executable = Path(python_executable)
        self.site_worker = site_worker
        for interface in getattr(site_manager, "interfaces", {}).values():
            if isinstance(interface, PackageProviderInterface):
                interface.wire_runtime(self._run_programming_package)

    def _run_programming_package(self, trusted: TrustedProviderAction,
                                 cancel_event: threading.Event) -> dict[str, Any]:
        """Execute under the parent Programming Job, not a second Package lease."""
        typed = trusted.asset_request
        executor = self.launcher.make_package_executor(
            self.product_root, python_executable=self.python_executable,
            state_root=self.state_root, cancel_event=cancel_event,
            site_worker=self.site_worker, spawner=self.spawner)
        return self.execution.dispatch_asset_execution(
            self.product_root, typed, authorization=trusted.authorization,
            owner_credential=trusted.owner_credential,
            execution_scope=lambda: self.site_manager.programming_package_scope(
                typed.job_id, trusted.route.site_id),
            trusted_executors={typed.package_kind: executor})

    async def run_programming_control(
            self, request: Mapping[str, Any], authorization: Mapping[str, Any],
            ephemeral_credential: str, device_id: str,
            cancel_event: threading.Event) -> dict[str, Any]:
        """Root-authorized option of the existing Package Action control socket.

        There is no additional public endpoint, execution engine, or Site owner.
        Hardware capability must come from a trusted observer; unconfigured
        production hardware fails closed (Host-only fake may inject an observer).
        """
        if (not isinstance(request, Mapping)
                or set(request) != {"asset_set_sha256", "package_id", "package_version",
                                    "package_kind", "package_identity_sha256", "job_id",
                                    "programming"}):
            raise ValueError("PROVIDER_PROGRAMMING_REQUEST_INVALID")
        programming = request["programming"]
        required = {"site_id", "target", "operation", "profile",
                    "asset_package_id", "asset_sha256"}
        if (type(programming) is not dict or set(programming) != required
                or type(programming["site_id"]) is not int
                or programming["site_id"] < 1
                or any(type(programming[k]) is not str or not programming[k]
                       for k in required - {"site_id"})
                or programming["operation"] != "flash_cycle"
                or self.hardware_observer is None):
            raise ValueError("PROVIDER_PROGRAMMING_NOT_QUALIFIED")
        data = {key: request[key] for key in request if key != "programming"}
        typed = self.execution.AssetExecutionRequest(**data)
        if typed.package_kind not in ("python", "native-c"):
            raise ValueError("PROVIDER_EXECUTABLE_KIND_DENIED")
        credential = self.execution.OwnerCredential(
            device_id=device_id, credential=ephemeral_credential)
        plan = self.execution.prepare_asset_execution(
            self.product_root, typed, authorization=authorization,
            owner_credential=credential)
        resources = plan["resources"]
        site_id = programming["site_id"]
        if (resources is None or resources["sites"] != [site_id]
                or self.site_worker is None):
            raise ValueError("PROVIDER_SITE_TRANSPORT_NOT_WIRED")
        active = _load(self.control_plane,
                       "ppu_asset_set.py")
        resolved = active.resolve_active_firmware(
            self.product_root, asset_set_sha256=typed.asset_set_sha256,
            asset_package_id=programming["asset_package_id"],
            profile_package_id=programming["profile"],
            asset_sha256=programming["asset_sha256"])
        hardware = self.hardware_observer(site_id)
        route = self.provider_contract.resolve(
            self.product_root, asset_set_sha256=typed.asset_set_sha256,
            target=programming["target"], provider=typed.package_id,
            profile=programming["profile"], operation="flash_cycle",
            site_id=site_id, image_size=len(resolved["image"]),
            hardware=hardware, options={})
        job = JobRequest(
            site_id=site_id, operation=Operation.FLASH_CYCLE,
            image=resolved["image"], target=programming["target"],
            job_id=typed.job_id, timeout_s=float(resources["max_runtime_s"]),
            max_retries=0, client_id="plasma-programming-package",
            metadata={"provider":typed.package_id, "profile":programming["profile"],
                      "image_name":resolved["image_name"],
                      "source_asset_sha256":resolved["image_sha256"]})
        trusted = TrustedProviderAction(typed, authorization, credential, route)
        future = self.site_manager.enqueue(job, trusted_provider=trusted)
        while not future.done():
            if cancel_event.is_set():
                self.site_manager.cancel(job.job_id)
            await asyncio.sleep(0.05)
        return (await future).to_dict()

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

    def run_control(self, request: Mapping[str, Any], authorization: Mapping[str, Any],
                    ephemeral_credential: str, device_id: str,
                    cancel_event: threading.Event | None = None) -> dict[str, Any]:
        """Runtime-control entry (root operator only; see RuntimeControlServer).

        The one-time ``ephemeral_credential`` verifies an authorization the
        root operator re-issued after verifying the owner's asset.execute
        authorization with the Bootstrap credential. One launch per job_id
        is enforced by the C-2 journal.
        """
        if not isinstance(request, Mapping):
            raise ValueError("PACKAGE_ACTION_REQUEST_INVALID")
        fields = ("asset_set_sha256", "package_id", "package_version", "package_kind",
                  "package_identity_sha256", "job_id")
        if set(request) != set(fields):
            raise ValueError("PACKAGE_ACTION_REQUEST_INVALID")
        typed = self.execution.AssetExecutionRequest(**{k: request[k] for k in fields})
        credential = self.execution.OwnerCredential(device_id=device_id, credential=ephemeral_credential)
        executor = self.launcher.make_package_executor(
            self.product_root, python_executable=self.python_executable,
            state_root=self.state_root, cancel_event=cancel_event,
            site_worker=self.site_worker, spawner=self.spawner)
        return self.execution.dispatch_asset_execution(
            self.product_root, typed, authorization=authorization, owner_credential=credential,
            execution_scope=lambda: self.site_manager.package_action_scope(typed.job_id),
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
