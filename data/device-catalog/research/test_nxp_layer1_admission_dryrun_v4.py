#!/usr/bin/env python3
"""NXP frozen 353 evidence and 12 metadata-qualified KL25 admission proposal."""
from __future__ import annotations
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("nxp_v4",HERE/"nxp_layer1_admission_dryrun_v4.py")
assert spec and spec.loader
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class NxpLayer1DryRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records,cls.report,cls.projection,cls.kl25=m.proposal()

    def test_exact_bounded_353_partition(self):
        self.assertEqual(len(self.records),353)
        self.assertEqual(len({r["icpn"] for r in self.records}),353)
        self.assertEqual(self.report["research_partition"],{
            "FOUR_FIELD_HTML_EVIDENCE_ONLY_REVIEW_REQUIRED":212,
            "KL25_BOUNDED_LAYER1_PROPOSAL_REQUIRES_OWNER_APPROVAL":12,
            "RESEARCH_SOURCE_OR_METADATA_GAP_NOT_ADMISSIBLE":129,
        })
        self.assertTrue(self.report["no_global_nxp_active_denominator"])

    def test_all_publication_and_hil_authority_denied(self):
        self.assertFalse(self.report["production_write_authorized"])
        self.assertFalse(self.report["runtime_programming_qualified"])
        self.assertFalse(self.report["physical_programming_verified"])
        self.assertFalse(self.report["publication_performed"])
        self.assertTrue(self.report["proposal_requires_owner_approval"])
        self.assertTrue(all(r["production_write_authorized"]=="false"
                            and r["canonical_metadata_admission_authorized"]=="false"
                            and r["programming_backend_qualified"]=="false"
                            and r["physical_programming_verified"]=="false"
                            for r in self.records))

    def test_kl25_exact_readiness_is_not_equated_to_programming(self):
        kl=[r for r in self.records if r["candidate_class"].startswith("KL25_")]
        self.assertEqual(len(kl),12)
        self.assertTrue(all(r["independent_qualifying_source"]==
            "manufacturer_document_reviewed_canonical_route_still_no_HIL" for r in kl))
        self.assertEqual(self.report["kl25_route_config_only"],"tcl/target/kl25.cfg")

    def test_unpublished_manifest_projection_is_twelve_only(self):
        self.assertEqual(self.report["production_exact_prestate"],4629)
        self.assertEqual(self.report["production_source_prestate"],28)
        self.assertEqual(self.report["hypothetical_production_exact_after_if_approved"],4641)
        self.assertEqual(self.report["hypothetical_production_sources_after_if_approved"],29)
        self.assertEqual(self.projection["sources"][-1]["row_count"],12)
        self.assertEqual(self.projection["sources"][-1]["sha256"],m.KL25_SOURCE_SHA)
        self.assertEqual(m.sha256(self.kl25),m.KL25_SOURCE_SHA)

    def test_85_http_non200_are_not_silent_alias_metadata(self):
        self.assertEqual(self.report["eighty_five_http_non200_peer_triage"],{
            "R_with_active_exact_minus_R_peer":22,
            "R_without_active_exact_minus_R_peer":32,
            "non_R_http_non200":31,
        })
        paired=[r for r in self.records if r["existing_exact_peer"]]
        self.assertEqual(len(paired),22)
        self.assertTrue(all(r["candidate_class"]==
            "RESEARCH_SOURCE_OR_METADATA_GAP_NOT_ADMISSIBLE" and
            r["source_exception"]=="http_non200" and
            r["requested_next_evidence"]=="official_datasheet_exact_ordering_table_required"
            for r in paired))
        self.assertTrue(all(r["peer_frozen_metadata_status"] in {
            "FOUR_SOURCE_FIELDS_VERIFIED_REVIEW_REQUIRED",
            "PARTIAL_SOURCE_FIELDS_REVIEW_REQUIRED",
        } for r in paired))

    def test_original_manifest_mutation_blocks_proposal(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"manifest.json"
            doc=json.loads(m.MANIFEST.read_text())
            doc["sources"].append(dict(doc["sources"][0]))
            path.write_text(json.dumps(doc))
            with patch.object(m,"MANIFEST",path):
                with self.assertRaisesRegex(ValueError,"Production staged KL25 source/manifest drift|Production manifest changed"):
                    m.proposal()

    def test_kl25_csv_source_mutation_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"KL25.csv"
            path.write_bytes(m.KL25.read_bytes().replace(b"MKL25Z128VFM4",b"MKL25Z128VFMX"))
            with patch.object(m,"KL25",path):
                with self.assertRaisesRegex(ValueError,"manufacturer-reviewed"):
                    m.proposal()

    def test_original_exact_active_identity_is_frozen(self):
        self.assertEqual(self.report["active_set_sha256"],m.ORIGINAL_353)
        self.assertEqual(self.report["production_nxp_exact_prestate"],0)
        self.assertEqual(self.report["unresolved_source_gap_counts"],{
            "http_non200":85,"flash_multi_value":8,"imx_rt_flash_temperature":23,
            "mcx_flash_ambient":5,"wireless_ambient":8,
        })


if __name__=="__main__":
    unittest.main()
