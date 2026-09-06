from __future__ import annotations

import unittest

import ab_benchmark as harness
import score_ab_benchmark as scorer


def run_with_evidence(evidence: dict) -> dict:
    return {
        "status": "success",
        "context": {
            "datasheet_physical_pages": [0],
            "programming_manual_physical_pages": [0],
        },
        "response": {
            "observed": {"value": 1},
            "evidence": evidence,
        },
    }


class EvidenceCitationPathTest(unittest.TestCase):
    def test_canonical_full_response_observed_path_is_cited(self):
        run = run_with_evidence({
            "$.observed.value": [
                {"source_id": harness.DS_SOURCE_ID, "physical_page_index": 0}
            ]
        })
        score = scorer.score_run(run, {"value": 1})
        self.assertEqual(score["exact_accuracy"], 1.0)
        self.assertEqual(score["uncited_assertion_count"], 0)
        self.assertEqual(score["unsupported_inference_proxy_count"], 0)
        self.assertEqual(score["unexpected_evidence_path_count"], 0)
        self.assertEqual(score["legacy_evidence_path_count"], 0)

    def test_legacy_observed_root_path_remains_readable_for_retained_runs(self):
        run = run_with_evidence({
            "$.value": [
                {"source_id": harness.DS_SOURCE_ID, "physical_page_index": 0}
            ]
        })
        score = scorer.score_run(run, {"value": 1})
        self.assertEqual(score["uncited_assertion_count"], 0)
        self.assertEqual(score["legacy_evidence_path_count"], 1)
        self.assertEqual(score["paths"]["legacy_evidence"], ["$.value"])

    def test_unrelated_evidence_path_does_not_satisfy_citation(self):
        run = run_with_evidence({
            "$.observed.other": [
                {"source_id": harness.DS_SOURCE_ID, "physical_page_index": 0}
            ]
        })
        score = scorer.score_run(run, {"value": 1})
        self.assertEqual(score["uncited_assertion_count"], 1)
        self.assertEqual(score["unsupported_inference_proxy_count"], 1)
        self.assertEqual(score["unexpected_evidence_path_count"], 1)


if __name__ == "__main__":
    unittest.main()
