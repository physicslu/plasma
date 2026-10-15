"""Negative tests for OpenOCD CFG-FIRST Microchip ICPN/Base Device crosswalk."""
from copy import deepcopy
import unittest

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
                "PIC16F777-I/SP","")]},
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
