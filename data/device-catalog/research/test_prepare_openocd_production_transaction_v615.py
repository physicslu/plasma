import unittest
import prepare_openocd_production_transaction_v615 as p

class TestOpenOCDProductionTransactionV615(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.txn, cls.before, cls.after = p.build()

    def test_scope(self):
        self.assertEqual(cls := self.txn["promotion_exact_count"], 364)
        self.assertEqual(self.txn["affected_family_count"], 10)
        self.assertEqual(len(self.before), 10)
        self.assertEqual(len(self.after), 10)

    def test_governance(self):
        g = self.txn["governance"]
        self.assertFalse(g["production_write_authorized"])
        self.assertTrue(g["requires_explicit_owner_approval"])
        self.assertTrue(g["backend_fields_only"])
        self.assertTrue(g["identity_fields_immutable"])
        self.assertTrue(g["rollback_preimages_frozen"])

    def test_partition(self):
        self.assertEqual(self.txn["prestate"]["mapped"], 3673)
        self.assertEqual(self.txn["prestate"]["no_mapping"], 956)
        self.assertEqual(self.txn["poststate_if_approved"]["mapped"], 4037)
        self.assertEqual(self.txn["poststate_if_approved"]["no_mapping"], 592)

    def test_route_projection(self):
        post = self.txn["poststate_if_approved"]
        self.assertEqual(post["active_openocd_route"], 3958)
        self.assertEqual(post["active_openocd_route_denominator"], 4550)
        self.assertAlmostEqual(post["active_openocd_route_coverage_percent"], 86.9890)

    def test_hashes_present(self):
        for row in self.txn["affected_files"].values():
            self.assertEqual(len(row["pre_sha256"]), 64)
            self.assertEqual(len(row["post_sha256"]), 64)
            self.assertEqual(row["rollback_preimage_sha256"], row["pre_sha256"])

if __name__ == "__main__":
    unittest.main()
