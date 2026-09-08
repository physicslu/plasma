#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


qualify = _load_module("kl25_qualify_gate53", HERE / "qualify_semantic_run.py")


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


def test_gate53_contract_and_protection_vocabulary_are_explicit() -> None:
    import json

    contract = json.loads((HERE / "live-model-qualification-contract.json").read_text(encoding="utf-8"))
    assert contract["contract_id"] == "nxp-kl25-live-model-qualification-v3"
    groups = contract["semantic_screening"]["required_term_groups"]
    protection = groups["nxp-kl25-erase-all-blocks-v0"][1]
    assert protection == ["protect", "protected", "protection", "unprotected"]


def test_true_coverage_omissions_remain_omissions() -> None:
    # These are the two genuine omissions observed in the retained Gate 5.2 v2 run.
    program_longword = (
        "The Program Longword command (FCMD 0x06) programs four previously-erased bytes. "
        "The supplied address must be longword aligned and the target must be unprotected."
    )
    swd_mdm = (
        "The MDM-AP Control Register contains mass erase and debug control functions. "
        "The MDM-AP Status Register contains Flash Ready and System Security status."
    )
    assert not qualify._contains_term(program_longword, "FCCOB")
    assert not qualify._contains_term(swd_mdm, "SWD")


def test_semantic_prompt_uses_generic_coverage_rule_not_per_unit_answer_keys() -> None:
    source = (HERE / "semantic_extraction.py").read_text(encoding="utf-8")
    assert "cover the programming-relevant named entities" in source
    assert "Do not invent a named mechanism solely to improve coverage" in source
    # Required-term groups belong to the deterministic qualification contract, not the prompt renderer.
    assert "required_term_groups" not in source


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
