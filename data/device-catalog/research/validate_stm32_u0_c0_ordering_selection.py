#!/usr/bin/env python3
"""Hard-lock STM32 U0/C0 ordering evidence and next-family research selection."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CROSS = HERE / "stm32-cross-family-prioritization-baseline.json"
ACCESS = HERE / "stm32-evidence-accessibility-probe-baseline.json"
REVIEW = HERE / "stm32-u0-c0-ordering-authority-review.json"
SELECTION = HERE / "stm32-next-family-selection.json"

H = {
    "cross": "9a99865865f048e6a7636efd82cb17958fdc593240a329e18e3b68d8b0f862f9",
    "access": "473e979818770fda2661e963d064f3a0cfbd7cbcad920203e7f358b5b6e140b6",
    "review": "3fe019d420cbe43c732b9d403acaa2f1b0bf0dc583b38073eb25528217f5efe9",
    "selection": "2c81a6c3495a75a6f4115252293af6e99b727f3d12d67f31853922279a96d017",
    "production_prestate": "93c2a4541daeb1d4aa1dcc57edef54042862eb6d9da03e3a6b401e4b8481b11d",
}
TARGETS = ["STM32U031C6","STM32U073C8","STM32U083CC","STM32C011F4","STM32C031C4","STM32C051C6","STM32C071C8","STM32C091CB","STM32C092CB"]
DOCS = {"DS14581":2,"DS14548":2,"DS14463":2,"DS13866":5,"DS13867":4,"DS14721":2,"DS14693":2,"DS14720":3}
SHORTLIST = ["STM32U0","STM32C0","STM32L1"]

def req(v: bool, msg: str) -> None:
    if not v:
        raise RuntimeError(msg)

def readj(p: Path) -> dict:
    v = json.loads(p.read_text(encoding="utf-8"))
    req(isinstance(v, dict), f"{p}: object required")
    return v

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def all_false(v: object) -> bool:
    return isinstance(v, dict) and bool(v) and set(v.values()) == {False}

def main() -> int:
    cross, access, review, selection = map(readj, (CROSS, ACCESS, REVIEW, SELECTION))
    for key, path in (("cross",CROSS),("access",ACCESS),("review",REVIEW),("selection",SELECTION)):
        req(sha(path) == H[key], f"{key} byte drift")

    shortlist = cross.get("research_shortlist")
    req(isinstance(shortlist, list), "cross-family shortlist missing")
    req([x.get("plasma_series") for x in shortlist] == SHORTLIST, "frozen shortlist drift")
    req(cross.get("selected_next_research_family") is None, "prioritization must remain pre-selection")

    s = access["by_series"]
    req(s["STM32U0"]["active_candidate_targets"] == 3, "U0 identity evidence drift")
    req(s["STM32C0"]["active_candidate_targets"] == 6, "C0 identity evidence drift")
    req(s["STM32L1"]["lifecycle_excluded_targets"] == 3, "L1 lifecycle evidence drift")
    req(access.get("selected_next_research_family") is None, "identity probe must remain pre-selection")

    req(review["scope"] == {
        "families":["STM32U0","STM32C0"],
        "purpose":"compare official ST ordering-information evidence quality before next-family research selection",
        "representative_target_count":9,
        "unique_official_datasheet_count":8,
    }, "ordering review scope drift")
    req(review["method"]["authority"] == "official_st_datasheet", "ordering authority drift")
    req(review["method"]["visual_screenshot_review_is_selection_gate"] is False, "visual cache must not gate selection")
    req(review["method"]["transport_diagnostics_are_selection_evidence"] is False, "transport failures must not score families")
    rows = review["targets"]
    req([x["base_device"] for x in rows] == TARGETS, "ordering target set/order drift")
    req(all(x["required_fields_complete"] is True and x["structured_text_review"] == "verified" for x in rows), "incomplete ordering evidence")
    req({x["datasheet_id"]:x["revision"] for x in rows} == DOCS, "datasheet authority/revision drift")
    req(all(x["datasheet_url"].startswith("https://www.st.com/resource/en/datasheet/") for x in rows), "non-ST authority")
    req(any("N is an official product-version option" in t for t in next(x for x in rows if x["base_device"]=="STM32C071C8")["special_semantics"]), "C071 N-version semantics lost")
    c091 = next(x for x in rows if x["base_device"]=="STM32C091CB")
    c092 = next(x for x in rows if x["base_device"]=="STM32C092CB")
    req(c091["datasheet_id"] == c092["datasheet_id"] == "DS14720", "C091/C092 shared authority drift")
    req(review["comparison"] == {"eligible_for_frozen_priority_tiebreak":["STM32U0","STM32C0"],"result":"equivalent_required_evidence_quality","selected_next_research_family":None}, "evidence-quality comparison drift")
    req(all_false(review["claims"]), "ordering review claims must remain false")

    req(selection["inputs"] == {
        "cross_family_prioritization_sha256":H["cross"],
        "identity_lifecycle_accessibility_baseline_sha256":H["access"],
        "ordering_information_review_sha256":H["review"],
        "production_prestate_sha256":H["production_prestate"],
    }, "selection input binding drift")
    d = selection["decision"]
    req(d["evidence_quality_comparison"] == "STM32U0_equals_STM32C0", "evidence tie drift")
    req(d["tie_break_policy"] == "frozen_cross_family_prioritization_order", "tie-break drift")
    req(d["frozen_shortlist"] == SHORTLIST, "selection shortlist drift")
    req(d["selected_next_research_family"] == "STM32U0", "next research family drift")
    req(d["selection_scope"] == "next_family_research_only", "selection scope drift")
    req(selection["candidate_evidence"]["STM32L1"]["disposition"] == "deprioritized_for_next_family_research_due_to_lifecycle", "L1 disposition drift")
    req(selection["candidate_evidence"]["STM32L1"]["rejected_for_future_support"] is False, "L1 must not be rejected")
    req(all_false(selection["authority_boundaries"]), "selection cannot authorize admission/programming/runtime")

    print("STM32 U0/C0 ordering evidence and next-family research selection: PASS")
    print(json.dumps({"selected_next_research_family":"STM32U0","review_sha256":H["review"],"selection_sha256":H["selection"]}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
