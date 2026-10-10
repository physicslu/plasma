import csv, unittest

import validate_openocd_final_write_v631 as v
from openocd_backend_evolution_v631 import (
    BackendEvolutionError,
    BACKEND_FIELDS,
    backend_state,
    bindings,
    rewind_v631_backend,
)

class TestOpenOCDFinalWriteV631(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary=v.validate()

    def test_repository_is_exact_complete_pre_or_approved_post(self):
        state=self.summary["repository_write_state"]
        self.assertIn(state,("pre","post"))
        self.assertEqual(
            self.summary["family_states"],
            {"STM32F3":state,"STM32F7":state,"STM32G4":state},
        )
        if state=="pre":
            self.assertEqual((self.summary["mapped"],self.summary["no_mapping"]),(4061,568))
            self.assertFalse(self.summary["approval"]["owner_approval_received"])
            self.assertFalse(self.summary["write_state"]["production_write_applied"])
        else:
            self.assertEqual((self.summary["mapped"],self.summary["no_mapping"]),(4164,465))
            self.assertTrue(self.summary["approval"]["owner_approval_received"])
            self.assertTrue(self.summary["approval"]["route_inventory_write_authorized"])
            self.assertTrue(self.summary["approval"]["production_write_authorized"])
            self.assertTrue(self.summary["approval"]["merge_after_green_ci_authorized"])
            self.assertTrue(self.summary["write_state"]["route_inventory_write_applied"])
            self.assertTrue(self.summary["write_state"]["production_write_applied"])

    def test_each_family_exact_post_simulation_rewinds(self):
        expected=bindings()
        for family,path in v.FAMILY_PATHS.items():
            with path.open(newline="",encoding="utf-8") as h:
                current=list(csv.DictReader(h))
            pre=rewind_v631_backend(current,family)
            self.assertEqual(backend_state(pre,family),"pre")
            post=[dict(r) for r in pre]
            by={r["icpn"]:r for r in post}
            for icpn,b in expected.items():
                if b["family"]!=family: continue
                for field in BACKEND_FIELDS:
                    by[icpn][field]=b[field]
            self.assertEqual(backend_state(post,family),"post")
            self.assertEqual(
                {r["icpn"]:r for r in rewind_v631_backend(post,family)},
                {r["icpn"]:r for r in pre},
            )

    def test_partial_family_application_fails_closed(self):
        family="STM32F7"
        with v.FAMILY_PATHS[family].open(newline="",encoding="utf-8") as h:
            rows=list(csv.DictReader(h))
        expected=bindings()
        first=next(icpn for icpn,b in expected.items() if b["family"]==family)
        by={r["icpn"]:r for r in rows}
        if self.summary["repository_write_state"]=="pre":
            for field in BACKEND_FIELDS:
                by[first][field]=expected[first][field]
        else:
            by[first].update({
                "cmsis_device_name":"",
                "existing_identifier":"",
                "existing_identifier_kind":"",
                "mapping_status":"no_mapping",
                "openocd_target_config":"",
            })
        with self.assertRaises(BackendEvolutionError):
            backend_state(rows,family)

    def test_projection_and_blocked_boundary(self):
        self.assertEqual(self.summary["safe_exact_count"],103)
        self.assertEqual(self.summary["blocked_exact_count"],465)
        self.assertEqual(self.summary["active_denominator"],4550)
        expected=(3982,87.5165) if self.summary["repository_write_state"]=="pre" else (4085,89.7802)
        self.assertEqual(
            (self.summary["active_openocd_route"],self.summary["coverage_percent"]),
            expected,
        )

if __name__=="__main__":
    unittest.main()
