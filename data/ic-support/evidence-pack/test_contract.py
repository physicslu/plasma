from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from contract import (
    EvidenceContractError,
    build_pack,
    catalog_digest,
    resolve_target_bundle,
)

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "stm32f103c-foundation-v0.json"
TAXONOMY = HERE / "taxonomy-v0.json"
RULES = HERE / "rules-v0.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class EvidencePackContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = load(FIXTURE)
        self.taxonomy = load(TAXONOMY)
        self.rules = load(RULES)
        self.source_lock_id = self.fixture["source_lock_id"]
        self.ds_catalog = copy.deepcopy(self.fixture["catalogs"]["datasheet"])
        self.pm_catalog = copy.deepcopy(self.fixture["catalogs"]["programming_manual"])

    def build_packs(self, *, rules=None, ds_catalog=None, ai_units=()):
        rules = rules or self.rules
        ds_catalog = ds_catalog or self.ds_catalog
        ds_pack = build_pack(
            pack_id="stm32f103c-datasheet-programming-v0",
            purpose="PROGRAMMING_SUPPORT",
            source_lock_id=self.source_lock_id,
            catalogs=[ds_catalog],
            taxonomy=self.taxonomy,
            rules=rules,
            builder={"name": "contract-test-builder", "version": "0.1.0"},
            dependency_edges=self.fixture["dependency_edges"],
            ai_supplemental_unit_ids=ai_units,
        )
        pm_pack = build_pack(
            pack_id="stm32f10xxx-programming-manual-v0",
            purpose="PROGRAMMING_SUPPORT",
            source_lock_id=self.source_lock_id,
            catalogs=[self.pm_catalog],
            taxonomy=self.taxonomy,
            rules=rules,
            builder={"name": "contract-test-builder", "version": "0.1.0"},
            dependency_edges=[],
        )
        return ds_pack, pm_pack

    def test_catalog_is_bound_to_source_preprocessor_and_normalization(self):
        original = self.ds_catalog["catalog_digest"]
        changed = copy.deepcopy(self.ds_catalog)
        changed["source"]["digest"] = "0" * 64
        changed.pop("catalog_digest")
        changed["catalog_digest"] = catalog_digest(changed)
        self.assertNotEqual(original, changed["catalog_digest"])

        changed = copy.deepcopy(self.ds_catalog)
        changed["preprocessor"]["version"] = "0.2.0"
        changed.pop("catalog_digest")
        changed["catalog_digest"] = catalog_digest(changed)
        self.assertNotEqual(original, changed["catalog_digest"])

        changed = copy.deepcopy(self.ds_catalog)
        changed["normalization_contract"] = "evidence-unit-normalization-v1"
        changed.pop("catalog_digest")
        changed["catalog_digest"] = catalog_digest(changed)
        self.assertNotEqual(original, changed["catalog_digest"])

    def test_dependency_closure_overrides_exclusion_and_unknown_fails_closed(self):
        ds_pack, _ = self.build_packs()
        entries = {item["unit_id"]: item for item in ds_pack["included_units"]}

        self.assertIn("ds5319-debug-pin-table", entries)
        self.assertIn("DEPENDENCY_FROM:ds5319-debug", entries["ds5319-debug-pin-table"]["inclusion_reasons"])
        self.assertEqual(entries["ds5319-debug-pin-table"]["origin"], "DETERMINISTIC")
        self.assertNotIn("ds5319-adc", entries)
        self.assertIn("ds5319-unknown", entries)
        self.assertIn("UNKNOWN_FAIL_CLOSED", entries["ds5319-unknown"]["inclusion_reasons"])

    def test_ai_is_add_only_and_cannot_remove_deterministic_evidence(self):
        baseline, _ = self.build_packs()
        enriched, _ = self.build_packs(ai_units=["ds5319-adc"])
        baseline_ids = {item["unit_id"] for item in baseline["included_units"]}
        enriched_entries = {item["unit_id"]: item for item in enriched["included_units"]}

        self.assertTrue(baseline_ids <= set(enriched_entries))
        self.assertEqual(enriched_entries["ds5319-adc"]["origin"], "AI_SUPPLEMENTAL")
        for unit_id in baseline_ids:
            self.assertEqual(enriched_entries[unit_id]["origin"], "DETERMINISTIC")

    def test_rule_change_changes_pack_identity(self):
        baseline, _ = self.build_packs()
        changed_rules = copy.deepcopy(self.rules)
        changed_rules["rule_set_id"] = "ic-programming-evidence-rules-v0.1-test"
        changed, _ = self.build_packs(rules=changed_rules)
        self.assertNotEqual(baseline["rules_digest"], changed["rules_digest"])
        self.assertNotEqual(baseline["pack_digest"], changed["pack_digest"])

    def test_source_change_changes_pack_and_bundle_identity(self):
        baseline_ds, baseline_pm = self.build_packs()
        changed_catalog = copy.deepcopy(self.ds_catalog)
        changed_catalog["source"]["digest"] = "1" * 64
        changed_catalog.pop("catalog_digest")
        changed_catalog["catalog_digest"] = catalog_digest(changed_catalog)
        changed_ds, changed_pm = self.build_packs(ds_catalog=changed_catalog)

        baseline_packs = {baseline_ds["pack_id"]: baseline_ds, baseline_pm["pack_id"]: baseline_pm}
        changed_packs = {changed_ds["pack_id"]: changed_ds, changed_pm["pack_id"]: changed_pm}
        binding = self.fixture["applicability_binding"]

        baseline_bundle = resolve_target_bundle(
            target_icpn="STM32F103C8T6",
            binding=binding,
            packs=baseline_packs,
            source_lock_id=self.source_lock_id,
        )
        changed_bundle = resolve_target_bundle(
            target_icpn="STM32F103C8T6",
            binding=binding,
            packs=changed_packs,
            source_lock_id=self.source_lock_id,
        )
        self.assertNotEqual(baseline_ds["pack_digest"], changed_ds["pack_digest"])
        self.assertNotEqual(baseline_bundle["bundle_digest"], changed_bundle["bundle_digest"])

    def test_many_to_many_reuse_and_exact_target_resolution(self):
        ds_pack, pm_pack = self.build_packs()
        packs = {ds_pack["pack_id"]: ds_pack, pm_pack["pack_id"]: pm_pack}
        binding = self.fixture["applicability_binding"]

        c8 = resolve_target_bundle(
            target_icpn="STM32F103C8T6",
            binding=binding,
            packs=packs,
            source_lock_id=self.source_lock_id,
        )
        cb = resolve_target_bundle(
            target_icpn="STM32F103CBT6",
            binding=binding,
            packs=packs,
            source_lock_id=self.source_lock_id,
        )

        self.assertEqual(c8["pack_digests"], cb["pack_digests"])
        self.assertEqual(len(c8["pack_digests"]), 2)
        self.assertNotEqual(c8["bundle_digest"], cb["bundle_digest"])
        self.assertFalse(c8["canonical_dataset_admission"])
        self.assertFalse(c8["production_admission"])

    def test_applicability_without_evidence_fails_closed(self):
        ds_pack, pm_pack = self.build_packs()
        packs = {ds_pack["pack_id"]: ds_pack, pm_pack["pack_id"]: pm_pack}
        binding = copy.deepcopy(self.fixture["applicability_binding"])
        binding["claims"]["ds-x8"]["evidence_unit_ids"] = []

        with self.assertRaises(EvidenceContractError):
            resolve_target_bundle(
                target_icpn="STM32F103C8T6",
                binding=binding,
                packs=packs,
                source_lock_id=self.source_lock_id,
            )

    def test_unbound_target_fails_closed(self):
        ds_pack, pm_pack = self.build_packs()
        packs = {ds_pack["pack_id"]: ds_pack, pm_pack["pack_id"]: pm_pack}

        with self.assertRaises(EvidenceContractError):
            resolve_target_bundle(
                target_icpn="STM32F103RCT6",
                binding=self.fixture["applicability_binding"],
                packs=packs,
                source_lock_id=self.source_lock_id,
            )


if __name__ == "__main__":
    unittest.main()
