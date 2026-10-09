import csv
import io
import unittest

import prepare_openocd_c0_production_transaction_v628 as v628
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
        cls.txn,cls.before,cls.after=v628.build()
        cls.pre_rows=list(csv.DictReader(io.StringIO(cls.before["STM32C0"].decode())))
        cls.post_rows=list(csv.DictReader(io.StringIO(cls.after["STM32C0"].decode())))

    def test_prewrite_repository_is_ready(self):
        self.assertEqual(self.summary["repository_write_state"],"pre")
        self.assertFalse(self.summary["approval"]["owner_approval_received"])
        self.assertFalse(self.summary["write_state"]["production_write_applied"])

    def test_simulated_postimage_is_complete_not_partial(self):
        self.assertEqual(backend_state(self.pre_rows,"STM32C0"),"pre")
        self.assertEqual(backend_state(self.post_rows,"STM32C0"),"post")

    def test_postimage_rewinds_to_exact_pre_backend_semantics(self):
        rewound=rewind_v629_backend(self.post_rows,"STM32C0")
        by_before={r["icpn"]:r for r in self.pre_rows}
        by_after={r["icpn"]:r for r in rewound}
        self.assertEqual(by_before,by_after)

    def test_partial_application_fails_closed(self):
        mixed=[dict(r) for r in self.pre_rows]
        post={r["icpn"]:r for r in self.post_rows}
        mixed_by={r["icpn"]:r for r in mixed}
        icpn="STM32C011D6Y6TR"
        mixed_by[icpn].update({
            key:post[icpn][key]
            for key in (
                "cmsis_device_name","existing_identifier","existing_identifier_kind",
                "mapping_status","openocd_target_config"
            )
        })
        with self.assertRaises(BackendEvolutionError):
            backend_state(mixed,"STM32C0")

    def test_expected_poststate(self):
        self.assertEqual(self.summary["expected_poststate"]["mapped"],4059)
        self.assertEqual(self.summary["expected_poststate"]["no_mapping"],570)
        self.assertEqual(self.summary["expected_poststate"]["active_openocd_route"],3980)
        self.assertEqual(
            self.summary["expected_poststate"]["active_openocd_route_coverage_percent"],
            87.4725,
        )


if __name__=="__main__":
    unittest.main()
