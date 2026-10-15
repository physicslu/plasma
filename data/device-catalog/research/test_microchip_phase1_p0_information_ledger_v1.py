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
        source["icpn_rows"][23]["openocd_target_cfg"] = "tcl/target/pic32mx.cfg"
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

    def test_official_chart_adds_partial_only_on_exact_mcp_base(self):
        chart_rows = []
        partials = ("package", "pin_count", "flash", "ram", "vdd",
                    "temperature", "core_model")
        for i in range(341):
            base = ("BASE000023" if i == 0 else f"CHARTOTHER{i:04d}")
            fields = {}
            for n, field in enumerate(partials):
                fields[field] = {
                    "status": "PARTIAL" if i == 0 else "UNKNOWN",
                    "value": 64 if i == 0 else None,
                    "original_raw_value": "64" if i == 0 else "",
                    "original_header": field,
                    "original_unit": "KB" if field in ("flash", "ram") else None,
                    "source_tr_ordinal": i + 5,
                    "source_column_number_1based": n + 1,
                    "source_original_sha256": H,
                    "evidence_scope": "official_base_device_chart_not_exact_icpn",
                }
            chart_rows.append({
                "base_device_chart_observation": base,
                "priority": "P0",
                "exact_icpn_verified_from_chart": False,
                "fields_family_scope_only": fields,
            })
        chart = {
            "schema_version": 1,
            "policy": "ADR-0002 Phase 1 - IC Information",
            "manufacturer": "Microchip",
            "chart_scope": "microchipdirect_chart_branchID_21_mid_3_only",
            "chart_records": {"P0_source_leads": 341},
            "exact_icpn_fields_verified_from_chart": 0,
            "production_write_authorized": False,
            "catalog_publication_authorized": False,
            "source_original_sha256": H,
            "source_url": "https://www.microchipdirect.com/chart.aspx?branchID=21&mid=3",
            "p0_family_records": chart_rows,
        }
        result = phase1.build(self.data, upstream_bytes_sha256=H, chart_report=chart)
        proof = result["p0_family_chart_evidence"]
        self.assertEqual(proof["p0_icpns_exact_manufacturer_base_joined_to_chart"], 1)
        self.assertEqual(proof["p0_icpns_reviewed_manufacturer_alias_joined_to_chart"], 0)
        self.assertEqual(proof["p0_icpns_chart_linked_with_approved_identity"], 1)
        self.assertEqual(proof["p0_icpns_not_in_observed_chart"], 2436)
        self.assertEqual(len(proof["chart_unmatched_exact_icpns"]), 2436)
        self.assertEqual(sum(proof["chart_unmatched_by_research_cfg"].values()), 2436)
        self.assertEqual(proof["p0_unmatched_distinct_manufacturer_base_count"], 2414)
        self.assertEqual(len(proof["p0_official_source_acquisition_queue"]), 2414)
        self.assertTrue(all(entry["official_exact_ordering_table_state"] ==
                            "NOT_REPLAYED" for entry in
                            proof["p0_official_source_acquisition_queue"]))
        self.assertTrue(result["chart_original_bytes_replayed_by_upstream_chart_builder"])
        for field in partials:
            self.assertEqual(result["per_field_coverage"][field]["PARTIAL"], 1)
            self.assertEqual(result["per_field_coverage"][field]["UNKNOWN"], 2436)
        r = next(x for x in result["records"] if x["base_device"] == "BASE000023")
        self.assertEqual(r["fields"]["flash"]["status"], "PARTIAL")
        self.assertEqual(r["fields"]["flash"]["unit"], "KB")
        self.assertEqual(r["fields"]["flash"]["evidence_scope"],
                         "official_base_device_chart_not_exact_icpn")
        self.assertEqual(r["fields"]["base_device"]["status"], "VERIFIED")
        self.assertEqual(result["record_level_phase1_information_complete"], 0)
        broken = copy.deepcopy(chart)
        broken["p0_family_records"][0]["fields_family_scope_only"]["flash"]["source_original_sha256"] = "0"*64
        with self.assertRaisesRegex(ValueError, "provenance"):
            phase1.build(self.data, upstream_bytes_sha256=H, chart_report=broken)
        broken = copy.deepcopy(chart)
        broken["p0_family_records"][1]["base_device_chart_observation"] = "BASE000023"
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            phase1.build(self.data, upstream_bytes_sha256=H, chart_report=broken)

    def test_reviewed_mcp_base_dfp_chart_alias_is_family_partial_only(self):
        # 23 synthetic ICPNs are original-source-tagged as the *one* approved
        # SAMD21 manufacturer Base/DFP alias. This test is not manufacturer
        # original-byte replay; real CI uses the official chart and MCP data.
        fields = {}
        for n, name in enumerate(("package", "pin_count", "flash", "ram",
                                  "vdd", "temperature", "core_model")):
            fields[name] = {
                "status": "PARTIAL", "value": 64,
                "original_raw_value": "64", "original_header": name,
                "original_unit": "KB" if name in ("flash","ram") else None,
                "source_tr_ordinal": 10,
                "source_column_number_1based": n+1,
                "source_original_sha256": H,
                "evidence_scope": "official_base_device_chart_not_exact_icpn",
            }
        empty_fields = {name:{**value,"status":"UNKNOWN","value":None}
                        for name,value in fields.items()}
        chart = {
            "schema_version":1, "policy":"ADR-0002 Phase 1 - IC Information",
            "manufacturer":"Microchip",
            "chart_scope":"microchipdirect_chart_branchID_21_mid_3_only",
            "chart_records":{"P0_source_leads":341},
            "exact_icpn_fields_verified_from_chart":0,
            "production_write_authorized":False,
            "catalog_publication_authorized":False,
            "source_original_sha256":H,
            "source_url":"https://www.microchipdirect.com/chart.aspx?branchID=21&mid=3",
            "p0_family_records":[
                {"base_device_chart_observation":("ATSAMD21G18A" if n==0
                      else f"CHARTUNRELATED{n:04d}"),
                 "priority":"P0", "exact_icpn_verified_from_chart":False,
                 "fields_family_scope_only":fields if n==0 else empty_fields}
                for n in range(341)],
        }
        outcome=phase1.build(self.data, upstream_bytes_sha256=H, chart_report=chart)
        proof=outcome["p0_family_chart_evidence"]
        self.assertEqual(proof["p0_icpns_reviewed_manufacturer_alias_joined_to_chart"],23)
        self.assertEqual(proof["p0_icpns_exact_manufacturer_base_joined_to_chart"],0)
        self.assertEqual(proof["p0_icpns_not_in_observed_chart"],2414)
        self.assertEqual(proof["p0_unmatched_distinct_manufacturer_base_count"],2414)
        self.assertEqual(sum(x["exact_icpn_count"] for x in
                            proof["p0_official_source_acquisition_queue"]),2414)
        self.assertFalse(any(x["field_inference_authorized"] for x in
                             proof["p0_official_source_acquisition_queue"]))
        self.assertEqual(proof["partial_field_observation_counts"]["flash"],23)
        alias_rows=[r for r in outcome["records"] if
            r["cfg_candidate_state"] ==
                "REVIEWED_MANUFACTURER_ALIAS_CFG_CANDIDATE"]
        self.assertEqual(len(alias_rows),23)
        for item in alias_rows:
            self.assertEqual(item["base_device"],"ATSAMD21G18")
            self.assertEqual(item["dfp_name"],"ATSAMD21G18A")
            self.assertEqual(item["fields"]["package"]["status"],"PARTIAL")
            self.assertIn("reviewed_mcp_dfp_alias",
                          item["fields"]["package"]["evidence_scope"])
            self.assertFalse(item["software_supported_claimed"])
        self.assertEqual(outcome["record_level_phase1_information_complete"],0)
        fake=copy.deepcopy(self.data)
        fake["icpn_rows"][0]["base_device"]="ATSAMD21G17"
        with self.assertRaisesRegex(ValueError,"source-approved"):
            phase1.build(fake,upstream_bytes_sha256=H,chart_report=chart)
        fake=copy.deepcopy(self.data)
        fake["icpn_rows"][0]["dfp_device_name"]="ATSAMD21G17A"
        with self.assertRaisesRegex(ValueError,"source-approved"):
            phase1.build(fake,upstream_bytes_sha256=H,chart_report=chart)

    def test_no_family_fields_promoted_or_fabricated(self):
        with self.assertRaisesRegex(ValueError, "invented"):
            phase1.status_field("UNKNOWN", 100)
        with self.assertRaisesRegex(ValueError, "original manufacturer source"):
            phase1.status_field("VERIFIED", 256, unit="KB", scope="family")
        self.assertEqual(phase1.status_field("UNKNOWN")["value"], None)


if __name__ == "__main__":
    unittest.main()
