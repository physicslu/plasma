#!/usr/bin/env python3
"""ADR-0002 Phase 1 v25: K32L2B family operating VDD evidence (PARTIAL).

Only manufacturer IC Information: not Phase 2 programming, runtime power
qualification, source-PDF SHA256, PPU/PL, Site/Socket, Production, or selector.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

import nxp_phase1_kl25_k32l2a_io_v24 as prev
from nxp_phase1_information_v13 import blob

DIR = Path(__file__).resolve().parent
SOURCE = DIR / "nxp-12-k32l2b-working-vdd-partial-source-v25.csv"
LOCK = DIR / "nxp-phase1-k32l2b-vdd-source-lock-v25.json"
LEDGER = DIR / "nxp-501-phase1-k32l2b-vdd-partial-v25.csv"
METRICS = DIR / "nxp-phase1-k32l2b-vdd-partial-coverage-v25.json"
EXTRA = (
    "k32l2b_vdd_source_doc_v25",
    "k32l2b_vdd_source_uri_v25",
    "k32l2b_vdd_family_applicability_uri_v25",
    "k32l2b_vdd_source_revision_v25",
    "k32l2b_vdd_source_locator_v25",
    "k32l2b_vdd_evidence_scope_v25",
    "k32l2b_vdd_original_pdf_sha256_v25",
    "k32l2b_vdd_evidence_limit_v25",
    "k32l2b_vdd_access_state_v25",
)
SUFFIXES = ("VFM0A", "VFT0A", "VLH0A", "VMP0A")
EXPECTED = {
    f"K32L2B{family}{suffix}": flash
    for family, flash in (("11", 64), ("21", 128), ("31", 256))
    for suffix in SUFFIXES
}
VOLTAGE_NOTE = (
    "NXP family host-controller operating voltage evidence; exact 12 device "
    "applicability via K32-L2 supported-parts listing; per-ordering-code operating "
    "requirements NOT established; VDDA/VDDIO and physical/HIL remain UNKNOWN"
)


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError("NXP Phase1 v25: " + message)


@lru_cache(maxsize=1)
def baseline_rows() -> list[dict]:
    return prev.build()


def read_source() -> list[dict]:
    with SOURCE.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load() -> dict:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    require(lock["schema_version"] == 25 and lock["adr"] == "ADR-0002"
            and lock["phase"] == "IC_INFORMATION" and lock["manufacturer"] == "NXP",
            "invalid Phase 1 scope")
    require((lock["expected_501"], lock["expected_admitted"],
             lock["expected_research_only"], lock["exact_k32l2b_cohort"]) ==
            (501, 224, 277, 12), "unapproved identity/admission population")
    require(lock["expected_voltage_value"] == "1.71 to 3.6"
            and lock["expected_voltage_unit"] == "V"
            and lock["expected_voltage_state"] == "PARTIAL", "voltage confidence changed")
    require(lock["source"] == "AN12648"
            and lock["revision"] == "Rev 0 01/2020"
            and lock["source_url"] ==
            "https://www.nxp.com/docs/en/application-note/AN12648.pdf"
            and lock["official_documentation_applicability"] ==
            "https://www.nxp.com/products/K32-L2"
            and lock["source_locator"] ==
            "AN12648 section 3.1.1 Host controller, PDF physical page 4 of 9",
            "manufacturer primary document/revision/locator drift")
    require(lock["original_vendor_pdf_binary_archived"] is False
            and lock["original_vendor_pdf_sha256"] is None
            and lock["other_rail_inference"] == "NEVER_FROM_FAMILY_APPLICATION_NOTE"
            and lock["software_programming_support_granted"] is False
            and lock["production_or_hil_changed"] is False,
            "unsafe manufacturer source/operation or physical claim")
    require(blob(prev.LEDGER.read_bytes()) == lock["baseline_v24_git_blob"],
            "unapproved v24 source baseline")
    require(prev.LEDGER.read_bytes() ==
            prev.prev.dump(baseline_rows(), prev.prev.header(prev.prev.LEDGER) + list(prev.EXTRA)),
            "v24 501-row input is not independently replayable")
    require(blob(SOURCE.read_bytes()) == lock["evidence_v25_git_blob"],
            "unreviewed change to exact official-source observation rows")
    return lock


def build() -> list[dict]:
    lock = load()
    obs = read_source()
    require(len(obs) == len(EXPECTED) == 12
            and {r["icpn"] for r in obs} == set(EXPECTED),
            "12 K32L2B exact manufacturer identities missing or duplicated")
    by = {}
    groups = Counter()
    for ev in obs:
        icpn = ev["icpn"]
        require(ev["manufacturer_exact_identity_source_url"] ==
                f"https://www.nxp.com/part/{icpn}"
                and ev["official_family_doc_applicability_url"] ==
                lock["official_documentation_applicability"],
                "manufacturer exact-ICPN / official applicability mismatch")
        require(ev["family_voltage_source_id"] == lock["source"]
                and ev["family_voltage_source_url"] == lock["source_url"]
                and ev["family_voltage_revision"] == lock["revision"]
                and ev["source_locator"] == lock["source_locator"]
                and (ev["observed_min_v"], ev["observed_max_v"]) == ("1.71", "3.6"),
                "incorrect family evidence range, document revision or source page")
        require(ev["confidence"] == "PARTIAL"
                and ev["source_scope"] == "K32L2B_FAMILY_APPLICATION_NOTE"
                and ev["primary_k32l2b_datasheet_access"] ==
                    "ACCOUNT_REQUIRED_NOT_REVIEWED"
                and not ev["vendor_original_pdf_sha256"]
                and ev["source_note"] == VOLTAGE_NOTE,
                "family-level VDD was promoted to exact VERIFIED, or bogus PDF custody")
        require(int(ev["previous_flash_kb"]) == EXPECTED[icpn],
                "previous manufacturer flash geometry differs from group")
        groups[icpn[6:8]] += 1
        by[icpn] = ev
    require(dict(groups) == {"11": 4, "21": 4, "31": 4},
            "group breakdown changed")
    out = []
    matched = set()
    for old in baseline_rows():
        r = dict(old)
        for name in EXTRA:
            r[name] = ""
        ev = by.get(old["icpn"])
        if ev:
            require(old["identity_state"] == "ADMITTED"
                    and old["working_vdd_state"] == "UNKNOWN"
                    and not old["working_vdd"] and not old["working_vdd_unit"]
                    and old["manufacturer_uri"] ==
                        ev["manufacturer_exact_identity_source_url"]
                    and int(old["flash"].split()[0]) ==
                        int(ev["previous_flash_kb"]),
                    "existing exact admission, flash or VDD state mismatch: " +
                    old["icpn"])
            r["working_vdd"] = lock["expected_voltage_value"]
            r["working_vdd_unit"] = "V"
            r["working_vdd_state"] = "PARTIAL"
            r.update({
                "k32l2b_vdd_source_doc_v25": ev["family_voltage_source_id"],
                "k32l2b_vdd_source_uri_v25": ev["family_voltage_source_url"],
                "k32l2b_vdd_family_applicability_uri_v25":
                    ev["official_family_doc_applicability_url"],
                "k32l2b_vdd_source_revision_v25": ev["family_voltage_revision"],
                "k32l2b_vdd_source_locator_v25": ev["source_locator"],
                "k32l2b_vdd_evidence_scope_v25": ev["source_scope"],
                "k32l2b_vdd_original_pdf_sha256_v25": "NOT_ARCHIVED",
                "k32l2b_vdd_evidence_limit_v25": ev["source_note"],
                "k32l2b_vdd_access_state_v25":
                    ev["primary_k32l2b_datasheet_access"],
            })
            matched.add(old["icpn"])
        require(r["icpn"] == old["icpn"]
                and r["identity_state"] == old["identity_state"]
                and r["phase"] == "1"
                and all(r[k] == v for k, v in old.items()
                        if k not in ("working_vdd", "working_vdd_unit",
                                     "working_vdd_state")),
                "unrelated manufacturer field/admission changed")
        if not ev:
            require(all(r[k] == old[k] for k in
                        ("working_vdd", "working_vdd_unit", "working_vdd_state")),
                    "unreviewed ICPN voltage changed")
        out.append(r)
    require(len(out) == 501 and matched == set(EXPECTED)
            and sum(r["identity_state"] == "ADMITTED" for r in out) == 224
            and sum(r["identity_state"] == "RESEARCH_ONLY" for r in out) == 277,
            "unreviewed identity or research population changed")
    return out


def stats(rows: list[dict]) -> dict:
    lock = load()
    old = baseline_rows()
    return {
        "schema_version": 25,
        "adr": "ADR-0002",
        "phase": "IC_INFORMATION",
        "manufacturer": "NXP",
        "baseline_v24_git_blob": lock["baseline_v24_git_blob"],
        "evidence_v25_git_blob": lock["evidence_v25_git_blob"],
        "exact_k32l2b_family_voltage_rows": len(EXPECTED),
        "source_document": "AN12648 Rev 0 01/2020 §3.1.1",
        "evidence_state": "PARTIAL_NOT_EXACT_DATASHEET_OR_PER_MATERIAL",
        "before_admitted": prev.summary(
            [r for r in old if r["identity_state"] == "ADMITTED"]),
        "after_admitted": prev.summary(
            [r for r in rows if r["identity_state"] == "ADMITTED"]),
        "all_501": prev.summary(rows),
        "vendor_original_pdf_sha256_archived": False,
        "k32l2b_independent_vddio_or_vdda_qualified": False,
        "software_programming_qualified": None,
        "physical_hil_validated": None,
    }


def verify() -> None:
    rows = build()
    columns = prev.prev.header(prev.prev.LEDGER) + list(prev.EXTRA) + list(EXTRA)
    require(LEDGER.read_bytes() == prev.prev.dump(rows, columns),
            "v25 501-row source replay failed")
    require(json.loads(METRICS.read_text(encoding="utf-8")) == stats(rows),
            "v25 manufacturer information coverage metrics drift")
    coverage = stats(rows)["after_admitted"]["fields"]["working_vdd"]
    require(coverage == {
        "VERIFIED": 135, "PARTIAL": 39, "UNKNOWN": 50, "CONFLICT": 0
    }, "admitted VDD evidence states unexpectedly changed")
    print("NXP_PHASE1_V25_PASS admitted=224 K32L2B=12 VDD_PARTIAL=12 "
          "VDD_UNKNOWN=50 no exact-datasheet/VDDA/VDDIO/Programming/HIL promotion")


if __name__ == "__main__":
    verify()
