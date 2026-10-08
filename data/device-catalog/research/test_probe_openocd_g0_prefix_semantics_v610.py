import unittest
import probe_openocd_g0_prefix_semantics_v610 as v
class T(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.rows,_,cls.s=v.build()
 def test_cardinality(self): self.assertEqual(len(self.rows),12)
 def test_fail_closed(self):
  self.assertFalse(self.s["claims"]["g0_prefix_policy_authorized"])
  self.assertFalse(self.s["claims"]["identifier_promoted"])
  self.assertTrue(all(r["production_write_authorized"]=="false" for r in self.rows))
if __name__=="__main__":unittest.main()
