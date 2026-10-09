import csv,io,unittest
import prepare_openocd_tier_a_tail_v630 as p
from openocd_backend_evolution_v630 import BackendEvolutionError,backend_state,rewind_v630_backend

class TestTierATailV630(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary,cls.before,cls.after=p.build()
        cls.pre=list(csv.DictReader(io.StringIO(cls.before["STM32L4"].decode())))
        cls.post=list(csv.DictReader(io.StringIO(cls.after["STM32L4"].decode())))

    def test_l4_scope_and_projection(self):
        self.assertEqual(self.summary["l4_exact_count"],2)
        self.assertEqual(self.summary["l4_route_identifier"],"STM32L496WGYxP")
        self.assertEqual(self.summary["l4_route_kind"],"cmsis_device_name")
        self.assertEqual(self.summary["poststate_if_l4_approved"]["mapped"],4061)
        self.assertEqual(self.summary["poststate_if_l4_approved"]["no_mapping"],568)
        self.assertEqual(self.summary["poststate_if_l4_approved"]["active_openocd_route"],3982)

    def test_dual_state_and_rewind(self):
        self.assertEqual(backend_state(self.pre,"STM32L4"),"pre")
        self.assertEqual(backend_state(self.post,"STM32L4"),"post")
        self.assertEqual(
            {r["icpn"]:r for r in rewind_v630_backend(self.post,"STM32L4")},
            {r["icpn"]:r for r in self.pre},
        )

    def test_partial_write_fails_closed(self):
        mixed=[dict(r) for r in self.pre]
        post={r["icpn"]:r for r in self.post}
        by={r["icpn"]:r for r in mixed}
        icpn="STM32L496WGY6PTR"
        for f in ("cmsis_device_name","existing_identifier","existing_identifier_kind","mapping_status","openocd_target_config"):
            by[icpn][f]=post[icpn][f]
        with self.assertRaises(BackendEvolutionError):
            backend_state(mixed,"STM32L4")

    def test_g4_stays_blocked(self):
        g=self.summary["g4"]
        self.assertEqual(g["state"],"BLOCKED_NO_CANONICAL_PACKAGE_ROUTE")
        self.assertFalse(g["production_write_authorized"])
        self.assertEqual(g["package"],"WLCSP")

if __name__=="__main__":
    unittest.main()
