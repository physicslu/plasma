from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from preprocessing import (
    PreprocessingError,
    build_manifest_from_extracted_text,
    manifest_digest,
    normalize_page_text,
    normalization_digest,
    sha256_bytes,
    split_physical_pages,
    validate_manifest,
    verify_locked_pdf,
)

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "synthetic-document-v0.json"
NORMALIZATION = HERE / "normalization-v0.json"
SCHEMA = HERE / "schema" / "document-structure-v0.schema.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class DocumentPreprocessingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = load(FIXTURE)
        self.normalization = load(NORMALIZATION)
        self.source = copy.deepcopy(self.fixture["source"])
        self.tool = copy.deepcopy(self.fixture["tool"])
        self.builder_sha256 = self.fixture["builder_sha256"]
        self.source_lock = {
            "source_lock_id": self.fixture["source_lock_id"],
            "sources": [copy.deepcopy(self.source)],
        }

    def build(self, text: str, *, normalization=None, tool=None, builder_sha256=None):
        manifest = build_manifest_from_extracted_text(
            source_lock_id=self.fixture["source_lock_id"],
            source=self.source,
            extracted_text=text,
            tool=tool or self.tool,
            normalization=normalization or self.normalization,
            builder_sha256=builder_sha256 or self.builder_sha256,
        )
        validate_manifest(manifest, source_lock=self.source_lock, normalization=normalization or self.normalization)
        return manifest

    def test_schema_and_normalization_contract_are_parseable(self):
        schema = load(SCHEMA)
        self.assertEqual(schema["$id"], "plasma://ic-support/evidence-pack/document-structure-v0")
        self.assertEqual(self.normalization["normalization_contract_id"], "plasma-document-normalization-v0")

    def test_crlf_and_trailing_whitespace_normalize_to_same_manifest(self):
        left = self.build(self.fixture["extracted_text_crlf"])
        right = self.build(self.fixture["extracted_text_lf"])
        self.assertEqual(left["manifest_digest"], right["manifest_digest"])
        self.assertEqual(left["normalized_document_sha256"], right["normalized_document_sha256"])

    def test_every_physical_page_survives_even_without_heading(self):
        manifest = self.build(self.fixture["extracted_text_lf"])
        page_units = [unit for unit in manifest["structural_units"] if unit["type"] == "PAGE"]
        self.assertEqual(manifest["page_count"], 3)
        self.assertEqual(len(page_units), 3)
        self.assertEqual(page_units[-1]["pdf_page_start"], 2)
        self.assertIsNone(page_units[-1]["heading"])

    def test_numbered_sections_get_deterministic_hierarchy_page_spans(self):
        manifest = self.build(self.fixture["extracted_text_lf"])
        sections = [unit for unit in manifest["structural_units"] if unit["type"] == "SECTION_CANDIDATE"]
        by_label = {unit["label"]: unit for unit in sections}
        self.assertEqual(by_label["1"]["section_level"], 1)
        self.assertEqual(by_label["1"]["pdf_page_start"], 0)
        self.assertEqual(by_label["1"]["pdf_page_end"], 1)
        self.assertEqual(by_label["2"]["section_level"], 1)
        self.assertEqual(by_label["2"]["pdf_page_start"], 1)
        self.assertEqual(by_label["2"]["pdf_page_end"], 2)

    def test_nested_section_closes_at_next_same_or_higher_level(self):
        text = "1 Parent\n\f1.1 Child\n\f1.1.1 Leaf\n\f2 Next top\n"
        manifest = self.build(text)
        sections = {unit["label"]: unit for unit in manifest["structural_units"] if unit["type"] == "SECTION_CANDIDATE"}
        self.assertEqual(sections["1"]["pdf_page_end"], 3)
        self.assertEqual(sections["1.1"]["pdf_page_end"], 3)
        self.assertEqual(sections["1.1.1"]["pdf_page_end"], 3)
        self.assertEqual(sections["2"]["pdf_page_end"], 3)

    def test_heading_and_table_detection_are_candidates_only(self):
        manifest = self.build(self.fixture["extracted_text_lf"])
        types = {unit["type"] for unit in manifest["structural_units"]}
        self.assertIn("SECTION_CANDIDATE", types)
        self.assertIn("TABLE_CANDIDATE", types)
        self.assertFalse(manifest["semantic_classification_performed"])
        self.assertFalse(manifest["canonical_dataset_admission"])
        self.assertFalse(manifest["production_admission"])

    def test_multicolumn_inline_caption_is_detected(self):
        text = "- left-column bullet                         Table 1. Device summary\n"
        manifest = self.build(text)
        tables = [unit for unit in manifest["structural_units"] if unit["type"] == "TABLE_CANDIDATE"]
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["label"], "Table 1")
        self.assertEqual(tables[0]["heading"], "Device summary")

    def test_plain_table_reference_is_not_misclassified_as_caption(self):
        text = "Refer to Table 11 for the values of VPOR/PDR and VPVD.\n"
        manifest = self.build(text)
        tables = [unit for unit in manifest["structural_units"] if unit["type"] == "TABLE_CANDIDATE"]
        self.assertEqual(tables, [])
        self.assertEqual(len(manifest["references"]), 1)
        self.assertEqual(manifest["references"][0]["target_label"], "Table 11")

    def test_explicit_reference_unique_match_is_not_dependency_authority(self):
        manifest = self.build(self.fixture["extracted_text_lf"])
        self.assertEqual(len(manifest["references"]), 1)
        reference = manifest["references"][0]
        self.assertEqual(reference["reference_type"], "DOCUMENT_EXPLICIT_CANDIDATE")
        self.assertEqual(reference["target_label"], "Table 3")
        self.assertEqual(reference["resolution"], "UNIQUE_LABEL_MATCH")
        self.assertIsNotNone(reference["target_unit_id"])

    def test_duplicate_structural_label_stays_ambiguous(self):
        text = "See Table 3.\n\fTable 3. First\n\fTable 3. Second\n"
        manifest = self.build(text)
        reference = manifest["references"][0]
        self.assertEqual(reference["resolution"], "AMBIGUOUS")
        self.assertIsNone(reference["target_unit_id"])

    def test_missing_structural_label_stays_not_found(self):
        manifest = self.build("See Figure 9.\n")
        reference = manifest["references"][0]
        self.assertEqual(reference["resolution"], "NOT_FOUND")
        self.assertIsNone(reference["target_unit_id"])

    def test_normalization_contract_change_changes_identity(self):
        changed = copy.deepcopy(self.normalization)
        changed["notes"] = changed["notes"] + ["synthetic contract revision"]
        left = self.build(self.fixture["extracted_text_lf"])
        right = self.build(self.fixture["extracted_text_lf"], normalization=changed)
        self.assertNotEqual(left["normalization"]["digest"], right["normalization"]["digest"])
        self.assertNotEqual(left["manifest_digest"], right["manifest_digest"])

    def test_tool_version_change_changes_identity(self):
        changed = copy.deepcopy(self.tool)
        changed["version"] = "pdftotext version synthetic-2.0"
        left = self.build(self.fixture["extracted_text_lf"])
        right = self.build(self.fixture["extracted_text_lf"], tool=changed)
        self.assertNotEqual(left["manifest_digest"], right["manifest_digest"])

    def test_builder_change_changes_identity(self):
        left = self.build(self.fixture["extracted_text_lf"])
        right = self.build(self.fixture["extracted_text_lf"], builder_sha256="c" * 64)
        self.assertNotEqual(left["manifest_digest"], right["manifest_digest"])

    def test_validator_rejects_manifest_mutation(self):
        manifest = self.build(self.fixture["extracted_text_lf"])
        manifest["pages"][0]["printed_page_label"] = "1"
        with self.assertRaises(PreprocessingError):
            validate_manifest(manifest, source_lock=self.source_lock, normalization=self.normalization)
        self.assertNotEqual(manifest["manifest_digest"], manifest_digest(manifest))

    def test_validator_rejects_page_index_gap_even_with_recomputed_digest(self):
        manifest = self.build(self.fixture["extracted_text_lf"])
        manifest["pages"][1]["pdf_page_index"] = 7
        manifest["manifest_digest"] = manifest_digest(manifest)
        with self.assertRaises(PreprocessingError):
            validate_manifest(manifest, source_lock=self.source_lock, normalization=self.normalization)

    def test_validator_rejects_duplicate_page_unit_even_with_recomputed_digest(self):
        manifest = self.build(self.fixture["extracted_text_lf"])
        duplicate = copy.deepcopy(next(unit for unit in manifest["structural_units"] if unit["type"] == "PAGE"))
        duplicate["unit_id"] = "duplicate-page-unit"
        manifest["structural_units"].append(duplicate)
        manifest["manifest_digest"] = manifest_digest(manifest)
        with self.assertRaises(PreprocessingError):
            validate_manifest(manifest, source_lock=self.source_lock, normalization=self.normalization)

    def test_validator_rejects_section_without_hierarchy_level(self):
        manifest = self.build(self.fixture["extracted_text_lf"])
        section = next(unit for unit in manifest["structural_units"] if unit["type"] == "SECTION_CANDIDATE")
        section.pop("section_level")
        manifest["manifest_digest"] = manifest_digest(manifest)
        with self.assertRaises(PreprocessingError):
            validate_manifest(manifest, source_lock=self.source_lock, normalization=self.normalization)

    def test_validator_rejects_dangling_resolved_reference(self):
        manifest = self.build(self.fixture["extracted_text_lf"])
        manifest["references"][0]["target_unit_id"] = "missing-unit"
        manifest["manifest_digest"] = manifest_digest(manifest)
        with self.assertRaises(PreprocessingError):
            validate_manifest(manifest, source_lock=self.source_lock, normalization=self.normalization)

    def test_validator_rejects_source_lock_fingerprint_drift(self):
        manifest = self.build(self.fixture["extracted_text_lf"])
        drifted = copy.deepcopy(self.source_lock)
        drifted["sources"][0]["integrity"]["digest"] = "d" * 64
        with self.assertRaises(PreprocessingError):
            validate_manifest(manifest, source_lock=drifted, normalization=self.normalization)

    def test_locked_pdf_digest_and_length_fail_closed(self):
        payload = b"synthetic locked pdf bytes"
        source = {
            "integrity": {
                "algorithm": "sha256",
                "digest": sha256_bytes(payload),
                "byte_length": len(payload),
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.pdf"
            path.write_bytes(payload)
            verify_locked_pdf(path, source)
            path.write_bytes(payload + b"changed")
            with self.assertRaises(PreprocessingError):
                verify_locked_pdf(path, source)

    def test_trailing_form_feed_fragment_does_not_create_phantom_page(self):
        self.assertEqual(split_physical_pages("one\fsecond\f"), ["one", "second"])
        self.assertEqual(split_physical_pages("one\fsecond\f\n"), ["one", "second"])

    def test_normalized_page_has_lf_and_single_terminal_newline(self):
        normalized = normalize_page_text("A  \r\nB\t\r\n\r\n", self.normalization)
        self.assertEqual(normalized, "A\nB\n")
        self.assertNotIn("\r", normalized)

    def test_normalization_digest_is_canonical(self):
        reordered = dict(reversed(list(self.normalization.items())))
        self.assertEqual(normalization_digest(self.normalization), normalization_digest(reordered))


if __name__ == "__main__":
    unittest.main()
