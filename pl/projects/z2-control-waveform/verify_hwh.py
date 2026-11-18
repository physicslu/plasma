"""Project-specific control/loopback HWH checks for the generic host build."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path


def verify_artifacts(*, hwh: Path, bit: Path, reports: Path,
                     source_sha: str, build: Path) -> dict:
    spec = importlib.util.spec_from_file_location("z2_control_artifact",
                                                  Path(__file__).with_name("artifact.py"))
    assert spec is not None and spec.loader is not None
    artifact = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(artifact)
    mapping = artifact.verify_hwh(hwh)
    exported = (build / "generated/axi-address-map.txt").read_text().splitlines()
    if len(exported) != len(artifact.MAP):
        raise ValueError("Incomplete Tcl address map")
    seen = set()
    for line in exported:
        instance, base, size = line.split()
        if instance in seen or instance not in artifact.MAP or \
                int(base, 0) != artifact.MAP[instance] or int(size, 0) != 4096:
            raise ValueError("Tcl/HWH address mismatch")
        seen.add(instance)
    if seen != set(artifact.MAP):
        raise ValueError("Incomplete Tcl address map")
    files = {name: reports / name for name in
             ("timing_summary.rpt", "drc.rpt", "methodology.rpt", "utilization.rpt")}
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    return {"source_sha": source_sha, "bit_sha256": digest(bit),
            "hwh_sha256": digest(hwh),
            "report_sha256": {name: digest(path) for name, path in files.items()},
            "map": mapping}
