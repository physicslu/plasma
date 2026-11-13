#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("v632",HERE/"validate_openocd_post_v631_gap_v632.py")
M=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(M)

class TestV632(unittest.TestCase):
    def test_final_gap_is_fully_dispositioned(self):
        r=M.validate()
        self.assertEqual(r["exact_count"],465)
        self.assertEqual(r["runtime_candidate_exact_count"],190)
        self.assertEqual(r["blocked_backend_exact_count"],275)
        self.assertEqual(r["family_counts"],{"STM32C5":172,"STM32H5":190,"STM32N6":32,"STM32WB0":24,"STM32WL3":47})

if __name__=="__main__":
    unittest.main()
