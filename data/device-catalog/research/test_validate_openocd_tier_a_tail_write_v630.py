import csv,unittest
import validate_openocd_tier_a_tail_write_v630 as v
from openocd_backend_evolution_v630 import BackendEvolutionError,backend_state,bindings,rewind_v630_backend

class TestTierATailWriteV630(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary=v.validate()
        with v.L4.open(newline="",encoding="utf-8") as h:
            cls.post=list(csv.DictReader(h))
        cls.pre=rewind_v630_backend(cls.post,"STM32L4")

    def test_repository_is_exact_postwrite(self):
        self.assertEqual(self.summary["repository_write_state"],"post")
        self.assertEqual(self.summary["l4_changed_exact_count"],2)
        self.assertTrue(self.summary["approval"]["owner_approval_received"])
        self.assertTrue(self.summary["approval"]["l4_production_write_authorized"])
        self.assertTrue(self.summary["approval"]["merge_after_green_ci_authorized"])
        self.assertTrue(self.summary["write_state"]["production_write_applied"])
        self.assertEqual(
            self.summary["write_state"]["applied_commit"],
            "e2d7809ed7c3f22354a9d62f28b4d5a57a4ed6df",
        )

    def test_exact_post_and_rewind(self):
        self.assertEqual(backend_state(self.post,"STM32L4"),"post")
        self.assertEqual(backend_state(self.pre,"STM32L4"),"pre")
        self.assertEqual(
          self.summary["inverse_l4_preimage_git_blob_sha"],
          "081aeaa80ed558785ba062255cd322fdfa505ff4",
        )

    def test_partial_application_fails_closed(self):
        mixed=[dict(r) for r in self.pre];by={r["icpn"]:r for r in mixed}
        b=bindings()["STM32L496WGY6PTR"]
        for f in v.BACKEND_FIELDS: by["STM32L496WGY6PTR"][f]=b[f]
        with self.assertRaises(BackendEvolutionError):
            backend_state(mixed,"STM32L4")

    def test_g4_remains_blocked(self):
        self.assertEqual(self.summary["g4_state"],"BLOCKED_NO_CANONICAL_PACKAGE_ROUTE")
        self.assertEqual(self.summary["mapped"],4061)
        self.assertEqual(self.summary["no_mapping"],568)

if __name__=="__main__": unittest.main()
