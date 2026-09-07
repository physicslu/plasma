#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILDER_PATH = HERE / "build_evidence_pack.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("nxp_kl25_evidence_pack_builder", BUILDER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KL25EvidencePackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = load_builder()
        cls.contract = json.loads((HERE / "evidence-pack-contract.json").read_text(encoding="utf-8"))
        cls.definitions = json.loads((HERE / "reviewed-evidence-unit-definitions.json").read_text(encoding="utf-8"))
        cls.binding = json.loads((HERE / "applicability-binding.json").read_text(encoding="utf-8"))
        cls.source_lock = json.loads((HERE / "source-lock.json").read_text(encoding="utf-8"))
        cls.builder_sha256 = "b" * 64
        max_page = max(unit["pdf_page_range"][1] for unit in cls.definitions["units"])
        cls.pages_by_source = {
            "nxp_kl25_rm_rev3": [
                f"Synthetic deterministic KL25 RM physical page {page_number}\nFTFA FCCOB FSTAT SWD MDM-AP security"
                for page_number in range(1, max_page + 1)
            ]
        }

    def build(self, *, contract=None, definitions=None, binding=None, pages_by_source=None):
        return self.builder.build_pack_set(
            contract=copy.deepcopy(contract or self.contract),
            definitions=copy.deepcopy(definitions or self.definitions),
            binding=copy.deepcopy(binding or self.binding),
            source_lock=copy.deepcopy(self.source_lock),
            pages_by_source=copy.deepcopy(pages_by_source or self.pages_by_source),
            builder_sha256=self.builder_sha256,
        )

    def test_eight_primary_packs_and_exact_target_bundle_are_built(self):
        packs, bundle = self.build()
        unit_ids = {unit["unit_id"] for unit in self.definitions["units"]}
        self.assertEqual(len(packs), 8)
        self.assertEqual(
            {pack["primary_unit_id"] for pack in packs.values()},
            unit_ids,
        )
        self.assertEqual(bundle["target"], "MKL25Z128VLK4")
        self.assertEqual(set(bundle["pack_digests"]), set(packs))
        self.assertFalse(bundle["admission"]["semantic_extraction"])
        self.assertFalse(bundle["admission"]["canonical_dataset"])
        self.assertFalse(bundle["admission"]["production"])

    def test_program_longword_pack_has_transitive_command_dependencies(self):
        packs, _ = self.build()
        pack = packs["nxp-kl25-program-longword-v0-pack-v0"]
        self.assertEqual(
            {item["unit_id"] for item in pack["included_units"]},
            {
                "nxp-kl25-ftfa-register-model-v0",
                "nxp-kl25-ftfa-command-sequencing-v0",
                "nxp-kl25-program-longword-v0",
            },
        )
        self.assertEqual(len(pack["page_refs"]), 17)
        self.assertEqual(
            {(ref["source_id"], ref["pdf_page_number"]) for ref in pack["page_refs"]},
            {(ref["source_id"], ref["pdf_page_number"]) for ref in pack["page_refs"]},
        )

    def test_debug_security_pack_closes_over_debug_and_flash_security_context(self):
        packs, _ = self.build()
        pack = packs["nxp-kl25-debug-security-interaction-v0-pack-v0"]
        included = {item["unit_id"] for item in pack["included_units"]}
        self.assertEqual(
            included,
            {
                "nxp-kl25-debug-security-interaction-v0",
                "nxp-kl25-swd-mdm-ap-v0",
                "nxp-kl25-flash-security-v0",
                "nxp-kl25-ftfa-command-sequencing-v0",
                "nxp-kl25-ftfa-register-model-v0",
            },
        )

    def test_unbound_unit_fails_closed(self):
        binding = copy.deepcopy(self.binding)
        binding["unit_bindings"]["nxp-kl25-program-longword-v0"]["status"] = "UNKNOWN"
        with self.assertRaises(self.builder.KL25EvidencePackError):
            self.build(binding=binding)

    def test_unreviewed_applicability_exclusion_fails_closed(self):
        binding = copy.deepcopy(self.binding)
        binding["applicability_exclusions_reviewed"] = False
        with self.assertRaises(self.builder.KL25EvidencePackError):
            self.build(binding=binding)

    def test_missing_physical_page_fails_closed(self):
        pages = copy.deepcopy(self.pages_by_source)
        pages["nxp_kl25_rm_rev3"] = pages["nxp_kl25_rm_rev3"][:450]
        with self.assertRaises(self.builder.KL25EvidencePackError):
            self.build(pages_by_source=pages)

    def test_dependency_cycle_fails_closed(self):
        contract = copy.deepcopy(self.contract)
        contract["unit_dependencies"]["nxp-kl25-ftfa-register-model-v0"] = [
            "nxp-kl25-program-longword-v0"
        ]
        with self.assertRaises(self.builder.KL25EvidencePackError):
            self.build(contract=contract)

    def test_page_content_mutation_changes_pack_and_bundle_identity(self):
        packs_a, bundle_a = self.build()
        pages = copy.deepcopy(self.pages_by_source)
        pages["nxp_kl25_rm_rev3"][443] += "\nmutated"
        packs_b, bundle_b = self.build(pages_by_source=pages)
        pack_id = "nxp-kl25-program-longword-v0-pack-v0"
        self.assertNotEqual(packs_a[pack_id]["pack_digest"], packs_b[pack_id]["pack_digest"])
        self.assertNotEqual(bundle_a["bundle_digest"], bundle_b["bundle_digest"])

    def test_materialized_text_is_page_deduplicated_and_hash_checked(self):
        packs, _ = self.build()
        pack = packs["nxp-kl25-program-longword-v0-pack-v0"]
        text = self.builder.materialize_evidence_text(pack, self.pages_by_source)
        for ref in pack["page_refs"]:
            marker = f"=== BEGIN {ref['source_id']} PDF_PAGE {ref['pdf_page_number']} SHA256 {ref['page_text_sha256']} ==="
            self.assertEqual(text.count(marker), 1)
        pages = copy.deepcopy(self.pages_by_source)
        pages["nxp_kl25_rm_rev3"][443] += "\ndrift"
        with self.assertRaises(self.builder.KL25EvidencePackError):
            self.builder.materialize_evidence_text(pack, pages)


if __name__ == "__main__":
    unittest.main()
