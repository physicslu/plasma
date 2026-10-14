#!/usr/bin/env python3
"""ADR-0002 NXP Phase 1 v24: KL25/K32L2A GPIO VDD-reference, PARTIAL not proven VDDIO."""
import csv
import json
from functools import lru_cache
from collections import Counter
from pathlib import Path

import nxp_phase1_mcxa_rails_v23 as prev
from nxp_phase1_information_v13 import blob

DIR = Path(__file__).resolve().parent
SOURCE = DIR / "nxp-16-kl25-k32l2a-io-reference-source-v24.csv"
LOCK = DIR / "nxp-phase1-kl25-k32l2a-io-lock-v24.json"
LEDGER = DIR / "nxp-501-phase1-kl25-k32l2a-io-v24.csv"
METRICS = DIR / "nxp-phase1-kl25-k32l2a-io-coverage-v24.json"
EXTRA = (
    "io_reference_source_doc_v24", "io_reference_source_uri_v24",
    "io_reference_source_revision_v24", "io_reference_source_locator_v24",
    "io_reference_inference_limit_v24", "io_reference_pdf_sha256_v24",
)

@lru_cache(maxsize=1)
def baseline_rows():
    """Source-locked v23 generator is pure; replay it once per validation process."""
    return prev.build()

def require(ok, why):
    if not ok:
        raise ValueError(why)

def source_records():
    with SOURCE.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))

def load():
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    require(lock["schema_version"] == 24 and lock["adr"] == "ADR-0002"
            and lock["phase"] == "IC_INFORMATION", "outside Phase 1 scope")
    require((lock["expected_501"], lock["expected_admitted"], lock["expected_research_only"])
            == (501, 224, 277), "identity cohort changed")
    require(lock["source_counts"] == {"KL25P80M48SF0": 12, "K32L2Ax": 4},
            "exact datasheet part count changed")
    require(lock["io_supply_state"] == "PARTIAL"
            and "NOT established" in lock["io_supply_value"],
            "unqualified independent IO rail was promoted")
    require(lock["vendor_pdf_binary_archived"] is False
            and lock["vendor_pdf_sha256"] is None, "false PDF archive/SHA256 claim")
    require(blob(prev.LEDGER.read_bytes()) == lock["baseline_v23_git_blob"]
            and prev.LEDGER.read_bytes() == prev.dump(baseline_rows(), prev.header(prev.LEDGER)),
            "v23 source ledger not reproducible")
    require(blob(SOURCE.read_bytes()) == lock["source_v24_git_blob"],
            "unreviewed change to original source rows")
    return lock

def build():
    lock = load()
    src = source_records()
    require(len(src) == 16 and len({r["icpn"] for r in src}) == 16,
            "exact ordering strings missing/duplicate")
    counts = Counter()
    by_code = {}
    for r in src:
        doc = r["datasheet_id"]
        require(doc in lock["documents"], "unreviewed document family")
        meta = lock["documents"][doc]
        require(r["datasheet_revision"] == meta["revision"]
                and r["official_pdf_url"] == meta["url"]
                and r["ordering_table_locator"] == meta["ordering"]
                and r["operating_table_locator"] == meta["electrical"],
                "source revision/page/table mismatch")
        require(r["gpio_input_threshold_reference"] ==
                "GPIO VIH/VIL reference VDD; normal VDD 1.71 to 3.6 V"
                and r["open_drain_pullup_reference"] == "Open-drain output pullup VDD",
                "GPIO VDD-reference evidence changed")
        require(r["io_supply_evidence_state"] == "PARTIAL"
                and r["independent_io_rail_established"] == "NO"
                and not r["original_vendor_pdf_sha256"],
                "unsafe VDDIO power qualification or binary hash claim")
        require("VIO absolute pin rating is NOT normal operating IO rail" in r["scope_note"]
                and "do not infer socket" in r["scope_note"],
                "GPIO power and absolute maximum limits lost")
        require(r["icpn"].startswith("MKL25Z") if doc == "KL25P80M48SF0"
                else r["icpn"].startswith("K32L2A"), "part family mismatch")
        counts[doc] += 1
        by_code[r["icpn"]] = r
    require(dict(counts) == lock["source_counts"], "source family cohort drift")
    output = []
    matched = set()
    for old in baseline_rows():
        row = dict(old)
        for k in EXTRA:
            row[k] = ""
        ev = by_code.get(old["icpn"])
        if ev:
            require(old["identity_state"] == "ADMITTED"
                    and old["io_supply_state"] == "UNKNOWN" and not old["io_supply"]
                    and old["working_vdd_state"] == "VERIFIED"
                    and old["vdda_state"] == "VERIFIED"
                    and old["document_id"] == ev["datasheet_id"]
                    and old["document_uri"] == ev["official_pdf_url"]
                    and int(old["flash"].split()[0]) == int(ev["original_flash_kb"]),
                    "part/flash/doc evidence mismatch: " + old["icpn"])
            row["io_supply"] = lock["io_supply_value"]
            row["io_supply_state"] = "PARTIAL"
            row.update(
                io_reference_source_doc_v24=ev["datasheet_id"],
                io_reference_source_uri_v24=ev["official_pdf_url"],
                io_reference_source_revision_v24=ev["datasheet_revision"],
                io_reference_source_locator_v24=ev["ordering_table_locator"] + "; "
                    + ev["operating_table_locator"],
                io_reference_inference_limit_v24=ev["scope_note"],
                io_reference_pdf_sha256_v24="NOT_ARCHIVED",
            )
            matched.add(old["icpn"])
        require(row["identity_state"] == old["identity_state"]
                and row["phase"] == "1"
                and all(row[k] == old[k] for k in
                    ("base_device", "package", "pin_count", "flash", "ram",
                     "temperature", "working_vdd", "vdda")),
                "phase, admission, manufacturer parameter changed")
        output.append(row)
    require(len(output) == 501 and matched == set(by_code)
            and len(matched) == 16
            and sum(x["identity_state"] == "ADMITTED" for x in output) == 224
            and sum(x["identity_state"] == "RESEARCH_ONLY" for x in output) == 277,
            "exact identity coverage/admission mismatch")
    return output

def summary(rows):
    return prev.summary(rows)

def stats(rows):
    lock = load()
    old = baseline_rows()
    return {
        "schema_version": 24,
        "adr": "ADR-0002",
        "phase": "IC_INFORMATION",
        "manufacturer": "NXP",
        "v23_baseline_git_blob": lock["baseline_v23_git_blob"],
        "v24_official_evidence_git_blob": lock["source_v24_git_blob"],
        "exact_source_rows": 16,
        "source_counts": lock["source_counts"],
        "before_admitted": summary([r for r in old if r["identity_state"] == "ADMITTED"]),
        "after_admitted": summary([r for r in rows if r["identity_state"] == "ADMITTED"]),
        "all_501": summary(rows),
        "io_evidence_confidence": "PARTIAL",
        "independent_vddio_supply_qualified": False,
        "original_datasheet_pdfs_archived_sha256": False,
        "software_programming_supported": None,
        "physical_site_hil_validated": None,
    }

def verify():
    rows = build()
    require(LEDGER.read_bytes() == prev.dump(rows, prev.header(prev.LEDGER) + list(EXTRA)),
            "v24 501-row output does not match reproducible source data")
    require(json.loads(METRICS.read_text(encoding="utf-8")) == stats(rows),
            "v24 field coverage metric drift")
    print("NXP_PHASE1_V24_PASS admitted=224 KL25=12 K32L2A=4 IO_PARTIAL=16; "
          "no independent VDDIO qualification/Production/Programming/HIL")

if __name__ == "__main__":
    verify()
