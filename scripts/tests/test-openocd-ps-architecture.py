#!/usr/bin/env python3
"""Host-only CI guard for the documented SWPC / Z2 PS OpenOCD boundary.

Check the actual bounded WordPort executable and Z2 PS runtime installer,
not merely the presence of architecture prose. No network, hardware or sudo.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ARCH = "docs/architecture/ic-support-openocd-plan-executor.md"
AGENTS = "AGENTS.md"
BRIDGE = "scripts/bluepill-wordport-session.py"
INSTALLER = "scripts/plasmactl-z2-ps"
WORKFLOW = ".github/workflows/repository-contracts.yml"


def reject(reason: str) -> None:
    raise ValueError("OPENOCD_PS_ARCHITECTURE_DRIFT: " + reason)


def validate(architecture: str, agents: str, bridge: str,
             installer: str, workflow: str) -> None:
    # The named architecture document, not a new per-component policy file,
    # remains the human-readable system-of-record for process placement.
    required_arch = (
        "SWPC: Web / Controller / BFF",
        "Z2 PS: OpenOCD -> PS-local UNIX WordPort/Remote Bitbang bridge -> MMIO",
        "Z2 PL: FPGA SWD engine",
        "SWPC OpenOCD is permitted for offline build",
        "must not host live OpenOCD",
    )
    for token in required_arch:
        if token not in architecture:
            reject("architecture document no longer pins " + token)

    if "**Hardware execution boundary (normative; CI-enforced):**" not in agents:
        reject("AGENTS.md missing binding execution-zone contract")
    if "**SWPC runs Web / Controller / BFF**" not in agents:
        reject("SWPC application role drift")
    if "**Z2 PS runs the embedded Linux programming runtime" not in agents:
        reject("Z2 PS programmer-engine ownership drift")

    # Parse executable Python, inspect the actual run() call tree, and reject
    # any replacement of the local native MMIO/UNIX boundary with remote ingress.
    try:
        module = ast.parse(bridge, filename=BRIDGE)
    except SyntaxError as exc:
        reject("invalid PS bridge Python: " + str(exc))
    docstring = ast.get_docstring(module) or ""
    if ("OpenOCD must execute on\nZ2 PS" not in docstring or
            "PS-local UNIX socket" not in docstring):
        reject("WordPort bridge no longer declares PS-local OpenOCD")
    if ("pinned OpenOCD on SWPC" in docstring or
            "over enrolled SSH" in docstring or
            "cross-host Remote Bitbang forwarding" not in docstring):
        reject("SWPC remote-bitbang execution/tunnel resurrected")

    run = next(
        (node for node in module.body
         if isinstance(node, ast.FunctionDef) and node.name == "run"), None
    )
    if run is None:
        reject("real WordPort run() missing")

    call_names: set[str] = set()
    for node in ast.walk(run):
        if not isinstance(node, ast.Call):
            continue
        try:
            call_names.add(ast.unparse(node.func))
        except ValueError:
            reject("cannot inspect bridge execution call")
    for call in ("root.native_runtime_preflight", "root.live_program_session_report",
                 "LinuxMMIO", "mmio.claim_site", "serve_local_unix_once"):
        if call not in call_names:
            reject("PS-native WordPort call missing: " + call)
    # A remote-host process or SSH command in the physical WordPort entrypoint
    # would turn a PS-local transport into an SWPC programmer backend.
    forbidden_names = ("paramiko", "fabric", "asyncssh", "ssh", "sshpass")
    for node in ast.walk(module):
        if isinstance(node, ast.Import) and any(
                alias.name.split(".")[0] in forbidden_names for alias in node.names):
            reject("SSH client imported into PS WordPort entrypoint")
        if isinstance(node, ast.ImportFrom) and (
                node.module or "").split(".")[0] in forbidden_names:
            reject("SSH module imported into PS WordPort entrypoint")

    # A SWPC-only qualified OpenOCD binary is not interchangeable with the
    # Z2 installer provisioned ARMv7 OpenOCD process.
    required_installer = (
        '--openocd-artifact PATH',
        'install_or_reuse_openocd() {',
        'installing verified Plasma-owned ARMv7 OpenOCD runtime',
        'programming-engines/openocd/*/bin/openocd',
    )
    for token in required_installer:
        if token not in installer:
            reject("Z2 PS ARMv7 runtime installation path missing: " + token)

    # The ordinary Repository contracts job must execute this guard on BOTH
    # architecture documentation and actual bridge source edits, on PR and main.
    if workflow.count('      - "scripts/bluepill-wordport-session.py"') != 2:
        reject("CI must trigger on bridge changes for push and pull_request")
    if workflow.count('      - "scripts/tests/test-openocd-ps-architecture.py"') != 2:
        reject("CI must trigger on architecture guard changes for push and pull_request")
    if workflow.count('      - "scripts/plasmactl-z2-ps"') != 2:
        reject("CI must trigger on Z2 OpenOCD installer changes for push and pull_request")
    if "run: python scripts/tests/test-openocd-ps-architecture.py" not in workflow:
        reject("repository-contracts CI is not executing the architecture guard")


def self_test(parts: dict[str, str]) -> None:
    keys = ("architecture", "agents", "bridge", "installer", "workflow")
    originals = [parts[k] for k in keys]
    validate(*originals)
    mutations = (
        ("architecture", "Z2 PS: OpenOCD", "SWPC: OpenOCD"),
        ("agents", "**SWPC runs Web / Controller / BFF**", "**SWPC runs OpenOCD**"),
        ("bridge", "Z2 PS and connect", "SWPC and connect"),
        ("bridge", "root.native_runtime_preflight()", "pass"),
        ("bridge", "root.live_program_session_report(port, release)", "pass"),
        ("bridge", "serve_local_unix_once(args.socket", "serve_remote_unix_once(args.socket"),
        ("installer", "install_or_reuse_openocd()", "install_not_available()"),
        ("workflow", "run: python scripts/tests/test-openocd-ps-architecture.py",
         "run: echo no-architecture-guard"),
    )
    for k, needle, replacement in mutations:
        if needle not in parts[k]:
            reject("negative control fixture no longer matches " + k + ": " + needle)
        changed = dict(parts)
        changed[k] = changed[k].replace(needle, replacement, 1)
        try:
            validate(*(changed[key] for key in keys))
        except ValueError as err:
            if not str(err).startswith("OPENOCD_PS_ARCHITECTURE_DRIFT: "):
                raise
        else:
            reject("negative control was not rejected: " + k + ": " + needle)


def main() -> int:
    paths = {"architecture": ARCH, "agents": AGENTS, "bridge": BRIDGE,
             "installer": INSTALLER, "workflow": WORKFLOW}
    try:
        parts = {key: (ROOT / path).read_text(encoding="utf-8")
                 for key, path in paths.items()}
        validate(*(parts[k] for k in paths))
        if "--self-test" in sys.argv[1:]:
            self_test(parts)
    except (OSError, ValueError) as exc:
        print("OpenOCD PS architecture: FAIL:", exc, file=sys.stderr)
        return 1
    print("OpenOCD PS architecture: PASS (docs ↔ PS WordPort ↔ installer ↔ CI, with negative controls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
