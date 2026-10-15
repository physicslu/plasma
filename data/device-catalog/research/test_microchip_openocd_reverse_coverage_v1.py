"""Negative tests for OpenOCD CFG-FIRST Microchip ICPN/Base Device crosswalk."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import microchip_openocd_reverse_coverage_v1 as target


def sample_index():
    return {
        "ATSAMD21G18A": {
            "dfp_name": "ATSAMD21G18A", "priority": "P0",
            "openocd_target_cfg": "tcl/target/at91samdXX.cfg",
        },
        "ATSAMD51G18A": {
            "dfp_name": "ATSAMD51G18A", "priority": "P0",
            "openocd_target_cfg": "tcl/target/atsame5x.cfg",
        },
        "PIC32MX110F016B": {
            "dfp_name": "PIC32MX110F016B", "priority": "P0",
            "openocd_target_cfg": "tcl/target/pic32mx.cfg",
        },
        "ATSAML21E18A": {
            "dfp_name": "ATSAML21E18A", "priority": "P1",
            "openocd_target_cfg": "tcl/target/atsaml1x.cfg",
        },
    }


def source(icpn, base, query=None):
    return {
        "query": query or base,
        "basePartNumber": base,
        "response_sha256": "a" * 64,
        "evidence_file": "sample/original-response-03.txt",
        "icpn": icpn,
    }


def make_rollup(entries):
    return {
        "type": "microchip-source-pinned-disjoint-dfp-evidence-merger",
        "manufacturer": "Microchip",
        "original_dfp_index_sha256": target.gates.PINNED_DFP_SOURCE,
        "manufacturer_population_complete": False,
        "global_active_denominator": None,
        "production_write_authorized": False,
        "commercial_sku_denominator_established": False,
        "unique_exact_prefix_research_candidates": len(entries),
        "ordering_candidates": entries,
    }


class ReverseCoverage(unittest.TestCase):
    def test_no_original_source_gives_only_frozen_p0_observations(self):
        report = target.build()
        self.assertEqual(report["p0_target_cfg_count"], 9)
        self.assertEqual(report["p1_target_only_cfg_count"], 2)
        self.assertEqual(report["frozen_dfp_p0_names"], 364)
        self.assertEqual(report["frozen_dfp_p1_names"], 12)
        self.assertEqual(report["research_icpn_candidate_count_from_other_stage_not_joined"], 24051)
        self.assertIsNone(report["exact_icpn_cfg_candidate_count"])
        self.assertIsNone(report["icpn_denominator_joined_in_this_run"])
        self.assertEqual(report["icpn_rows"], [])
        self.assertFalse(report["production_write_authorized"])

    def test_direct_exact_and_reviewed_alias_only(self):
        entries = [
            {"icpn":"ATSAMD21G18A-MU", "sources":[source(
                "ATSAMD21G18A-MU","ATSAMD21G18","ATSAMD21G18A")]},
            {"icpn":"ATSAMD51G18A-AU", "sources":[source(
                "ATSAMD51G18A-AU","ATSAMD51G18A")]},
            {"icpn":"PIC32MX110F016B-50I/SP","sources":[source(
                "PIC32MX110F016B-50I/SP","PIC32MX110F016B")]},
            {"icpn":"ATSAML21E18A-MU","sources":[source(
                "ATSAML21E18A-MU","ATSAML21E18A")]},
            {"icpn":"ATSAMD21G18A-MF","sources":[source(
                "ATSAMD21G18A-MF","ATSAMD21G18","WRONG_ALIAS")]},
            {"icpn":"AVR32DA28-I/SP","sources":[source(
                "AVR32DA28-I/SP","AVR32DA28")]},
            {"icpn":"ATSAMD21G18A-TR","sources":[source(
                "ATSAMD21G18A-TR","ATSAMD21G18"),source(
                "ATSAMD21G18A-TR","ATSAMD21G18A")]},
            {"icpn":"PIC16F777-I/SP","sources":[source(
                "PIC16F777-I/SP","","PIC16F777")]},
        ]
        rows, states, counts=target.join_icpns({},sample_index(),make_rollup(entries))
        byid={r["icpn"]:r for r in rows}
        self.assertEqual(byid["ATSAMD21G18A-MU"]["mapping_state"],
                         "REVIEWED_MANUFACTURER_ALIAS_CFG_CANDIDATE")
        self.assertEqual(byid["ATSAMD21G18A-MU"]["base_device"],"ATSAMD21G18")
        self.assertEqual(byid["ATSAMD51G18A-AU"]["openocd_target_cfg"],
                         "tcl/target/atsame5x.cfg")
        self.assertEqual(byid["PIC32MX110F016B-50I/SP"]["openocd_target_cfg"],
                         "tcl/target/pic32mx.cfg")
        self.assertEqual(byid["ATSAML21E18A-MU"]["mapping_state"],
                         "P1_TARGET_ONLY_CFG_CANDIDATE")
        self.assertIsNone(byid["ATSAMD21G18A-MF"]["openocd_target_cfg"])
        self.assertIsNone(byid["AVR32DA28-I/SP"]["openocd_target_cfg"])
        self.assertEqual(byid["AVR32DA28-I/SP"]["mapping_state"],
                         "NO_DFP_NAME_CFG_CROSSWALK")
        self.assertEqual(byid["ATSAMD21G18A-TR"]["mapping_state"],
                         "CONFLICTING_MANUFACTURER_BASE")
        self.assertEqual(byid["PIC16F777-I/SP"]["mapping_state"],
                         "UNKNOWN_MANUFACTURER_BASE")
        self.assertTrue(all(r["software_supported_claimed"] is False for r in rows))
        self.assertEqual(sum(states.values()),8)
        self.assertEqual(sum(counts.values()),4)

    def test_unverified_icpn_source_or_leaked_authority_fails_closed(self):
        valid=make_rollup([
            {"icpn":"ATSAMD51G18A-AU","sources":[source(
                "ATSAMD51G18A-AU","ATSAMD51G18A")]}])
        for prop,value in (("manufacturer_population_complete",True),
                           ("production_write_authorized",True),
                           ("global_active_denominator",24051),
                           ("original_dfp_index_sha256","0"*64)):
            with self.subTest(prop=prop):
                bogus=deepcopy(valid)
                bogus[prop]=value
                with self.assertRaises(ValueError):
                    target.join_icpns({},sample_index(),bogus)
        broken=deepcopy(valid)
        broken["ordering_candidates"][0]["sources"][0]["response_sha256"]="BAD"
        with self.assertRaisesRegex(ValueError,"source link"):
            target.join_icpns({},sample_index(),broken)
        duplicated=deepcopy(valid)
        duplicated["ordering_candidates"].append(
            deepcopy(duplicated["ordering_candidates"][0]))
        duplicated["unique_exact_prefix_research_candidates"]=2
        with self.assertRaisesRegex(ValueError,"duplicate commercial ICPN"):
            target.join_icpns({},sample_index(),duplicated)

    def test_no_rollup_join_without_original_dfp(self):
        with self.assertRaisesRegex(ValueError,"actual pinned original DFP"):
            target.build(None,make_rollup([]))

    def test_full_source_requires_all_thirteen_disjoint_archives(self):
        with self.assertRaisesRegex(ValueError, "13|12 shard"):
            target.replay_all_original_batch_sources("/synthetic/dfp", [
                ("original-16-batches", "/synthetic/old"),
                ("shard-0", "/synthetic/shard-0")])
        with self.assertRaisesRegex(ValueError, "unapproved"):
            target.replay_all_original_batch_sources("/synthetic/dfp", [
                ("original-16-batches", "/synthetic/old")] +
                [("shard-0", "/synthetic/path") for _ in range(12)])
        with self.assertRaisesRegex(ValueError, "original manufacturer DFP"):
            target.replay_all_original_batch_sources(None, [
                ("original-16-batches", "/synthetic/old")] +
                [(f"shard-{n}", f"/synthetic/shard-{n}") for n in range(12)])

    def test_full_source_frozen_audit_rejects_missing_query_replays(self):
        # The actual GitHub CI also repeats the complete 13 source archives.
        # Mocked objects below only exercise the immutable audit gate.
        audit = {
            "original_dfp_index_sha256": target.gates.PINNED_DFP_SOURCE,
            "planned_dfp_queries": 3198,
            "planned_batches": 321,
            "batch_archives_with_valid_capture_attestation": 313,
            "batches_quarantined_due_to_missing_attestation_after_worker_timeouts": 8,
            "complete_positive_exact_prefix_queries": 2753,
            "fully_replayed_zero_exact_prefix_queries": 68,
            "unique_exact_prefix_candidates_without_conflicts": 23276,
            "raw_lifecycle_conflicts": 0,
            "verified_original_source_response_links": 23427,
        }
        expected = {
            "supported_text_search_seeds": 3198,
            "batch_count": 321,
        }
        result = {
            "observed_batch_archives": 321,
            "replayed_positive_exact_prefix_queries": 2753,
            "replayed_zero_exact_prefix_queries": 68,
            "unique_exact_prefix_research_candidates": 23276,
            "conflicting_lifecycle_identity_count": 0,
            "replayed_queries": 2821,
            "production_write_authorized": False,
            "ordering_candidates": [{"sources": [{}]} for _ in range(23276)],
            "not_archived_batch_ids": [],
            "batch_reports": (
                [{"batch_id": f"valid-{n}", "state": "fully_replayed"}
                 for n in range(313)] +
                [{"batch_id": f"quarantine-{n}", "state": "entire_batch_quarantined"}
                 for n in range(8)]),
        }
        sources = [("original-16-batches", "/synthetic/old")] + [
            (f"shard-{n}", f"/synthetic/shard-{n}") for n in range(12)]
        inventory = {"source_bytes_sha256": target.gates.PINNED_DFP_SOURCE}
        with patch.object(target, "archived_inventory", return_value=inventory), \
             patch.object(target.batch_plan, "plan_inventory", return_value=expected), \
             patch.object(target.full_mcp, "build", return_value=result), \
             patch("pathlib.Path.read_text", side_effect=[
                 __import__("json").dumps({"gate_1b_surface_audit": {
                     "dfp_index_observation": {"raw_index_sha256":
                         target.gates.PINNED_DFP_SOURCE}}}),
                 __import__("json").dumps(audit),
                 __import__("json").dumps({"gate_1b_surface_audit": {
                     "dfp_index_observation": {"raw_index_sha256":
                         target.gates.PINNED_DFP_SOURCE}}}),
                 __import__("json").dumps(audit)]):
            output, summary = target.replay_all_original_batch_sources(
                "/synthetic/dfp", sources)
            self.assertEqual(summary["historical_research_icpn_candidates_replayed"],23276)
            self.assertEqual(summary["exact_prefix_queries_replayed"],2821)
            self.assertFalse(summary["manufacturer_whole_population_known"])
            corrupted = deepcopy(result)
            corrupted["replayed_positive_exact_prefix_queries"] = 2752
            with patch.object(target.full_mcp, "build", return_value=corrupted):
                with self.assertRaisesRegex(ValueError, "audited"):
                    target.replay_all_original_batch_sources("/synthetic/dfp",sources)

    def test_original_dfp_index_rejects_case_insensitive_duplicates(self):
        lock,_=target.source_lock()
        # First forcefully reject malicious re-used source SHA rather than
        # trusting only its 3,717 population count.
        fixture={"manufacturer":"Microchip",
                 "source_bytes_sha256":"0"*64}
        with self.assertRaisesRegex(ValueError,"pinned original"):
            target.cfg_index(lock,fixture)


if __name__=="__main__":
    unittest.main()
