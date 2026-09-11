#!/usr/bin/env python3
"""P3 wrapper around the retained P2 Z2 installer core.

The wrapper deliberately keeps the audited release-verification/install machinery in
`ppu-z2-installer-core.py` and adds only the P3 operational delta. The retained
bootstrap still owns ``--plasma-python`` validation: the isolated runtime must be a
final ``release >= 3.11`` and its ``releaselevel`` must be ``final``. Local health
probing remains explicitly proxy-free through
``urllib.request.build_opener(urllib.request.ProxyHandler({}))``. The wrapper and
its sibling core are one bootstrap unit and release packaging must ship and verify
both files together.

* successful upgrades preserve an existing canonical `/etc/plasma/ppu.yaml`
  instead of regenerating `sites: []`;
* Plasma Server exposes a local authoritative quiesce socket;
* Plasma Gateway receives only the bounded runtime-activation helper socket;
* a root helper exposes exactly one operation: restart `plasma-server.service`.

No PL, FPGA, DUT power, or real-IC operation is introduced here.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Mapping


CORE_PATH = Path(__file__).with_name("ppu-z2-installer-core.py")
_spec = importlib.util.spec_from_file_location("plasma_ppu_z2_installer_core", CORE_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"cannot load retained installer core: {CORE_PATH}")
_core = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _core
_spec.loader.exec_module(_core)

for _name in dir(_core):
    if not _name.startswith("__"):
        globals().setdefault(_name, getattr(_core, _name))

_original_render_systemd_units = _core.render_systemd_units
_original_install_release = _core.install_release

SERVER_CONTROL_SOCKET = Path("/run/plasma-server/control.sock")
RUNTIME_ACTIVATION_SOCKET = Path("/run/plasma-runtime-activation/helper.sock")
RUNTIME_ACTIVATION_SERVICE = "plasma-runtime-activation.service"


def render_runtime_activation_unit(*, paths, python_runtime) -> str:
    app = paths.current / "runtime" / "ppu" / "ppu.pyz"
    return "\n".join(
        [
            "[Unit]",
            "Description=Plasma bounded runtime activation helper",
            "After=plasma-server.service",
            "Requires=plasma-server.service",
            "",
            "[Service]",
            "Type=simple",
            "User=root",
            "Group=plasma",
            "RuntimeDirectory=plasma-runtime-activation",
            "RuntimeDirectoryMode=0750",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "ProtectHome=true",
            "ProtectSystem=strict",
            "RestrictAddressFamilies=AF_UNIX",
            "Restart=on-failure",
            "RestartSec=2",
            (
                f"ExecStart={python_runtime.path} {app} runtime-activation-helper "
                f"--socket {RUNTIME_ACTIVATION_SOCKET} "
                f"--server-control-socket {SERVER_CONTROL_SOCKET}"
            ),
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )


def render_systemd_units(*, paths, python_runtime, gateway_host: str, catalog_relative: str) -> dict[str, str]:
    units = _original_render_systemd_units(
        paths=paths,
        python_runtime=python_runtime,
        gateway_host=gateway_host,
        catalog_relative=catalog_relative,
    )
    server = units["plasma-server.service"]
    server = server.replace(
        "Type=simple\n",
        "Type=simple\nRuntimeDirectory=plasma-server\nRuntimeDirectoryMode=0700\n",
        1,
    )
    server = server.replace(
        f" server --config {paths.config_root / 'ppu.yaml'}",
        f" server --config {paths.config_root / 'ppu.yaml'} --runtime-control-socket {SERVER_CONTROL_SOCKET}",
        1,
    )

    gateway = units["plasma-web.service"]
    gateway = gateway.replace(
        "After=network-online.target plasma-server.service",
        f"After=network-online.target plasma-server.service {RUNTIME_ACTIVATION_SERVICE}",
        1,
    )
    gateway = gateway.replace(
        "Requires=plasma-server.service",
        f"Requires=plasma-server.service {RUNTIME_ACTIVATION_SERVICE}",
        1,
    )
    gateway = gateway.replace(
        f"--ppu-config {paths.config_root / 'ppu.yaml'} ",
        f"--ppu-config {paths.config_root / 'ppu.yaml'} --runtime-activation-socket {RUNTIME_ACTIVATION_SOCKET} ",
        1,
    )
    return {
        "plasma-server.service": server,
        "plasma-web.service": gateway,
        RUNTIME_ACTIVATION_SERVICE: render_runtime_activation_unit(
            paths=paths,
            python_runtime=python_runtime,
        ),
    }


def install_release(
    verified,
    *,
    python_runtime,
    gateway_host: str,
    paths,
    ppu_id: str,
    facility_id: str,
    display_name: str,
    systemctl=_core._systemctl,
    health_check=_core._health_ready,
    ensure_service_account=_core._ensure_service_account,
) -> dict[str, object]:
    config_path = paths.config_root / "ppu.yaml"
    helper_unit = paths.systemd_root / RUNTIME_ACTIVATION_SERVICE
    helper_snapshot = _core._snapshot_file(helper_unit)
    existing_config = _core._snapshot_file(config_path)

    units = render_systemd_units(
        paths=paths,
        python_runtime=python_runtime,
        gateway_host=_core._validate_gateway_host(gateway_host),
        catalog_relative=_core._catalog_relative(verified.runtime_manifest),
    )

    helper_unit.parent.mkdir(parents=True, exist_ok=True)
    _core._write_text_atomic(helper_unit, units[RUNTIME_ACTIVATION_SERVICE])

    original_writer = _core._write_text_atomic
    original_renderer = _core.render_systemd_units

    def preserving_writer(path: Path, content: str, mode: int = 0o644) -> None:
        if path == config_path and existing_config.existed:
            path.chmod(0o640)
            return
        original_writer(path, content, mode)

    _core._write_text_atomic = preserving_writer
    _core.render_systemd_units = render_systemd_units
    try:
        evidence = _original_install_release(
            verified,
            python_runtime=python_runtime,
            gateway_host=gateway_host,
            paths=paths,
            ppu_id=ppu_id,
            facility_id=facility_id,
            display_name=display_name,
            systemctl=systemctl,
            health_check=health_check,
            ensure_service_account=ensure_service_account,
        )
    except Exception:
        try:
            _core._restore_file(helper_snapshot)
            systemctl("daemon-reload")
        except Exception:
            pass
        raise
    finally:
        _core._write_text_atomic = original_writer
        _core.render_systemd_units = original_renderer

    try:
        systemctl("enable", "--now", RUNTIME_ACTIVATION_SERVICE)
    except Exception as exc:
        raise _core.Z2InstallerError(
            f"runtime activation helper failed to enable after release activation: {exc}"
        ) from exc

    site_state = evidence.get("site_desired_state")
    if isinstance(site_state, dict):
        site_state["runtime_apply_supported"] = True
        site_state["runtime_activation_socket"] = str(RUNTIME_ACTIVATION_SOCKET)
        site_state["server_control_socket"] = str(SERVER_CONTROL_SOCKET)
        site_state["upgrade_preserves_existing_config"] = True
    evidence["runtime_activation"] = {
        "service": RUNTIME_ACTIVATION_SERVICE,
        "scope": "restart-plasma-server-only",
        "server_authoritative_quiesce": True,
        "quiesce_ttl_bounded": True,
    }
    original_writer(
        paths.install_root / "last-install.json",
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
    )
    return evidence


_core.render_systemd_units = render_systemd_units
_core.install_release = install_release


def main(argv=None) -> int:
    return _core.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
