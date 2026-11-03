#!/usr/bin/env python3
"""Stage C production integration: systemd / polkit / tmpfiles renderers.

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
  /run/plasma-server/control.sock         plasma 0600 (unchanged; the Package
                                           uid cannot connect)
"""
from __future__ import annotations

PYTHON = "/opt/plasma/python/3.12.13/bin/python3"
RUNTIME_DIR = "/opt/plasma/runtime"
PACKAGE_USER = "plasma-package"
RUNTIME_USER = "plasma"
SPEC_DIR = "/run/plasma-package-specs"
WORKER_RUN = "/run/plasma-site-worker"

# Runtime-private resources the Package unit must never see (defence in depth
# on top of DAC: different uid, not in group plasma).
PACKAGE_INACCESSIBLE = (
    "/run/plasma-server", "/var/lib/plasma", "/var/lib/plasma-bootstrap",
    "/var/lib/plasma-privileged", "/var/lib/plasma-site-worker", "/etc/plasma",
    "/opt/plasma/privileged", "/opt/plasma/bootstrap", "/run/plasma-z2-swd05",
    f"{WORKER_RUN}/control.sock", "/root",
)


def package_unit() -> str:
    return "\n".join([
        "[Unit]",
        "Description=PLASMA Package Action %i (non-root, fixed entry)",
        "Documentation=docs/deployment/ppu-common-asset-execution-gate1.md",
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


def runtime_dropin() -> str:
    """plasma-server.service.d/50-package-actions.conf (existing unit unchanged)."""
    return "\n".join([
        "[Unit]",
        "Wants=plasma-site-worker.service",
        "After=plasma-site-worker.service",
        "",
        "[Service]",
        f"ReadWritePaths={SPEC_DIR}",
        "",
    ])


def tmpfiles() -> str:
    """/etc/tmpfiles.d/plasma-package.conf: Runtime-owned, world-readable spec dir."""
    return (f"d {SPEC_DIR} 0755 {RUNTIME_USER} {RUNTIME_USER} -\n"
            "d /run/plasma-package 0755 root root -\n")


def polkit_rule() -> str:
    """Allow ONLY the Runtime uid to start/stop/kill the fixed Package template.

    Requires polkit with JavaScript rules (>= 0.106). On polkit 0.105 (.pkla)
    a unit-name restriction is impossible: do NOT grant manage-units there.
    """
    return "\n".join([
        "// PLASMA: Runtime may manage only plasma-package@<32 hex>.service instances.",
        "polkit.addRule(function(action, subject) {",
        '    if (action.id !== "org.freedesktop.systemd1.manage-units") { return polkit.Result.NOT_HANDLED; }',
        f'    if (subject.user !== "{RUNTIME_USER}") {{ return polkit.Result.NOT_HANDLED; }}',
        '    var unit = action.lookup("unit");',
        '    var verb = action.lookup("verb");',
        '    if (unit && /^plasma-package@[0-9a-f]{32}\\.service$/.test(unit) &&',
        '        (verb === "start" || verb === "stop" || verb === "kill")) {',
        "        return polkit.Result.YES;",
        "    }",
        "    return polkit.Result.NOT_HANDLED;",
        "});",
        "",
    ])


def render_all() -> dict[str, str]:
    return {
        "/etc/systemd/system/plasma-package@.service": package_unit(),
        "/etc/systemd/system/plasma-site-worker.service": site_worker_unit(),
        "/etc/systemd/system/plasma-server.service.d/50-package-actions.conf": runtime_dropin(),
        "/etc/tmpfiles.d/plasma-package.conf": tmpfiles(),
        "/etc/polkit-1/rules.d/50-plasma-package.rules": polkit_rule(),
    }
