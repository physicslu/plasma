#!/usr/bin/env python3
"""Permanent offline hard-lock validator for STM32L1 requalification."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stm32l1_requalification import (
    DEFAULT_ORDERING,
    DEFAULT_OUTPUT,
    DEFAULT_PROVENANCE,
    DEFAULT_SUMMARY,
    DEFAULT_TARGETS,
    FROZEN_PRODUCTION_PRESTATE,
    build_requalification_result,
)

HERE = Path(__file__).resolve().parent
EVIDENCE_DIR = DEFAULT_SUMMARY.parent / "evidence"
EXPECTED_BLOBS = {
    DEFAULT_SUMMARY: "51aa041be6749e7f094870a79cea6994b23a4057",
    DEFAULT_TARGETS: "b8499df773d6b850565646670dd2fc780cc63596",
    DEFAULT_PROVENANCE: "09ed0aaafee0b5b4f6103a6e786535d72cdb7807",
    DEFAULT_ORDERING: "72e14cf7ae86ffb30282986712c9bbbbdf0650bc",
    FROZEN_PRODUCTION_PRESTATE: "477f0fa4f507e01e420df47a49384d3db7928ba7",
    DEFAULT_OUTPUT: "2c90037444efddc85e200b45631ec6ec762eb901",
    EVIDENCE_DIR / "STM32L100C6-generation-a.json": "29885348d9828849c2e5df6188b7240b0f489f88",
    EVIDENCE_DIR / "STM32L100C6-legacy.json": "67d2dd62aebfb6c845a04c21ad58e8ba7f2a98fc",
    EVIDENCE_DIR / "STM32L151C6-generation-a.json": "66e04a54ba46983096cb722cd36d414109fa9d36",
    EVIDENCE_DIR / "STM32L151C6-legacy.json": "6c6d8897b172f43db24dddf16fe43e8e6b5d4fe0",
    EVIDENCE_DIR / "STM32L152C6-generation-a.json": "b3c22e6a016e49825bd7cfe886fe074a934adf58",
    EVIDENCE_DIR / "STM32L152C6-legacy.json": "72046b960562b06e2a399d13d454a85a7aebf4a3",
    EVIDENCE_DIR / "STM32L162QC-current.json": "d8c9263d835c1d8ab660a3c0e9ad47abc6651c18",
}


def req(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data, usedforsecurity=False).hexdigest()


def main() -> int:
    for path, expected in EXPECTED_BLOBS.items():
        req(path.is_file(), f"missing hard-locked file: {path.name}")
        observed = git_blob_sha(path)
        req(observed == expected, f"Git blob drift: {path.name}: {observed} != {expected}")

    frozen = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
    generated = build_requalification_result()
    req(generated == frozen, "frozen STM32L1 requalification result no longer replays")

    summary = json.loads(DEFAULT_SUMMARY.read_text(encoding="utf-8"))
    retained = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(EVIDENCE_DIR.glob("*.json"))
    }
    req(len(retained) == 7, "expected exactly seven retained STM32L1 evidence files")
    for result in summary["results"]:
        target_id = result["target_id"]
        req(target_id in retained, f"missing retained evidence for {target_id}")
        req(retained[target_id] == result["evidence"], f"retained evidence differs from live summary for {target_id}")

    prestate = json.loads(FROZEN_PRODUCTION_PRESTATE.read_text(encoding="utf-8"))
    sources = prestate["sources"]
    req(sum(source["row_count"] for source in sources) == 1718, "frozen Production exact count drifted")
    req(len(sources) == 12, "frozen Production family count drifted")
    req(all(source["family"] != "STM32L1" for source in sources), "STM32L1 unexpectedly exists in frozen Production")
    req(next(source["row_count"] for source in sources if source["family"] == "STM32L4") == 446, "frozen STM32L4 state drifted")

    provenance = json.loads(DEFAULT_PROVENANCE.read_text(encoding="utf-8"))
    req(provenance["artifact_digest"] == "sha256:b20ffce5cf4ab540fbed1458719c544ba06cfceb8f0ba10829034b76c0dbcf5f", "artifact digest drifted")
    req(provenance["workflow_run_id"] == 34749400091, "workflow run provenance drifted")
    req(provenance["executed_git_sha"] == "b7b9ce7b7e808eae765f964c0cd6e2799887a456", "executed Git SHA drifted")

    req(frozen["status"] == "eligible_for_next_research_gate", "requalification status drifted")
    req(frozen["active_exact_icpn_evidence_count"] == 9, "Active exact evidence count drifted")
    req(frozen["non_active_exact_icpn_evidence_count"] == 8, "non-Active exact evidence count drifted")
    req(frozen["selected_next_research_family"] is None, "requalification must not select a family")
    req(all(value is False for value in frozen["claims"].values()), "requalification claims escaped fail-closed state")
    print("STM32L1 lifecycle requalification hard-lock: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
