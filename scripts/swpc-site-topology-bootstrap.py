#!/usr/bin/env python3
"""One-time empty-topology bootstrap for the SWPC PPU surrogate.

This tool mutates only the canonical ``sites`` collection from an explicit empty
list to the fixed one-based SITE1..SITE8 topology.  It deliberately does not
restart Plasma services or activate Desired configuration.
"""

from __future__ import annotations

import argparse
import copy
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

import yaml


SITE_COUNT = 8


class BootstrapError(RuntimeError):
    """Raised when the bounded topology bootstrap contract is not satisfied."""


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise BootstrapError(f"cannot load canonical PPU configuration: {path}") from exc
    if not isinstance(raw, dict):
        raise BootstrapError("canonical PPU configuration root must be a mapping")
    return raw


def _build_candidate(raw: dict[str, Any]) -> dict[str, Any]:
    if "sites" not in raw:
        raise BootstrapError("canonical PPU configuration must explicitly contain sites: []")
    sites = raw["sites"]
    if not isinstance(sites, list):
        raise BootstrapError("canonical sites field must be a list")
    if sites:
        raise BootstrapError("refusing bootstrap: canonical Site topology is already non-empty")

    server = raw.get("server")
    if not isinstance(server, dict):
        raise BootstrapError("canonical PPU configuration must contain a server mapping")
    maximum = server.get("max_supported_sites")
    if isinstance(maximum, bool) or maximum != SITE_COUNT:
        raise BootstrapError(
            f"SWPC topology bootstrap requires server.max_supported_sites == {SITE_COUNT}"
        )

    candidate = copy.deepcopy(raw)
    candidate["sites"] = [
        {"id": site_id, "enabled": False, "interface": "mock"}
        for site_id in range(1, SITE_COUNT + 1)
    ]
    return candidate


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    directory_fd = os.open(path, flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def bootstrap_sites(config_path: str | Path) -> None:
    path = Path(config_path)
    if not path.is_absolute():
        raise BootstrapError("canonical PPU configuration path must be absolute")

    try:
        original_stat = path.lstat()
    except OSError as exc:
        raise BootstrapError(f"canonical PPU configuration is unavailable: {path}") from exc
    if stat.S_ISLNK(original_stat.st_mode) or not stat.S_ISREG(original_stat.st_mode):
        raise BootstrapError("canonical PPU configuration must be a regular non-symlink file")

    original = _load_yaml(path)
    candidate = _build_candidate(original)

    temp_name: str | None = None
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.bootstrap.", suffix=".tmp", dir=path.parent
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(candidate, handle, sort_keys=False, default_flow_style=False)
            handle.flush()
            os.fsync(handle.fileno())

        mode = stat.S_IMODE(original_stat.st_mode)
        os.chmod(temp_name, mode)
        temp_stat = os.stat(temp_name)
        if temp_stat.st_uid != original_stat.st_uid or temp_stat.st_gid != original_stat.st_gid:
            os.chown(temp_name, original_stat.st_uid, original_stat.st_gid)

        round_trip = _load_yaml(Path(temp_name))
        if round_trip != candidate:
            raise BootstrapError("temporary topology candidate failed YAML round-trip validation")

        sites = round_trip.get("sites")
        if not isinstance(sites, list) or [site.get("id") for site in sites] != list(
            range(1, SITE_COUNT + 1)
        ):
            raise BootstrapError("temporary topology candidate does not contain SITE1..SITE8")
        if any(site.get("enabled") is not False or site.get("interface") != "mock" for site in sites):
            raise BootstrapError("temporary topology candidate is not disabled mock topology")

        os.replace(temp_name, path)
        temp_name = None
        _fsync_directory(path.parent)
    except BootstrapError:
        raise
    except OSError as exc:
        raise BootstrapError(f"atomic topology bootstrap failed for {path}") from exc
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap an explicit empty SWPC topology to disabled mock SITE1..SITE8."
    )
    parser.add_argument("--config", default="/etc/plasma/ppu.yaml")
    args = parser.parse_args()

    try:
        bootstrap_sites(args.config)
    except BootstrapError as exc:
        parser.exit(1, f"swpc-site-topology-bootstrap: ERROR: {exc}\n")
    print(
        "swpc-site-topology-bootstrap: bootstrapped SITE1..SITE8 as disabled mock Desired topology; "
        "runtime activation was not performed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
