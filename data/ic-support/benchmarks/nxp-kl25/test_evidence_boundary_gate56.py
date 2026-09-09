#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

import build_evidence_pack as builder

HERE = Path(__file__).resolve().parent
PROGRAM = "nxp-kl25-program-longword-v0"
SOURCE = "nxp_kl25_rm_rev3"


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def load_derive():
    path = HERE / "derive_applicability_binding.py"
    spec = importlib.util.spec_from_file_location("kl25_gate56_derive", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KL25EvidenceBoundaryGate56Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current_definitions = load("reviewed-evidence-unit-definitions.json")
        cls.historical_definitions = load("reviewed-evidence-unit-definitions-v0.json")
        cls.current_binding = load("applicability-binding.json")
        cls.historical_binding = load("applicability-binding-v0.json")
        cls.pack_contract = load("evidence-pack-contract.json")
        cls.applicability_contract = load("applicability-contract.json")
        cls.evidence_lock = load("retained-applicability-evidence-lock.json")
        cls.reviewed = load("reviewed-applicability-claims.json")
        cls.source_lock = load("source-lock.json")
        cls.retained = load("retained-evidence-pack-build.json")
        cls.derive = load_derive()

    @staticmethod
    def units(value: dict) -> dict[str, dict]:
        return {item["unit_id"]: item for item in value["units"]}

    def test_historical_v0_inputs_still_match_retained_gate3_proof(self):
        self.assertEqual(
            builder.canonical_sha256(self.historical_definitions),
            self.retained["definition_set"]["digest"],
        )
        self.assertEqual(
            builder.canonical_sha256(self.historical_binding),
            self.retained["applicability_binding"]["digest"],
        )
        self.assertEqual(
            builder.canonical_sha256(self.pack_contract),
            self.retained["evidence_pack_contract"]["digest"],
        )

    def test_release_is_exactly_one_page_boundary_correction(self):
        release = self.current_definitions["boundary_release"]
        self.assertEqual(release["release_id"], "nxp-kl25-evidence-boundary-release-v1")
        self.assertEqual(release["review_status"], "REVIEWED")
        self.assertEqual(
            release["supersedes_definition_digest"],
            builder.canonical_sha256(self.historical_definitions),
        )
        self.assertEqual(len(release["corrections"]), 1)
        correction = release["corrections"][0]
        self.assertEqual(correction["unit_id"], PROGRAM)
        self.assertEqual(correction["source_id"], SOURCE)
        self.assertEqual(correction["previous_pdf_page_range"], [444, 445])
        self.assertEqual(correction["corrected_pdf_page_range"], [444, 446])
        self.assertEqual(correction["scope_change"], "BOUNDARY_ONLY_NO_UNIT_IDENTITY_CHANGE")

        before = self.units(self.historical_definitions)
        after = self.units(self.current_definitions)
        self.assertEqual(set(before), set(after))
        for unit_id in sorted(before):
            old = copy.deepcopy(before[unit_id])
            new = copy.deepcopy(after[unit_id])
            if unit_id == PROGRAM:
                self.assertEqual(old.pop("pdf_page_range"), [444, 445])
                self.assertEqual(new.pop("pdf_page_range"), [444, 446])
            self.assertEqual(old, new)

    def test_current_binding_is_deterministically_regenerated(self):
        derived = self.derive.derive(
            copy.deepcopy(self.applicability_contract),
            copy.deepcopy(self.current_definitions),
            copy.deepcopy(self.evidence_lock),
            copy.deepcopy(self.reviewed),
            HERE / "retained-applicability-evidence-lock.json",
        )
        self.assertEqual(derived, self.current_binding)
        self.assertEqual(self.current_binding["unit_bindings"][PROGRAM]["pdf_page_range"], [444, 446])

        old = copy.deepcopy(self.historical_binding)
        new = copy.deepcopy(self.current_binding)
        self.assertEqual(old["unit_bindings"][PROGRAM]["pdf_page_range"], [444, 445])
        old["unit_bindings"][PROGRAM]["pdf_page_range"] = [444, 446]
        self.assertEqual(old, new)

    def test_synthetic_pack_admits_446_only_where_required_and_not_447(self):
        max_page = max(item["pdf_page_range"][1] for item in self.current_definitions["units"])
        pages = {
            SOURCE: [f"Synthetic Gate 5.6 page {page}" for page in range(1, max_page + 1)]
        }
        packs, _ = builder.build_pack_set(
            contract=copy.deepcopy(self.pack_contract),
            definitions=copy.deepcopy(self.current_definitions),
            binding=copy.deepcopy(self.current_binding),
            source_lock=copy.deepcopy(self.source_lock),
            pages_by_source=pages,
            builder_sha256="d" * 64,
        )
        program_pack = next(pack for pack in packs.values() if pack["primary_unit_id"] == PROGRAM)
        refs = {(item["source_id"], item["pdf_page_number"]) for item in program_pack["page_refs"]}
        self.assertIn((SOURCE, 444), refs)
        self.assertIn((SOURCE, 445), refs)
        self.assertIn((SOURCE, 446), refs)
        self.assertNotIn((SOURCE, 447), refs)

        erase_pack = next(
            pack for pack in packs.values()
            if pack["primary_unit_id"] == "nxp-kl25-erase-sector-v0"
        )
        erase_446 = next(
            item for item in erase_pack["page_refs"]
            if item["source_id"] == SOURCE and item["pdf_page_number"] == 446
        )
        self.assertEqual(erase_446["required_by_unit_ids"], ["nxp-kl25-erase-sector-v0"])

        program_446 = next(
            item for item in program_pack["page_refs"]
            if item["source_id"] == SOURCE and item["pdf_page_number"] == 446
        )
        self.assertEqual(program_446["required_by_unit_ids"], [PROGRAM])

    def test_source_lock_and_non_ai_admissions_remain_frozen(self):
        rm = next(item for item in self.source_lock["sources"] if item["source_id"] == SOURCE)
        self.assertEqual(rm["integrity"]["digest"], "7911a7d9f8192fa317960feabc9377d0fd81a9b90d31f8070cae9612cb237241")
        self.assertEqual(rm["integrity"]["byte_length"], 6637765)
        for artifact in (self.current_definitions, self.current_binding, self.pack_contract):
            text = json.dumps(artifact)
            self.assertNotIn('"production": true', text)
            self.assertNotIn('"semantic_extraction": true', text)
            self.assertNotIn('"canonical_dataset": true', text)


if __name__ == "__main__":
    unittest.main()
