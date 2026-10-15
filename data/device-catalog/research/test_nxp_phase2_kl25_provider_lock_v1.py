"""ADR-0002 NXP KL25 Phase2: exact-ICPN software evidence & provider mismatch gates."""
from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

import nxp_phase2_kl25_provider_lock_v1 as audit

class TestNxpKl25Phase2ProviderLock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result=audit.build()
        cls.rows=cls.result["rows"]
        cls.old=json.loads(audit.checked_bytes("executor_backend"))
        cls.adapter=json.loads(audit.checked_bytes("executor_contract"))
        cls.release=json.loads(audit.checked_bytes("runtime"))

    def test_exact_12_and_canonical_nxp_phase_denominators(self):
        self.assertEqual(len(self.rows),12)
        self.assertEqual(self.result["phase1_identified_global_nxp"],297)
        self.assertEqual(self.result["phase2_candidate_global_nxp"],28)
        self.assertEqual(self.result["phase2_supported_newly_qualified_by_this_review"],0)
        self.assertEqual(self.result["phase3_newly_qualified"],0)
        self.assertFalse(self.result["production_or_ic_selector_mutated"])

    def test_only_one_exact_icpn_has_fake_executor_prototype(self):
        known=[r["icpn"] for r in self.rows if r["existing_exact_software_prototype"]]
        self.assertEqual(known,["MKL25Z128VLK4"])
        for r in self.rows:
            self.assertFalse(r["phase2_supported"])
            self.assertFalse(r["source_only_programming_profile_reusable"])
            self.assertFalse(r["current_provider_operations_qualified"])
            self.assertEqual(r["phase3_hil"],"NOT_AUDITED")
            if r["icpn"]!="MKL25Z128VLK4":
                self.assertEqual(r["software_prototype_scope_only"],[])

    def test_upstream_diff_proves_driver_and_include_changed(self):
        d=self.result["upstream_source_diff"]
        self.assertEqual(d["source_graph_reviewed"],3)
        self.assertEqual(d["byte_identical_files"],1)
        self.assertEqual(d["changed_files"],2)
        self.assertEqual(d["changed_paths"],["tcl/target/klx.cfg",
                                             "src/flash/nor/kinetis.c"])
        self.assertFalse(d["source_semantics_requalified"])
        self.assertFalse(d["current_provider_software_supported"])

    def test_reject_fabricated_unchanged_kinetis_driver_claim(self):
        delta=json.loads(audit.checked_bytes("upstream_delta"))
        for item in delta["per_file"]:
            if item["path"]=="src/flash/nor/kinetis.c":
                item["identical_bytes"]=True
        with self.assertRaisesRegex(ValueError,"Git blob evidence"):
            audit.review_upstream_delta(delta,self.result["provider_boundary"])

    def test_reject_source_diff_promoted_to_qualified(self):
        delta=json.loads(audit.checked_bytes("upstream_delta"))
        delta["conclusions"]["current_provider_exact_operations_qualified"]=True
        with self.assertRaisesRegex(ValueError,"same CFG"):
            audit.review_upstream_delta(delta,self.result["provider_boundary"])

    def test_openocd_lock_differs_from_current_approved_provider(self):
        b=self.result["provider_boundary"]
        self.assertEqual(b["benchmark_backend_commit"],audit.LEGACY_COMMIT)
        self.assertEqual(b["approved_provider_commit"],audit.APPROVED_COMMIT)
        self.assertTrue(b["backend_commit_mismatch"])
        self.assertTrue(b["requires_provider_requalification"])
        self.assertFalse(b["prototype_qualified_under_current_provider"])
        self.assertFalse(b["real_ic_execution_evidenced_here"])

    def test_old_gate58_rejection_cannot_be_erased(self):
        d=copy.deepcopy(self.adapter)
        d["gate58"]["qualification_status"]="QUALIFIED"
        with self.assertRaisesRegex(ValueError,"Gate 5.8"):
            audit.review_provider_boundary(self.old,d,self.release)

    def test_backend_approval_cannot_be_forged_by_relabeling_commit(self):
        b=copy.deepcopy(self.old)
        b["commit"]=audit.APPROVED_COMMIT
        with self.assertRaisesRegex(ValueError,"frozen exact-prototype"):
            audit.review_provider_boundary(b,self.adapter,self.release)

    def test_future_commit_match_alone_still_requires_review(self):
        # Pure unit-level test: even a matching pin doesn't automatically
        # transfer source semantics or Phase2 operation qualification.
        r=copy.deepcopy(self.release)
        r["source_commit"]=audit.LEGACY_COMMIT
        with patch.object(audit,"APPROVED_COMMIT",audit.LEGACY_COMMIT):
            b=audit.review_provider_boundary(self.old,self.adapter,r)
        self.assertFalse(b["backend_commit_mismatch"])
        self.assertTrue(b["requires_provider_requalification"])
        self.assertFalse(b["prototype_qualified_under_current_provider"])

    def test_fc_field_program_or_sector_erase_boundary_cannot_change(self):
        for field,value in (
            ("flash_configuration_field_start","0x00000300"),
            ("flash_configuration_field_size_bytes",0),
            ("flash_configuration_field_sector_start","0x00000000"),
            ("program_start_alignment_bytes",1),
            ("program_implicit_erase",True),
            ("erase_requires_exact_sector_range",False),
        ):
            with self.subTest(field=field):
                b=copy.deepcopy(self.old)
                b["admitted_constraints"][field]=value
                with self.assertRaisesRegex(ValueError,"FCF"):
                    audit.review_provider_boundary(b,self.adapter,self.release)

    def test_unsupported_security_operations_cannot_be_omitted(self):
        d=copy.deepcopy(self.adapter)
        d["operation_mapping"].pop("MDM_MASS_ERASE")
        with self.assertRaisesRegex(ValueError,"operation scope"):
            audit.review_provider_boundary(self.old,d,self.release)

    def test_no_hardware_or_production_claims_from_software_executor(self):
        for k in ("hardware_behavior_validated","production_admission",
                  "destructive_security_operation_admission"):
            b=copy.deepcopy(self.old)
            b["trust_boundary"][k]=True
            with self.subTest(k=k),self.assertRaisesRegex(ValueError,"software-only"):
                audit.review_provider_boundary(b,self.adapter,self.release)

    def test_reject_misleading_cross_variant_profile_reuse(self):
        rows=copy.deepcopy(self.rows)
        row=next(r for r in rows if r["icpn"]=="MKL25Z32VFM4")
        row["software_prototype_scope_only"]=["READ","VERIFY","PROGRAM","ERASE_SECTOR"]
        with self.assertRaisesRegex(ValueError,"cannot inherit"):
            audit.validate(rows,self.result["provider_boundary"])

    def test_reject_fabricated_supported_or_fake_phase3(self):
        for field,value in (
            ("phase2_supported",True),
            ("current_provider_operations_qualified",True),
            ("source_only_programming_profile_reusable",True),
            ("phase3_hil","PASSED"),
        ):
            rows=copy.deepcopy(self.rows)
            rows[0][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"fabricated"):
                audit.validate(rows,self.result["provider_boundary"])

    def test_unreviewed_provider_cannot_become_qualified_by_boolean(self):
        rows=copy.deepcopy(self.rows)
        b=copy.deepcopy(self.result["provider_boundary"])
        b["prototype_qualified_under_current_provider"]=True
        with self.assertRaisesRegex(ValueError,"cannot qualify"):
            audit.validate(rows,b)

    def test_source_bytes_git_blob_lock_fail_closed(self):
        with patch.dict(audit.FILES, {
            "kl25_official":(audit.RESEARCH/"nxp-kl25-commercial-icpn.csv","0"*40)
        }):
            with self.assertRaisesRegex(ValueError,"source evidence Git blob"):
                audit.checked_bytes("kl25_official")

    def test_manufacturer_32_64_128_all_four_order_codes(self):
        groups={}
        for row in self.rows:
            groups.setdefault(row["flash_kib_manufacturer"],[]).append(row["icpn"])
        self.assertEqual({size:len(codes) for size,codes in groups.items()},
                         {32:4,64:4,128:4})
        self.assertTrue(all(r["phase1"]=="IDENTIFIED" and r["phase2"]=="CANDIDATE"
                            for r in self.rows))

if __name__=="__main__":
    unittest.main(verbosity=2)
