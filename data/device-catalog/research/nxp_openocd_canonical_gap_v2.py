#!/usr/bin/env python3
"""NXP OpenOCD -> Canonical Catalog bounded gap, no promotion or hardware.

Frozen sources: v10 501-row research, v13 identity, production manifest,
canonical ProgrammingQualificationRegistry and prior pinned reverse-source v1.
Do not equate historical P0/P1/P2 priorities with Catalog L0/L1/L2/L3.
"""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "data/device-catalog/research"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
PINNED = {
    "nxp-501-adr0002-core-transport-qualification-v10.csv": "9f0397fe6062356fd04cd5eb73133969e75d9bfb",
    "nxp-501-phase1-ic-information-v13.csv": "4a0fbad8fa5f57580ba28e92f71b0793e12faf07",
    "nxp-openocd-reverse-coverage-v1.json": "a8eeafc1f20abbc649030d38e345c695446d728d",
}
OPENOCD_COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
FAMILIES = {"KL25": 12, "MCX": 196, "K32L2": 16,
            "LPC11U6X": 8, "LPC81X": 8, "LPC11U2X": 1}


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError("NXP canonical gap: " + reason)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def checked_bytes(path: Path, expected_blob: str) -> bytes:
    contents = path.read_bytes()
    require(git_blob(contents) == expected_blob, "pinned source drift: " + path.name)
    return contents


def rows(content: bytes, *, expected: int, label: str) -> list[dict[str, str]]:
    import io
    result = list(csv.DictReader(io.StringIO(content.decode("utf-8"))))
    require(len(result) == expected, label + " row count drift")
    identifiers = [row["icpn"] for row in result]
    require(len(set(identifiers)) == expected and all(identifiers),
            label + " duplicate/empty exact ICPN")
    return result


def build() -> dict:
    release = json.loads(checked_bytes(
        ROOT / "release/openocd.json", "08c884b1bf6f5999c6d34c090992a8b59d85971d"
    ))
    require(release["version"] == "0.12.0"
            and release["source_commit"] == OPENOCD_COMMIT
            and release["hardware_runtime_ready"] is False, "OpenOCD provider changed")
    raw = {
        name: checked_bytes(RESEARCH / name, sha)
        for name, sha in PINNED.items()
    }
    historical = rows(raw["nxp-501-adr0002-core-transport-qualification-v10.csv"],
                      expected=501, label="historic v10")
    identity = rows(raw["nxp-501-phase1-ic-information-v13.csv"],
                    expected=501, label="historic v13")
    v10 = {r["icpn"]: r for r in historical}
    v13 = {r["icpn"]: r for r in identity}
    require(set(v10) == set(v13), "historical source identity mismatch")
    require(Counter(r["research_priority"] for r in historical) ==
            {"P0": 27, "P1": 38, "P2": 436}, "historical priority drift")
    require(Counter(r["identity_state"] for r in identity) ==
            {"ADMITTED": 224, "RESEARCH_ONLY": 277}, "historical admission drift")
    reverse = json.loads(raw["nxp-openocd-reverse-coverage-v1.json"])
    require(reverse["openocd_commit"] == OPENOCD_COMMIT
            and reverse["existing_nxp_exact_reviewed"] == 501
            and reverse["new_p0_exact_attested_by_reverse_check"] == 0
            and reverse["nxp_entire_active_portfolio_complete"] is False,
            "historic reverse source scope drift")

    manifest = json.loads(PRODUCTION.read_text(encoding="utf-8"))
    sources = [r for r in manifest["sources"] if r["manufacturer"] == "NXP"]
    require(len(sources) == 6 and
            {s["family"]: s["row_count"] for s in sources} == FAMILIES,
            "NXP production source manifest changed")
    production = {}
    family_rows = {}
    for source in sources:
        path = (PRODUCTION.parent / source["path"]).resolve(strict=True)
        require(path.is_relative_to(RESEARCH.resolve()), "source escaped Research")
        blob = path.read_bytes()
        require(git_blob(blob) == source["git_blob_sha"]
                and hashlib.sha256(blob).hexdigest() == source["sha256"],
                "production source hash drift: " + source["family"])
        records = rows(blob, expected=source["row_count"], label=source["family"])
        family_rows[source["family"]] = records
        for row in records:
            require(row["manufacturer"] == "NXP"
                    and row["family"] == source["family"]
                    and row["icpn"] not in production,
                    "production ICPN or family collision")
            production[row["icpn"]] = row
    require(len(production) == 241, "NXP production denominator drift")
    shared = set(production) & set(v10)
    historic_only = set(v10) - set(production)
    new_prod = set(production) - set(v10)
    require(len(shared) == 224 and len(historic_only) == 277
            and len(new_prod) == 17, "old/new Canonical identity intersection changed")
    require(all(v13[x]["identity_state"] == "ADMITTED" for x in shared)
            and all(v13[x]["identity_state"] == "RESEARCH_ONLY" for x in historic_only),
            "historic identity/admission state mismatch")

    old_only_priority = Counter(v10[x]["research_priority"] for x in historic_only)
    require(old_only_priority == {"P0": 15, "P1": 22, "P2": 240},
            "historical-only priority classification drift")
    require(sum(x.startswith(("LPC844", "LPC845")) for x in historic_only
                if v10[x]["research_priority"] == "P0") == 15,
            "LPC84x historical P0 gap changed")
    require(sum(x.startswith("K32L2") for x in historic_only
                if v10[x]["research_priority"] == "P1") == 4
            and sum(x.startswith(("LPC802", "LPC804")) for x in historic_only
                    if v10[x]["research_priority"] == "P1") == 18,
            "historical P1 split changed")
    require(all(x in shared and v10[x]["research_priority"] == "P1"
                for x in (r["icpn"] for r in family_rows["K32L2"])),
            "K32L2 exact identity link drift")

    # Canonical registry is the only Catalog level authority.
    sys.path.insert(0, str(ROOT / "software/python"))
    from plasma_web.catalog_promotion_framework import get_default_catalog_promotion_framework
    report = get_default_catalog_promotion_framework().report
    vendor = next(x for x in report["manufacturers"] if x["manufacturer"] == "NXP")
    levels = vendor["catalog_level_counts"]
    require(levels == {"0": 212, "1": 29, "2": 0, "3": 0},
            "Canonical NXP levels drifted")
    require(vendor["discovered_exact_icpns"] == 241 and
            vendor["job_selectable_exact_icpns"] == 0 and
            report["execution_authorized_by_framework"] is False,
            "canonical qualification entitlement drift")
    # A source-backed family cfg is admissible at L1, not an executable profile.
    require({name for name in new_prod if name.startswith("LPC")} == new_prod,
            "17 newer LPC production identities changed")
    return {
        "scope": "BOUNDED_501_V10_TO_241_CANONICAL_NO_PROMOTION",
        "openocd": {"version": release["version"], "commit": OPENOCD_COMMIT},
        "historical_501": {"total": len(v10), "priority": {"P0": 27, "P1": 38, "P2": 436}},
        "canonical": {"total": 241, "catalog_levels": levels},
        "identity_join": {"in_both": len(shared), "historic_only": len(historic_only),
                          "newer_canonical_lpc": len(new_prod)},
        "historic_only_priority": dict(sorted(old_only_priority.items())),
        "historic_only_priority_detail": {
            "P0_LPC844_LPC845": 15, "P1_K32L2_not_admitted": 4,
            "P1_LPC802_LPC804_not_admitted": 18, "P2_other": 240,
        },
        "current_family_counts": {name: len(rows) for name, rows in sorted(family_rows.items())},
        "current_l1_families": {"KL25": 12, "LPC11U6X": 8, "LPC81X": 8,
                               "LPC11U2X": 1},
        "current_l0_families": {"MCX": 196, "K32L2": 16},
        "promotion_authorized": False,
        "hardware_executed": False,
        "unbounded_nxp_portfolio_coverage": None,
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, ensure_ascii=False, sort_keys=True))
