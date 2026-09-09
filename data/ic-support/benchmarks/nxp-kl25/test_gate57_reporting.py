#!/usr/bin/env python3
"""Gate 5.7 reporting regression: skipped screening must never be reported PASS."""
from __future__ import annotations

import unittest

from test_live_bounded_qualification import KL25LiveBoundedQualificationTest


class Gate57ReportingRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        KL25LiveBoundedQualificationTest.setUpClass()

    def test_integrity_failure_marks_screening_not_reached(self):
        case = KL25LiveBoundedQualificationTest(methodName="test_length_failure_is_retained_without_retry_and_rejected_integrity")
        case.setUp()
        self.addCleanup(case.doCleanups)

        def transport(**kwargs):
            response = case.transport(**kwargs)
            if len(case.calls) == 1:
                response["done_reason"] = "length"
                response["usage"]["generation_tokens"] = 8192
            return response

        result, _, report = case.execute(transport=transport)
        self.assertEqual(result["aggregate"]["status"], "REJECTED_INTEGRITY")
        self.assertEqual(report["status"], "REJECTED_INTEGRITY")
        self.assertEqual(report["schema_version"], "0.1.1")
        self.assertEqual(report["semantic_screening"]["status"], "NOT_REACHED")
        self.assertEqual(report["semantic_screening"]["errors"], [])
        self.assertIn("not executed", report["semantic_screening"]["note"].lower())


if __name__ == "__main__":
    unittest.main()
