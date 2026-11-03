#!/usr/bin/env python3
"""Stage C production integration: systemd / tmpfiles renderers.

Pure text renderers only. Nothing here installs or enables units, and the
existing Z2 installer does not reference this module yet (Z2 Gate step).

Identity model:
  plasma           Runtime (plasma-server.service, unchanged unit + drop-in)
  plasma-package   Package Actions (plasma-package@<job>.service)
  root             Site Worker (plasma-site-worker.service): Site admission +
                   PS-local OpenOCD need root; no MMIO in the Worker itself.

Sockets (AF_UNIX only, no TCP/HTTP):
  /run/plasma-site-worker/control.sock    root:plasma          0660
  /run/plasma-site-worker/transport.sock  root:plasma-package  0660
  /run/plasma-package-control/helper.sock root:plasma          0660 (fixed-purpose
                                           unit control; Runtime MainPID only)
  /run/plasma-server/control.sock         plasma 0600 (unchanged; the Package
                                           uid cannot connect)
"""
from __future__ import annotations

import sys

# The interpreter that renders these units is the Active Python Runtime (the
# installer runs under it); units therefore launch that same interpreter. A
# stable, atomically switched launcher path is a separate deployment change.
PYTHON = sys.executable
# Control plane ships in the factory Bootstrap kit (root-owned, code only;
# the Bootstrap credential lives in /var/lib/plasma-bootstrap, kept inaccessible).
RUNTIME_DIR = "/opt/plasma/bootstrap"
PACKAGE_USER = "plasma-package"
RUNTIME_USER = "plasma"
SPEC_DIR = "/run/plasma-package-specs"
WORKER_RUN = "/run/plasma-site-worker"

# Runtime-private resources the Package unit must never see (defence in depth
# on top of DAC: different uid, not in group plasma).
PACKAGE_INACCESSIBLE = (
    "/run/plasma-server", "/var/lib/plasma", "/var/lib/plasma-bootstrap",
    "/var/lib/plasma-privileged", "/var/lib/plasma-site-worker", "/etc/plasma",
    "/opt/plasma/privileged", "/run/plasma-z2-swd05",
    f"{WORKER_RUN}/control.sock", "/root",
)


def package_unit() -> str:
    return "\n".join([
        "[Unit]",
        "Description=PLASMA Package Action %i (non-root, fixed entry)",
        "",
        "[Service]",
        "Type=exec",
        f"User={PACKAGE_USER}",
        f"Group={PACKAGE_USER}",
        f"ExecStart={PYTHON} -I -B -S {RUNTIME_DIR}/ppu_package_entry.py %i",
        "RemainAfterExit=yes",
        "RuntimeDirectory=plasma-package/%i",
        "RuntimeDirectoryMode=0755",
        f"Environment=PLASMA_PACKAGE_SPEC_DIR={SPEC_DIR}",
        "Environment=PLASMA_PACKAGE_STAGED_ROOT=/opt/plasma/assets/staged",
        "UMask=0022",
        "NoNewPrivileges=yes",
        "CapabilityBoundingSet=",
        "AmbientCapabilities=",
        "PrivateDevices=yes",
        "PrivateNetwork=yes",
        "IPAddressDeny=any",
        "RestrictAddressFamilies=AF_UNIX",
        "ProtectSystem=strict",
        "ProtectHome=yes",
        "PrivateTmp=yes",
        "ProtectKernelTunables=yes",
        "ProtectKernelModules=yes",
        "ProtectKernelLogs=yes",
        "ProtectControlGroups=yes",
        "ProtectClock=yes",
        "ProtectHostname=yes",
        "ProtectProc=invisible",
        "RestrictNamespaces=yes",
        "LockPersonality=yes",
        "RestrictRealtime=yes",
        "RestrictSUIDSGID=yes",
        "SystemCallArchitectures=native",
        "SystemCallFilter=@system-service",
        "SystemCallFilter=~@privileged @mount @debug @module @raw-io @reboot @swap @obsolete @cpu-emulation @clock",
        "InaccessiblePaths=" + " ".join(f"-{p}" for p in PACKAGE_INACCESSIBLE),
        "KillMode=control-group",
        "TasksAccounting=yes",
        "TasksMax=64",
        "MemoryMax=512M",
        "LimitAS=512M",
        "LimitNOFILE=64",
        "LimitFSIZE=16M",
        "LimitCORE=0",
        "RuntimeMaxSec=3700",
        "",
    ])


def site_worker_unit() -> str:
    return "\n".join([
        "[Unit]",
        "Description=PLASMA Site Worker (single local hardware transport)",
        "After=local-fs.target",
        "",
        "[Service]",
        "Type=simple",
        "User=root",
        f"ExecStart={PYTHON} -I -B -S {RUNTIME_DIR}/ppu_site_worker_service.py",
        "RuntimeDirectory=plasma-site-worker",
        "RuntimeDirectoryMode=0755",
        "StateDirectory=plasma-site-worker",
        "StateDirectoryMode=0700",
        "UMask=0077",
        "NoNewPrivileges=yes",
        "PrivateNetwork=yes",
        "IPAddressDeny=any",
        "RestrictAddressFamilies=AF_UNIX",
        "ProtectSystem=strict",
        "ProtectHome=read-only",
        "PrivateTmp=yes",
        "ReadWritePaths=/run/plasma-z2-swd05 /run/lock",
        "ProtectKernelModules=yes",
        "ProtectControlGroups=yes",
        "ProtectClock=yes",
        "ProtectHostname=yes",
        "RestrictNamespaces=yes",
        "LockPersonality=yes",
        "RestrictSUIDSGID=yes",
        "Restart=on-failure",
        "RestartSec=5",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
    ])


PACKAGE_ACTIONS_CONFIG = "/etc/plasma/ppu-package-actions.json"


def runtime_dropin() -> str:
    """plasma-server.service.d/50-package-actions.conf (existing unit unchanged)."""
    return "\n".join([
        "[Unit]",
        "Wants=plasma-site-worker.service plasma-package-control.service",
        "After=plasma-site-worker.service plasma-package-control.service",
        "",
        "[Service]",
        f"ReadWritePaths={SPEC_DIR}",
        f"Environment=PLASMA_PACKAGE_ACTIONS_CONFIG={PACKAGE_ACTIONS_CONFIG}",
        "",
    ])


def package_actions_config(*, site_worker: bool = True) -> str:
    """/etc/plasma/ppu-package-actions.json (root:plasma 0640)."""
    import json
    return json.dumps({
        "schema": "plasma.ppu.package-actions-config.v1",
        "control_plane": RUNTIME_DIR,
        "product_root": "/opt/plasma",
        "state_root": "/var/lib/plasma/package-actions",
        "python": PYTHON,
        "package_user": PACKAGE_USER,
        "helper_socket": "/run/plasma-package-control/helper.sock",
        "site_worker_control_socket": f"{WORKER_RUN}/control.sock" if site_worker else None,
    }, indent=1, sort_keys=True) + "\n"


def tmpfiles() -> str:
    """/etc/tmpfiles.d/plasma-package.conf: Runtime-owned, world-readable spec dir."""
    return (f"d {SPEC_DIR} 0755 {RUNTIME_USER} {RUNTIME_USER} -\n"
            "d /run/plasma-package 0755 root root -\n")


def package_control_helper_unit() -> str:
    """Fixed-purpose root helper (replaces the rejected polkit rule: Z2 runs
    polkit 0.105, which cannot restrict manage-units by unit name).

    Same shape as the existing plasma-runtime-activation helper: root, group
    plasma for the socket directory, AF_UNIX only, no network, read-only FS.
    """
    return "\n".join([
        "[Unit]",
        "Description=PLASMA Package unit control helper (plasma-package@ only)",
        "Before=plasma-server.service",
        "",
        "[Service]",
        "Type=simple",
        "User=root",
        f"Group={RUNTIME_USER}",
        f"ExecStart={PYTHON} -I -B -S {RUNTIME_DIR}/ppu_package_unit_helper.py",
        "RuntimeDirectory=plasma-package-control",
        "RuntimeDirectoryMode=0750",
        "UMask=0077",
        "NoNewPrivileges=yes",
        "PrivateNetwork=yes",
        "IPAddressDeny=any",
        "RestrictAddressFamilies=AF_UNIX",
        "ProtectSystem=strict",
        "ProtectHome=yes",
        "PrivateTmp=yes",
        "PrivateDevices=yes",
        "ProtectKernelTunables=yes",
        "ProtectKernelModules=yes",
        "ProtectKernelLogs=yes",
        "ProtectClock=yes",
        "ProtectHostname=yes",
        "RestrictNamespaces=yes",
        "LockPersonality=yes",
        "RestrictSUIDSGID=yes",
        "Restart=on-failure",
        "RestartSec=2",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
    ])


def render_all() -> dict[str, str]:
    return {
        "/etc/systemd/system/plasma-package@.service": package_unit(),
        "/etc/systemd/system/plasma-site-worker.service": site_worker_unit(),
        "/etc/systemd/system/plasma-server.service.d/50-package-actions.conf": runtime_dropin(),
        "/etc/tmpfiles.d/plasma-package.conf": tmpfiles(),
        PACKAGE_ACTIONS_CONFIG: package_actions_config(),
        "/etc/systemd/system/plasma-package-control.service": package_control_helper_unit(),
    }
