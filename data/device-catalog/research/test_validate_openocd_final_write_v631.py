import csv,unittest

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

    def test_prewrite_repository_is_ready(self):
        self.assertEqual(self.summary["repository_write_state"],"pre")
        self.assertEqual(self.summary["family_states"],
            {"STM32F3":"pre","STM32F7":"pre","STM32G4":"pre"})
        self.assertEqual((self.summary["mapped"],self.summary["no_mapping"]),(4061,568))
        self.assertFalse(self.summary["approval"]["owner_approval_received"])
        self.assertFalse(self.summary["write_state"]["production_write_applied"])

    def test_each_family_exact_post_simulation_rewinds(self):
        expected=bindings()
        for family,path in v.FAMILY_PATHS.items():
            with path.open(newline="",encoding="utf-8") as h:
                pre=list(csv.DictReader(h))
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
        for field in BACKEND_FIELDS:
            by[first][field]=expected[first][field]
        with self.assertRaises(BackendEvolutionError):
            backend_state(rows,family)

    def test_projection_and_blocked_boundary(self):
        self.assertEqual(self.summary["safe_exact_count"],103)
        self.assertEqual(self.summary["blocked_exact_count"],465)
        self.assertEqual(self.summary["active_openocd_route"],3982)
        self.assertEqual(self.summary["active_denominator"],4550)
        self.assertEqual(self.summary["coverage_percent"],87.5165)

if __name__=="__main__":
    unittest.main()
