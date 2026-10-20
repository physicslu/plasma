"""No SWPC/Z2: F1-B staging must fail closed on substitute artifacts."""
import unittest
from unittest.mock import patch
from pl.hil.fixed_b1_staging import (
    B1Blocked, CANDIDATE_BIN_SHA256, derive_candidate, from_evidence_zip,
)


class CandidateConversionContract(unittest.TestCase):
    def test_no_real_evidence_means_no_candidate(self):
        with self.assertRaisesRegex(B1Blocked, "PROVENANCE"):
            derive_candidate(b"FAKE", b"HWH", {})

    def test_bit_and_hwh_are_both_pinned(self):
        bad = dict(source_sha="5473176a5ca6a04f9fe9359b4406c38208f9498f",
                   bit_sha256="ad7c525385ae265f8f479acbe4227b2ef97fee51d68ba85b8efeff804bc740f6",
                   hwh_sha256="a367f820e375c7770b7b71c4c7dfee42b64c64eb57fc3d0cdf906a944100ce2e",
                   execution_path="path2-cli", physical_image_loaded="NOT_RUN")
        for field in ("source_sha", "bit_sha256", "hwh_sha256", "execution_path",
                      "physical_image_loaded"):
            with self.subTest(field=field), self.assertRaisesRegex(B1Blocked, "PROVENANCE"):
                derive_candidate(b"wrong", b"wrong", bad | {field: "spoofed"})

    def test_missing_or_ambiguous_zip_members(self):
        from pathlib import Path
        import tempfile
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "evidence.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("unrelated/file.txt", "not an artifact")
            with self.assertRaisesRegex(B1Blocked, "MEMBERS"):
                from_evidence_zip(archive)
            with zipfile.ZipFile(archive, "a") as z:
                z.writestr("a/system_wrapper.bit", "fake")
                z.writestr("b/system_wrapper.bit", "duplicate")
                z.writestr("a/system.hwh", "fake")
                z.writestr("_temp/plasma-path2-vivado-host-receipt.json", "{}")
            with self.assertRaisesRegex(B1Blocked, "MEMBERS"):
                from_evidence_zip(archive)

    def test_literal_candidate_digest_is_fixed(self):
        self.assertEqual(
            CANDIDATE_BIN_SHA256,
            "c351f668094a2b841426c64681d44c76cb8c14b61766d90a0e10adcf3a22a3c3")


if __name__ == "__main__":
    unittest.main()
