"""Project-specific Identity HWH checks for the generic host build."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path


def verify_artifacts(*, hwh: Path, bit: Path, reports: Path,
                     source_sha: str, build: Path) -> dict:
    spec = importlib.util.spec_from_file_location("z2_identity_artifact",
                                                  Path(__file__).with_name("artifact.py"))
    assert spec is not None and spec.loader is not None
    artifact = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(artifact)
    base = int((build / "generated/identity-axi-base.txt").read_text().strip(), 0)
    if base != 0x40000000:
        raise ValueError("Identity base mismatch")
    artifact.verify_hwh(hwh, base)
    files = {name: reports / name for name in
             ("timing_summary.rpt", "drc.rpt", "methodology.rpt", "utilization.rpt")}
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    return {"source_sha": source_sha, "bit_sha256": digest(bit),
            "hwh_sha256": digest(hwh),
            "report_sha256": {name: digest(path) for name, path in files.items()},
            "map": {"identity_axi_base": f"0x{base:08X}",
                    "external_pl_io": False}}
