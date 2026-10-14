import unittest
from nxp_38_p1_bounded_v12 import build,serialize,LEDGER,STOP

class TestP1OneBoundedCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.all=build()
        cls.ids={r["icpn"]:r for r in cls.all}
    def test_exact_38_all_reviewed_once(self):
        self.assertEqual(len(self.all),38)
        self.assertEqual(sum(r["investigation_group"]=="LPC802_804" for r in self.all),18)
        self.assertEqual(sum(r["investigation_group"]=="K32L2" for r in self.all),20)
        self.assertEqual(set(r["bounded_review_status"] for r in self.all),{"COMPLETED_FOR_PINNED_COMMIT"})
    def test_no_false_positive_support(self):
        self.assertTrue(all(r["openocd_software_support_state"]=="CANDIDATE" and
            r["driver_geometry_qualified"]=="false" and
            r["public_catalog_visibility_authorized"]=="false" and
            r["stop_or_reopen_rule"]==STOP for r in self.all))
        self.assertEqual(self.ids["LPC804M101JDH20J"]["investigation_group"],"LPC802_804")
        self.assertEqual(self.ids["K32L2B11VFT0AR"]["target_family_source_path"],"")
    def test_ledger_replay(self):
        self.assertEqual(LEDGER.read_bytes(),serialize(self.all))
if __name__=="__main__":unittest.main()
