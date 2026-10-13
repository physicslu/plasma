import sys
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from microchip_product_api_probe_v1 import ProbeError, validate_page


def valid_page(page=1):
    return {
        "totalRecords": 3,
        "totalPages": 2,
        "pagenumber": page,
        "pagesize": 2,
        "data": [{
            "part_number": f"PIC10F202-E/{'MC' if page == 1 else 'OT'}",
            "base_part_number": "pic10f202",
            "lifecycle_status": "REL",
        }],
    }


class MicrochipProductApiProbeTests(unittest.TestCase):
    def test_accepts_valid_page_envelope_and_preserves_raw_status(self):
        page = validate_page(valid_page(), 1, 2)
        self.assertEqual(page["data"][0]["lifecycle_status"], "REL")

    def test_rejects_inconsistent_total_pages(self):
        page = valid_page()
        page["totalPages"] = 3
        with self.assertRaisesRegex(ProbeError, "totalPages"):
            validate_page(page, 1, 2)

    def test_rejects_wrong_returned_page_number(self):
        with self.assertRaisesRegex(ProbeError, "pagenumber"):
            validate_page(valid_page(2), 1, 2)

    def test_rejects_row_missing_exact_part_number(self):
        page = valid_page()
        del page["data"][0]["part_number"]
        with self.assertRaisesRegex(ProbeError, "part_number"):
            validate_page(page, 1, 2)

    def test_rejects_row_missing_raw_lifecycle_field(self):
        page = valid_page()
        del page["data"][0]["lifecycle_status"]
        with self.assertRaisesRegex(ProbeError, "lifecycle_status"):
            validate_page(page, 1, 2)


if __name__ == "__main__":
    unittest.main()
