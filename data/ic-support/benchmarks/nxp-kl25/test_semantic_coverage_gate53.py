#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


qualify = _load_module("kl25_qualify_gate53", HERE / "qualify_semantic_run.py")


def _contract() -> dict:
    return json.loads((HERE / "live-model-qualification-contract.json").read_text(encoding="utf-8"))


def test_structured_identifier_segments_match_required_concepts() -> None:
    text = (
        "The FTFA_FSTAT register reports flash status. "
        "The FTFA_FCCOB registers carry command parameters."
    )
    assert qualify._contains_term(text, "FTFA")
    assert qualify._contains_term(text, "FSTAT")
    assert qualify._contains_term(text, "FCCOB")


def test_compound_terms_keep_exact_behavior() -> None:
    assert qualify._contains_term("The MDM-AP is available through the debug port.", "MDM-AP")
    assert qualify._contains_term("Do not project FLASH_CR into NXP semantics.", "FLASH_CR")
    assert not qualify._contains_term("The MDM AP is described here.", "MDM-AP")


def test_identifier_segment_matching_also_protects_forbidden_terms() -> None:
    assert qualify._contains_term("A projected FLASH_KEYR register would be cross-vendor contamination.", "KEYR")


def test_no_fuzzy_or_stemming_behavior() -> None:
    assert not qualify._contains_term("The region is protected.", "protect")
    assert qualify._contains_term("The region is protected.", "protected")
    assert not qualify._contains_term("The controller uses FSTATUS.", "FSTAT")


def test_gate53_screening_vocabulary_survives_gate54_contract_versioning() -> None:
    contract = _contract()
    assert contract["contract_id"] == "nxp-kl25-live-model-qualification-v4.1"
    groups = contract["semantic_screening"]["required_term_groups"]
    protection = groups["nxp-kl25-erase-all-blocks-v0"][1]
    assert protection == ["protect", "protected", "protection", "unprotected"]


def test_fccob_indexed_register_family_vocabulary_is_explicit() -> None:
    groups = _contract()["semantic_screening"]["required_term_groups"]
    expected = ["FCCOB", "FCCOBn"] + [f"FCCOB{i}" for i in range(12)]
    for unit_id in (
        "nxp-kl25-ftfa-register-model-v0",
        "nxp-kl25-ftfa-command-sequencing-v0",
        "nxp-kl25-program-longword-v0",
    ):
        fccob_group = next(group for group in groups[unit_id] if "FCCOB" in group)
        assert fccob_group == expected


def test_retained_v3_fccob_forms_match_without_fuzzy_prefix_logic() -> None:
    groups = _contract()["semantic_screening"]["required_term_groups"]
    register_group = next(group for group in groups["nxp-kl25-ftfa-register-model-v0"] if "FCCOB" in group)
    program_group = next(group for group in groups["nxp-kl25-program-longword-v0"] if "FCCOB" in group)

    register_text = (
        "The Flash Common Command Object Registers (FTFA_FCCOBn) are located at addresses "
        "0x4002_0004 to 0x4002_000F and provide 12 bytes for command codes and parameters."
    )
    program_text = (
        "The Program Longword command requires FCCOB0 to be 0x06 (PGM4), FCCOB1-3 to contain "
        "the longword-aligned flash address, and FCCOB4-7 to contain the data bytes to be programmed."
    )
    assert any(qualify._contains_term(register_text, term) for term in register_group)
    assert any(qualify._contains_term(program_text, term) for term in program_group)

    assert not any(qualify._contains_term("The controller exposes FCCOBX.", term) for term in register_group)
    assert not qualify._contains_term("The controller uses FSTATUS.", "FSTAT")


def test_gate52_true_coverage_omissions_remain_omissions() -> None:
    program_longword = (
        "The Program Longword command (FCMD 0x06) programs four previously-erased bytes. "
        "The supplied address must be longword aligned and the target must be unprotected."
    )
    swd_mdm = (
        "The MDM-AP Control Register contains mass erase and debug control functions. "
        "The MDM-AP Status Register contains Flash Ready and System Security status."
    )
    fccob_group = next(
        group
        for group in _contract()["semantic_screening"]["required_term_groups"]["nxp-kl25-program-longword-v0"]
        if "FCCOB" in group
    )
    assert not any(qualify._contains_term(program_longword, term) for term in fccob_group)
    assert not qualify._contains_term(swd_mdm, "SWD")


def test_semantic_prompt_uses_generic_coverage_rule_not_per_unit_answer_keys() -> None:
    source = (HERE / "semantic_extraction.py").read_text(encoding="utf-8")
    assert "cover the programming-relevant named entities" in source
    assert "Do not invent a named mechanism solely to improve coverage" in source
    assert "required_term_groups" not in source


def test_semantic_prompt_requires_global_fact_id_uniqueness() -> None:
    source = (HERE / "semantic_extraction.py").read_text(encoding="utf-8")
    assert "fact_id must be globally unique across the entire response" in source
    assert "do not restart fact numbering for each Evidence Unit" in source
    assert "duplicate fact_id" in source


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
