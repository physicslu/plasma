import unittest
from nxp_277_final_review_v8 import baseline,pdf_table,LPC

class ReviewTests(unittest.TestCase):
    def test_277_previous_source_lock(self):
        self.assertEqual(len(baseline()),277)
    def test_pdf_exact_table(self):
        text="Table 2. Ordering options\nLPC5502JHI48 64 48\nLPC5504JHI48 128 80\nLPC5506JHI48 256 96\n"
        self.assertEqual(pdf_table(text),LPC)
        for corrupt in (text.replace("128 80","128 81"),text.replace("256 96","256 0"),text+ "LPC5502JHI48 64 48\n"):
            with self.assertRaises(ValueError):pdf_table(corrupt)

if __name__=="__main__":unittest.main()
