from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("post_review_disposition", HERE / "post_review_disposition.py")
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class DispositionContractTests(unittest.TestCase):
    def candidate(self, cid="candidate-a"):
        value = {"candidate_id": cid, "statement": "Manufacturer statement.", "evidence": [{"source_id": "nxp_kl25_rm_rev3", "pdf_page_number": 425, "source_sha256": module.CONTRACT["manufacturer_sources"]["nxp_kl25_rm_rev3"], "locator": "27.3.3.1 CCIF"}]}
        value["candidate_digest"] = module.canonical_digest(value, "candidate_digest")
        return value

    def artifacts(self):
        fact = {"fact_id": "fact-a", "fact_digest": "a" * 64}
        view = {"units": [{"primary_unit_id": "unit-a", "facts": [fact]}]}
        verdict_row = {"primary_unit_id": "unit-a", "fact_id": "fact-a", "fact_digest": "a" * 64, **module.PASS}
        verdict = {"fact_verdicts": [verdict_row]}
        row = {"primary_unit_id": "unit-a", "fact_id": "fact-a", "fact_digest": "a" * 64, "action": "ACCEPT", "projection_state": "KNOWLEDGE_ONLY", "rationale": "Reviewed knowledge retained.", "candidates": [self.candidate()]}
        artifact = {"schema_version": "0.1.0", "artifact_type": "post_review_disposition", "source": module.CONTRACT["source"], "dispositions": [row]}
        artifact["artifact_digest"] = module.canonical_digest(artifact, "artifact_digest")
        return view, verdict, artifact

    def test_accept_is_knowledge_only_and_not_automatic_admission(self):
        view, verdict, artifact = self.artifacts()
        result = module.validate_disposition(view, verdict, artifact)
        self.assertEqual(result["candidate_count"], 1)
        self.assertFalse(module.CONTRACT["trust_boundary"]["accept_implies_canonical_admission"])

    def test_fact_digest_drift_fails_closed(self):
        view, verdict, artifact = self.artifacts()
        artifact["dispositions"][0]["fact_digest"] = "b" * 64
        artifact["artifact_digest"] = module.canonical_digest(artifact, "artifact_digest")
        with self.assertRaises(module.DispositionError):
            module.validate_disposition(view, verdict, artifact)

    def test_transform_requires_explicit_candidate_review(self):
        _, _, artifact = self.artifacts()
        artifact["dispositions"][0]["action"] = "NARROW"
        artifact["artifact_digest"] = module.canonical_digest(artifact, "artifact_digest")
        review = {"candidate_reviews": []}
        review["review_digest"] = module.canonical_digest(review, "review_digest")
        with self.assertRaisesRegex(module.DispositionError, "explicit local review"):
            module.validate_candidate_review(artifact, review)


if __name__ == "__main__":
    unittest.main()
