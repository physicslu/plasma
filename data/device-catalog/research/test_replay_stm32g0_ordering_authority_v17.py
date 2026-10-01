import unittest
import replay_stm32g0_ordering_authority_v17 as r

class TestG0OrderingAuthorityV17(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows,cls.summary=r.build()
    def test_all_359_decode(self):
        self.assertEqual(self.summary["fully_metadata_decoded_exact"],359)
        self.assertEqual(len(self.rows),359)
    def test_all_88_gap_bases_decode(self):
        self.assertEqual(self.summary["unique_base_devices"],88)
    def test_no_backend_gate(self):
        self.assertFalse(self.summary["backend_route_gates_metadata_decode"])
    def test_no_publication(self):
        self.assertFalse(self.summary["production_write_authorized"])
    def test_observed_package_surface(self):
        self.assertEqual({x["package"] for x in self.rows},
                         {"LQFP","UFQFPN","WLCSP","TSSOP","SO8N","UFBGA"})

if __name__=="__main__": unittest.main()
