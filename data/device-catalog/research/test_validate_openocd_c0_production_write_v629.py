import csv
import unittest

import validate_openocd_c0_production_write_v629 as v629
from openocd_backend_evolution_v629 import (
    BackendEvolutionError,
    backend_state,
    rewind_v629_backend,
)


class TestOpenOCDC0ProductionWriteV629(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary=v629.validate()
        with v629.C0.open(newline="",encoding="utf-8") as handle:
            cls.post_rows=list(csv.DictReader(handle))
        cls.pre_rows=rewind_v629_backend(cls.post_rows,"STM32C0")

    def test_repository_is_exact_postwrite(self):
        self.assertEqual(self.summary["repository_write_state"],"post")
        self.assertEqual(self.summary["changed_exact_count"],5)
        self.assertTrue(self.summary["approval"]["owner_approval_received"])
        self.assertTrue(self.summary["approval"]["production_write_authorized"])
        self.assertTrue(self.summary["approval"]["merge_after_green_ci_authorized"])
        self.assertTrue(self.summary["write_state"]["production_write_applied"])
        self.assertEqual(
            self.summary["write_state"]["applied_commit"],
            "37d61baf8e6d978116836ebdf40940a15ee42cb6",
        )

    def test_postimage_rewinds_to_frozen_preimage(self):
        self.assertEqual(backend_state(self.post_rows,"STM32C0"),"post")
        self.assertEqual(backend_state(self.pre_rows,"STM32C0"),"pre")
        self.assertEqual(
            self.summary["inverse_c0_preimage_git_blob_sha"],
            "c015e131082a3f9fe32ca226a9b2ada71a5c350d",
        )

    def test_partial_application_fails_closed(self):
        mixed=[dict(r) for r in self.pre_rows]
        post={r["icpn"]:r for r in self.post_rows}
        mixed_by={r["icpn"]:r for r in mixed}
        icpn="STM32C011D6Y6TR"
        for field in (
            "cmsis_device_name","existing_identifier","existing_identifier_kind",
            "mapping_status","openocd_target_config",
        ):
            mixed_by[icpn][field]=post[icpn][field]
        with self.assertRaises(BackendEvolutionError):
            backend_state(mixed,"STM32C0")

    def test_poststate(self):
        self.assertEqual(self.summary["mapped"],4059)
        self.assertEqual(self.summary["no_mapping"],570)
        expected=self.summary["expected_poststate"]
        self.assertEqual(expected["active_openocd_route"],3980)
        self.assertEqual(expected["active_openocd_route_denominator"],4550)
        self.assertEqual(expected["active_openocd_route_coverage_percent"],87.4725)


if __name__=="__main__":
    unittest.main()
