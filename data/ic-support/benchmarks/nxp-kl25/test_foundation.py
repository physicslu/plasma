from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class KL25FoundationTest(unittest.TestCase):
    def test_contracts_fail_closed_after_source_lock_until_evidence_is_retained(self):
        acquisition = json.loads((HERE / "source-acquisition-contract.json").read_text(encoding="utf-8"))
        foundation = json.loads((HERE / "evidence-foundation-contract.json").read_text(encoding="utf-8"))
        self.assertTrue(acquisition["trust_boundary"]["source_lock_complete"])
        self.assertFalse(acquisition["trust_boundary"]["evidence_pack_admission"])
        self.assertFalse(foundation["admission"]["evidence_pack"])
        self.assertFalse(foundation["admission"]["semantic_extraction"])
        self.assertFalse(foundation["admission"]["production"])
        self.assertFalse(foundation["admission"]["destructive_security_operation"])

    def test_reference_manual_can_own_programming_authority_role(self):
        acquisition = json.loads((HERE / "source-acquisition-contract.json").read_text(encoding="utf-8"))
        roles = {s["document_role"] for s in acquisition["sources"]}
        self.assertIn("datasheet", roles)
        self.assertIn("reference_manual_programming_authority", roles)
        foundation = json.loads((HERE / "evidence-foundation-contract.json").read_text(encoding="utf-8"))
        self.assertFalse(foundation["cross_vendor_invariants"]["programming_manual_document_name_required"])
        self.assertTrue(foundation["cross_vendor_invariants"]["stm32_register_names_are_not_canonical_semantics"])

    def test_retained_source_lock_matches_captured_swpc_identities(self):
        lock = json.loads((HERE / "source-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["targets"], ["MKL25Z128VLK4"])
        by_id = {source["source_id"]: source for source in lock["sources"]}
        self.assertEqual(
            by_id["nxp_kl25_ds_rev5"]["integrity"],
            {
                "algorithm": "sha256",
                "digest": "e42271b7f612ac1b0812001e62bef10d217be4a61dbee5bb0a1e5c4076209a3b",
                "byte_length": 1280088,
            },
        )
        self.assertEqual(
            by_id["nxp_kl25_rm_rev3"]["integrity"],
            {
                "algorithm": "sha256",
                "digest": "7911a7d9f8192fa317960feabc9377d0fd81a9b90d31f8070cae9612cb237241",
                "byte_length": 6637765,
            },
        )
        self.assertTrue(lock["trust_boundary"]["source_lock_complete"])
        self.assertFalse(lock["trust_boundary"]["evidence_pack_admission"])

    def test_source_lock_capture_hashes_exact_pdf_bytes(self):
        contract = json.loads((HERE / "source-acquisition-contract.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = {}
            for i, source in enumerate(contract["sources"]):
                payload = b"%PDF-1.4\n" + bytes([65 + i]) * (2048 + i)
                path = root / source["local_filename"]
                path.write_bytes(payload)
                expected[source["source_id"]] = (hashlib.sha256(payload).hexdigest(), len(payload))
            output = root / "source-lock.json"
            subprocess.run(
                [sys.executable, str(HERE / "capture_source_lock.py"), "--source-dir", str(root), "--output", str(output)],
                check=True,
                capture_output=True,
                text=True,
            )
            lock = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(lock["source_lock_id"], "nxp-kl25-source-lock-v0")
            for source in lock["sources"]:
                digest, size = expected[source["source_id"]]
                self.assertEqual(source["integrity"]["digest"], digest)
                self.assertEqual(source["integrity"]["byte_length"], size)

    def test_source_lock_capture_rejects_tiny_or_non_pdf_artifact(self):
        contract = json.loads((HERE / "source-acquisition-contract.json").read_text(encoding="utf-8"))
        for bad_payload in (b"Not Found\n", b"X" * 2048):
            with self.subTest(payload=bad_payload[:16]):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    for index, source in enumerate(contract["sources"]):
                        payload = bad_payload if index == 0 else b"%PDF-1.4\n" + b"A" * 2048
                        (root / source["local_filename"]).write_bytes(payload)
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(HERE / "capture_source_lock.py"),
                            "--source-dir",
                            str(root),
                            "--output",
                            str(root / "source-lock.json"),
                        ],
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
