import unittest

import prepare_openocd_production_transaction_v620 as p


class TestOpenOCDProductionTransactionV620(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.txn, cls.before, cls.after = p.build()

    def test_scope(self):
        self.assertEqual(self.txn["promotion_exact_count"], 17)
        self.assertEqual(self.txn["affected_family_count"], 3)
        self.assertEqual(set(self.before), {"STM32F3","STM32G0","STM32L1","MANIFEST"})
        self.assertEqual(set(self.after), {"STM32F3","STM32G0","STM32L1","MANIFEST"})

    def test_partition(self):
        self.assertEqual(self.txn["prestate"]["mapped"], 4037)
        self.assertEqual(self.txn["prestate"]["no_mapping"], 592)
        self.assertEqual(self.txn["poststate_if_approved"]["mapped"], 4054)
        self.assertEqual(self.txn["poststate_if_approved"]["no_mapping"], 575)

    def test_route_projection(self):
        post = self.txn["poststate_if_approved"]
        self.assertEqual(post["active_openocd_route"], 3975)
        self.assertEqual(post["active_openocd_route_denominator"], 4550)
        self.assertAlmostEqual(post["active_openocd_route_coverage_percent"], 87.3626)

    def test_governance(self):
        g = self.txn["governance"]
        self.assertFalse(g["production_write_authorized"])
        self.assertTrue(g["requires_explicit_owner_approval"])
        self.assertTrue(g["backend_fields_only"])
        self.assertTrue(g["identity_fields_immutable"])
        self.assertTrue(g["manifest_integrity_updates_only"])
        self.assertTrue(g["rollback_preimages_frozen"])
        self.assertFalse(g["generic_one_char_generalization_authorized"])
        self.assertTrue(g["exact_set_bridge_only"])
        self.assertFalse(g["programming_verified_claimed"])
        self.assertFalse(g["engineering_verified_claimed"])
        self.assertFalse(g["hil_verified_claimed"])

    def test_hashes_and_rollback(self):
        for row in self.txn["affected_files"].values():
            self.assertEqual(len(row["pre_sha256"]), 64)
            self.assertEqual(len(row["post_sha256"]), 64)
            self.assertEqual(row["rollback_preimage_sha256"], row["pre_sha256"])


if __name__ == "__main__":
    unittest.main()
