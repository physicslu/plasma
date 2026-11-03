#!/usr/bin/env python3
"""Explicit one-time provisioning of root-owned FPGA action source.

No FPGA, Runtime, service or DUT operation. A migration/install task must
be separately approved and its Z2 results recorded; factory refresh does NOT
silently activate this new privileged source or remove old recovery files.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import sys
from pathlib import Path

FACTORY_ROOT = Path("/opt/plasma/bootstrap")
DESTINATION = Path("/opt/plasma/privileged/fpga-root")


class ProvisionDenied(RuntimeError):
    pass


def _verifier(factory_root: Path):
    src = factory_root / "ppu_privileged_source.py"
    spec = importlib.util.spec_from_file_location("plasma_qualified_fpga_code", src)
    if spec is None or spec.loader is None:
        raise ProvisionDenied("PRIVILEGED_VERIFIER_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _trusted(path: Path, uid: int, *, folder: bool) -> None:
    info = path.lstat()
    if (not (stat.S_ISDIR(info.st_mode) if folder else stat.S_ISREG(info.st_mode))
            or info.st_uid != uid or info.st_mode & 0o022):
        raise ProvisionDenied("PRIVILEGED_PROVISION_SOURCE_UNTRUSTED")


def provision(
    factory_root: Path = FACTORY_ROOT,
    destination: Path = DESTINATION,
    *,
    _test_uid: int | None = None,
) -> dict:
    # Test-only UID override cannot be supplied through the CLI.
    uid = 0 if _test_uid is None else _test_uid
    if os.geteuid() != uid:
        raise ProvisionDenied("PRIVILEGED_PROVISION_ROOT_REQUIRED")
    if not factory_root.is_absolute() or not destination.is_absolute():
        raise ProvisionDenied("PRIVILEGED_PROVISION_PATH_INVALID")
    _trusted(factory_root, uid, folder=True)
    _trusted(factory_root / "ppu_privileged_source.py", uid, folder=False)
    verifier = _verifier(factory_root)
    if destination.exists() or destination.is_symlink():
        raise ProvisionDenied("PRIVILEGED_PROVISION_ALREADY_INSTALLED")
    parent = destination.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _trusted(parent, uid, folder=True)
    stage = parent / (".fpga-root-provision-%d" % os.getpid())
    if stage.exists() or stage.is_symlink():
        raise ProvisionDenied("PRIVILEGED_PROVISION_STAGE_COLLISION")
    stage.mkdir(mode=0o700)
    try:
        inventory = {}
        for rel in sorted(verifier.CODE_FILES):
            original = factory_root / rel
            if any((factory_root / Path(*Path(rel).parts[:i])).is_symlink()
                   for i in range(1, len(Path(rel).parts) + 1)):
                raise ProvisionDenied("PRIVILEGED_PROVISION_SYMLINK_DENIED")
            _trusted(original, uid, folder=False)
            target = stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
            target.chmod(0o644)
            inventory[rel] = hashlib.sha256(target.read_bytes()).hexdigest()
        (stage / verifier.MANIFEST).write_text(json.dumps({
            "schema": verifier.SCHEMA, "files": inventory,
        }, sort_keys=True) + "\n", encoding="utf-8")
        (stage / verifier.MANIFEST).chmod(0o600)
        # Verify the staged closure before atomic publication. Ancestors of
        # the new root are qualified by the root-only CLI at live execution.
        verifier.verify_source(stage, expected_uid=uid)
        os.rename(stage, destination)  # No replacement of an existing tree.
        return {"result": "PROVISIONED_NOT_EXECUTED",
                "source_root": str(destination),
                "code_files": len(inventory), "fpga_loaded": False}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main(argv: list[str]) -> int:
    if argv or os.geteuid() != 0:
        print("PRIVILEGED_PROVISION_ROOT_ONLY_NO_ARGS", file=sys.stderr)
        return 2
    try:
        print(json.dumps(provision(), sort_keys=True))
    except (OSError, ProvisionDenied, Exception) as exc:
        print(type(exc).__name__ + ":" + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
