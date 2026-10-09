import unittest
import prepare_openocd_c0_production_transaction_v628 as p

class TestOpenOCDC0ProductionTransactionV628(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.txn,cls.before,cls.after=p.build()

    def test_scope(self):
        self.assertEqual(self.txn["promotion_exact_count"],5)
        self.assertEqual(self.txn["affected_family_count"],1)
        self.assertEqual(self.txn["affected_family_counts"],{"STM32C0":5})
        self.assertEqual(set(self.before),{"STM32C0","MANIFEST"})
        self.assertEqual(set(self.after),{"STM32C0","MANIFEST"})

    def test_successor_is_explicit_source(self):
        route=self.txn["route_inventory"]
        self.assertEqual(route["path"],"data/device-catalog/research/openocd-parts-canonical-v627.csv")
        self.assertEqual(route["git_blob_sha"],"81e44f6a6df902f3b206d06bfac38e37ec74630b")
        self.assertEqual(route["row_count"],7661)

    def test_partition_projection(self):
        self.assertEqual(self.txn["prestate"]["mapped"],4054)
        self.assertEqual(self.txn["prestate"]["no_mapping"],575)
        self.assertEqual(self.txn["poststate_if_approved"]["mapped"],4059)
        self.assertEqual(self.txn["poststate_if_approved"]["no_mapping"],570)

    def test_route_projection(self):
        post=self.txn["poststate_if_approved"]
        self.assertEqual(post["active_openocd_route"],3980)
        self.assertEqual(post["active_openocd_route_denominator"],4550)
        self.assertAlmostEqual(post["active_openocd_route_coverage_percent"],87.4725)

    def test_hashes_and_rollback(self):
        for row in self.txn["affected_files"].values():
            self.assertEqual(len(row["pre_sha256"]),64)
            self.assertEqual(len(row["post_sha256"]),64)
            self.assertEqual(row["rollback_preimage_sha256"],row["pre_sha256"])
            self.assertEqual(row["rollback_preimage_git_blob_sha"],row["pre_git_blob_sha"])

    def test_governance(self):
        g=self.txn["governance"]
        self.assertFalse(g["production_write_authorized"])
        self.assertTrue(g["requires_explicit_owner_approval"])
        self.assertTrue(g["backend_fields_only"])
        self.assertTrue(g["identity_fields_immutable"])
        self.assertTrue(g["manifest_integrity_updates_only"])
        self.assertTrue(g["route_inventory_successor_explicit"])
        self.assertTrue(g["exact_set_only"])
        self.assertFalse(g["programming_profile_binding_claimed"])
        self.assertFalse(g["programming_verified_claimed"])
        self.assertFalse(g["engineering_verified_claimed"])
        self.assertFalse(g["hil_verified_claimed"])

if __name__=="__main__":
    unittest.main()
