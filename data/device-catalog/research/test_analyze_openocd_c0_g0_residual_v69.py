import unittest
import analyze_openocd_c0_g0_residual_v69 as v
class T(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.rows,_,cls.s=v.build()
 def test_counts(self):
  self.assertEqual(len(self.rows),28); self.assertEqual(self.s["family_counts"],{"STM32C0":16,"STM32G0":12})
 def test_fail_closed(self):
  self.assertTrue(all(r["production_write_authorized"]=="false" for r in self.rows))
  self.assertTrue(all(x is False for x in self.s["claims"].values()))
if __name__=="__main__":unittest.main()
