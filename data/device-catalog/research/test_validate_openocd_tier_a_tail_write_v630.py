import csv,unittest
import validate_openocd_tier_a_tail_write_v630 as v
from openocd_backend_evolution_v630 import BackendEvolutionError,backend_state,bindings,rewind_v630_backend

class TestTierATailWriteV630(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary=v.validate()
        with v.L4.open(newline="",encoding="utf-8") as h:
            cls.current=list(csv.DictReader(h))
        cls.pre=rewind_v630_backend(cls.current,"STM32L4")
        cls.post=[dict(r) for r in cls.pre]
        by={r["icpn"]:r for r in cls.post}
        for icpn,b in bindings().items():
            for f in v.BACKEND_FIELDS: by[icpn][f]=b[f]

    def test_repository_prewrite_ready(self):
        self.assertEqual(self.summary["repository_write_state"],"pre")
        self.assertFalse(self.summary["approval"]["owner_approval_received"])
        self.assertFalse(self.summary["write_state"]["production_write_applied"])

    def test_exact_post_simulation_and_rewind(self):
        self.assertEqual(backend_state(self.pre,"STM32L4"),"pre")
        self.assertEqual(backend_state(self.post,"STM32L4"),"post")
        self.assertEqual(
          {r["icpn"]:r for r in rewind_v630_backend(self.post,"STM32L4")},
          {r["icpn"]:r for r in self.pre},
        )

    def test_partial_application_fails_closed(self):
        mixed=[dict(r) for r in self.pre];by={r["icpn"]:r for r in mixed}
        b=bindings()["STM32L496WGY6PTR"]
        for f in v.BACKEND_FIELDS: by["STM32L496WGY6PTR"][f]=b[f]
        with self.assertRaises(BackendEvolutionError):
            backend_state(mixed,"STM32L4")

    def test_g4_remains_blocked(self):
        self.assertEqual(self.summary["g4_state"],"BLOCKED_NO_CANONICAL_PACKAGE_ROUTE")

if __name__=="__main__": unittest.main()
