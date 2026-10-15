"""Synthetic negative tests; CI separately replays real Microchip originals."""
import copy
import unittest

import microchip_phase1_p0_information_ledger_v1 as phase1


H = "a" * 64


def row(n, config, state):
    alias = state == "REVIEWED_MANUFACTURER_ALIAS_CFG_CANDIDATE"
    base = "ATSAMD21G18" if alias else f"BASE{n:06d}"
    return {
        "icpn": f"DEMO{n:06d}-MU",
        "base_device": base,
        "dfp_device_name": "ATSAMD21G18A" if alias else base,
        "openocd_target_cfg": config,
        "mapping_state": state,
        "manufacturer_base_identity_evidence":
            "ORIGINAL_MICROCHIP_MCP_RESPONSE_REPLAYED_IN_THIS_COMMAND",
        "original_mcp_response_sha256_refs": [H],
        "production_write_authorized": False,
        "software_supported_claimed": False,
        "cfg_applicability_reviewed": False,
    }


def synthetic_upstream():
    rows = []
    n = 0
    for cfg, count in phase1.P0_CFGS.items():
        for _ in range(count):
            state = ("REVIEWED_MANUFACTURER_ALIAS_CFG_CANDIDATE"
                     if n < 23 else "EXACT_DFP_NAME_CFG_CANDIDATE")
            rows.append(row(n, cfg, state))
            n += 1
    for i in range(phase1.EXPECTED_P1):
        r = row(n, "tcl/target/atsaml1x.cfg", "P1_TARGET_ONLY_CFG_CANDIDATE")
        rows.append(r)
        n += 1
    while n < phase1.EXPECTED_ALL:
        r = row(n, "", "NO_DFP_NAME_CFG_CROSSWALK")
        r["openocd_target_cfg"] = None
        rows.append(r)
        n += 1
    return {
        "schema_version": 1, "manufacturer": "Microchip",
        "scope": "reverse_openocd_cfg_to_dfp_base_to_source_linked_research_icpn",
        "openocd_release": "0.12.0",
        "all_icpn_original_bytes_replayed_in_this_command": True,
        "original_dfp_observation_available_in_this_run": True,
        "original_dfp_index_sha256_required":
            "9a00c71e262882687219fce322169435a36d45ac06d0a26bf146c4d6a5db83b0",
        "p0_target_cfg_count": 9, "p1_target_only_cfg_count": 2,
        "actual_original_dfp_p0_names_replayed": 364,
        "actual_original_dfp_p1_names_replayed": 12,
        "icpn_denominator_joined_in_this_run": phase1.EXPECTED_ALL,
        "production_write_authorized": False,
        "cfg_software_supported_claimed": False,
        "phase2_programming_authorized": False,
        "phase3_compatibility_authorized": False,
        "full_batch_original_source_replay": {
            "historical_research_icpn_candidates_replayed": phase1.EXPECTED_ALL,
            "original_batch_directories_observed": 321,
            "original_batch_archives_replayed": 313,
            "quarantined_batch_archives_not_admitted": 8,
            "exact_prefix_queries_replayed": 2821,
            "source_replay_status": "REPLAYED_AGAINST_PINNED_ORIGINAL_BYTES",
        },
        "icpn_rows": rows,
        "icpn_mapping_state_counts": {
            "EXACT_DFP_NAME_CFG_CANDIDATE": 2414,
            "REVIEWED_MANUFACTURER_ALIAS_CFG_CANDIDATE": 23,
            "P1_TARGET_ONLY_CFG_CANDIDATE": 126,
            "NO_DFP_NAME_CFG_CROSSWALK": 20713,
        },
    }


class MicrochipP0Phase1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = synthetic_upstream()

    def test_projection_exact_cohort_and_13_independent_fields(self):
        out = phase1.build(self.data, upstream_bytes_sha256=H)
        self.assertEqual(out["p0_icpn_count"], 2437)
        self.assertEqual(len(out["records"]), 2437)
        self.assertEqual(out["p0_cfg_research_candidate_counts"], phase1.P0_CFGS)
        self.assertEqual(out["p0_mapping_states"], phase1.P0_STATES)
        self.assertEqual(out["record_level_phase1_information_complete"], 0)
        self.assertEqual(out["field_unknown_denominator"], 10)
        self.assertFalse(out["phase1_p0_information_complete_claimed"])
        self.assertFalse(out["catalog_publication_authorized"])
        self.assertFalse(out["openocd_software_supported_claimed"])
        self.assertFalse(out["original_manufacturer_bytes_replayed_by_this_projection"])
        for name in ("manufacturer", "icpn", "base_device"):
            self.assertEqual(out["per_field_coverage"][name]["VERIFIED"], 2437)
            self.assertEqual(out["per_field_coverage"][name]["UNKNOWN"], 0)
        for name in phase1.UNKNOWN_FIELDS:
            self.assertEqual(out["per_field_coverage"][name]["UNKNOWN"], 2437)
            self.assertEqual(out["per_field_coverage"][name]["VERIFIED"], 0)
        example = out["records"][0]
        self.assertEqual(set(example["fields"]), set(phase1.FIELDS))
        self.assertEqual(example["internal_identity_admission"], "NOT_ADMITTED")
        self.assertIsNone(example["fields"]["vdd"]["value"])
        self.assertIsNone(example["fields"]["temperature"]["value"])
        self.assertTrue(example["fields"]["base_device"]["source_locator"].endswith(
            "/ basePartNumber"))

    def test_missing_original_sha_and_wrong_source_authority_fail_closed(self):
        source = copy.deepcopy(self.data)
        source["original_dfp_index_sha256_required"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source-locked"):
            phase1.build(source, upstream_bytes_sha256=H)
        source = copy.deepcopy(self.data)
        source["all_icpn_original_bytes_replayed_in_this_command"] = False
        with self.assertRaises(ValueError):
            phase1.build(source, upstream_bytes_sha256=H)
        source = copy.deepcopy(self.data)
        source["full_batch_original_source_replay"]["quarantined_batch_archives_not_admitted"] = 0
        with self.assertRaisesRegex(ValueError, "quarantine"):
            phase1.build(source, upstream_bytes_sha256=H)

    def test_duplicate_icpn_and_cfg_distribution_drift_rejected(self):
        source = copy.deepcopy(self.data)
        source["icpn_rows"][1]["icpn"] = source["icpn_rows"][0]["icpn"]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            phase1.build(source, upstream_bytes_sha256=H)
        source = copy.deepcopy(self.data)
        source["icpn_rows"][0]["openocd_target_cfg"] = "tcl/target/pic32mx.cfg"
        with self.assertRaisesRegex(ValueError, "distribution"):
            phase1.build(source, upstream_bytes_sha256=H)

    def test_unverified_field_or_false_supported_rejected(self):
        changed = copy.deepcopy(self.data)
        changed["icpn_rows"][0]["original_mcp_response_sha256_refs"] = ["notsha"]
        with self.assertRaisesRegex(ValueError, "original MCP response"):
            phase1.build(changed, upstream_bytes_sha256=H)
        changed = copy.deepcopy(self.data)
        changed["icpn_rows"][0]["software_supported_claimed"] = True
        with self.assertRaisesRegex(ValueError, "qualification"):
            phase1.build(changed, upstream_bytes_sha256=H)

    def test_no_family_fields_promoted_or_fabricated(self):
        with self.assertRaisesRegex(ValueError, "invented"):
            phase1.status_field("UNKNOWN", 100)
        with self.assertRaisesRegex(ValueError, "original manufacturer source"):
            phase1.status_field("VERIFIED", 256, unit="KB", scope="family")
        self.assertEqual(phase1.status_field("UNKNOWN")["value"], None)


if __name__ == "__main__":
    unittest.main()
