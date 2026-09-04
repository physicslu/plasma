from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from preprocessing import manifest_digest
from semantic_pack import (
    SemanticPackError,
    build_catalog,
    build_semantic_artifacts,
    materialize_evidence_text,
)

HERE = Path(__file__).resolve().parent
POLICY = HERE / "policies" / "st-ds5319-rev20-programming-v0.json"
OUTLINE = HERE / "fixtures" / "st-ds5319-rev20-outline-v0.json"
TAXONOMY = HERE / "taxonomy-v0.json"
RULES = HERE / "rules-v0.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class DS5319SemanticPackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load(POLICY)
        self.outline = load(OUTLINE)
        self.taxonomy = load(TAXONOMY)
        self.rules = load(RULES)
        source = self.policy["source"]
        self.source_lock = {
            "source_lock_id": self.policy["source_lock_id"],
            "sources": [
                {
                    "source_id": source["source_id"],
                    "integrity": {
                        "algorithm": source["algorithm"],
                        "digest": source["digest"],
                        "byte_length": source["byte_length"],
                    },
                }
            ],
        }

    def make_manifest(
        self,
        *,
        page_text_overrides: dict[int, str] | None = None,
        extra_structural_units: list[dict] | None = None,
    ):
        page_text_overrides = page_text_overrides or {}
        normalized_pages = [page_text_overrides.get(index, f"synthetic DS5319 page {index}\n") for index in range(114)]
        pages = [
            {
                "pdf_page_index": index,
                "printed_page_label": None,
                "normalized_content_sha256": sha(text),
            }
            for index, text in enumerate(normalized_pages)
        ]
        units = [
            {
                "unit_id": f"page-{index:04d}",
                "type": "PAGE",
                "pdf_page_start": index,
                "pdf_page_end": index,
                "printed_page_label": None,
                "heading": None,
                "label": None,
                "normalized_content_sha256": pages[index]["normalized_content_sha256"],
            }
            for index in range(114)
        ]
        for position, (label, heading, start, end) in enumerate(self.outline["sections"]):
            units.append(
                {
                    "unit_id": f"section-{position:03d}",
                    "type": "SECTION_CANDIDATE",
                    "pdf_page_start": start,
                    "pdf_page_end": end,
                    "printed_page_label": None,
                    "heading": heading,
                    "label": label,
                    "section_level": label.count(".") + 1,
                }
            )
        for position, (kind, label, heading, page_index) in enumerate(self.outline["anchors"]):
            units.append(
                {
                    "unit_id": f"anchor-{position:03d}",
                    "type": kind,
                    "pdf_page_start": page_index,
                    "pdf_page_end": page_index,
                    "printed_page_label": None,
                    "heading": heading,
                    "label": label,
                }
            )
        for position, (kind, label, heading, page_index) in enumerate(self.outline["toc_decoys"]):
            unit = {
                "unit_id": f"toc-decoy-{position:03d}",
                "type": kind,
                "pdf_page_start": page_index,
                "pdf_page_end": page_index,
                "printed_page_label": None,
                "heading": heading,
                "label": label,
            }
            if kind == "SECTION_CANDIDATE":
                unit["section_level"] = label.count(".") + 1
            units.append(unit)
        units.extend(extra_structural_units or [])

        source = self.policy["source"]
        manifest = {
            "artifact_type": "document_structure_manifest",
            "schema_version": "0.1.0",
            "source_lock_id": self.policy["source_lock_id"],
            "source": {
                "source_id": source["source_id"],
                "algorithm": source["algorithm"],
                "digest": source["digest"],
                "byte_length": source["byte_length"],
            },
            "preprocessor": {
                "name": "pdftotext",
                "version": "pdftotext version synthetic-ds5319",
                "arguments": ["-layout", "-enc", "UTF-8"],
            },
            "normalization": {
                "contract_id": "plasma-document-normalization-v0",
                "digest": "a" * 64,
            },
            "builder": {
                "builder_id": "plasma-document-preprocessor-v0",
                "implementation_sha256": "b" * 64,
            },
            "normalized_document_sha256": sha("\f".join(normalized_pages)),
            "page_count": 114,
            "pages": pages,
            "structural_units": units,
            "references": [],
            "semantic_classification_performed": False,
            "canonical_dataset_admission": False,
            "production_admission": False,
        }
        manifest["manifest_digest"] = manifest_digest(manifest)
        return manifest, normalized_pages

    def build(self, *, manifest=None, normalized_pages=None, policy=None):
        if manifest is None:
            manifest, normalized_pages = self.make_manifest()
        return build_semantic_artifacts(
            manifest=manifest,
            policy=policy or self.policy,
            source_lock=self.source_lock,
            taxonomy=self.taxonomy,
            rules=self.rules,
            builder_sha256="c" * 64,
            normalized_pages=normalized_pages,
        )

    def test_real_policy_outline_resolves_without_toc_aliasing(self):
        manifest, pages = self.make_manifest()
        artifacts = self.build(manifest=manifest, normalized_pages=pages)
        self.assertEqual(artifacts["pack"]["pack_id"], "st-ds5319-rev20-programming-evidence-v0")
        self.assertLess(len(artifacts["pack"]["included_units"]), 114)
        self.assertGreater(len(artifacts["pack"]["included_units"]), 20)

    def test_page_classification_separates_relevant_and_excluded_regions(self):
        manifest, _ = self.make_manifest()
        catalog = build_catalog(
            manifest=manifest,
            policy=self.policy,
            source_lock=self.source_lock,
            taxonomy=self.taxonomy,
            builder_sha256="c" * 64,
        )
        by_page = {unit["pdf_page_index"]: unit for unit in catalog["units"]}
        self.assertEqual(by_page[5]["classification"], "EXCLUDE")
        self.assertEqual(by_page[18]["classification"], "EXCLUDE")
        self.assertEqual(by_page[45]["classification"], "EXCLUDE")
        self.assertEqual(by_page[90]["classification"], "EXCLUDE")
        self.assertEqual(by_page[14]["classification"], "MUST_INCLUDE")
        self.assertEqual(by_page[53]["classification"], "MUST_INCLUDE")
        self.assertEqual(by_page[103]["classification"], "MUST_INCLUDE")
        self.assertIn("ORDERING", by_page[103]["categories"])

    def test_one_pack_is_reused_by_c8_and_cb_bindings(self):
        artifacts = self.build()
        binding = artifacts["binding"]
        self.assertEqual({target["icpn"] for target in binding["targets"]}, {"STM32F103C8T6", "STM32F103CBT6"})
        self.assertEqual({tuple(target["pack_ids"]) for target in binding["targets"]}, {(artifacts["pack"]["pack_id"],)})
        self.assertEqual(set(artifacts["bundles"]), {"STM32F103C8T6", "STM32F103CBT6"})

    def test_document_explicit_dependency_can_rescue_excluded_page(self):
        extra = [
            {
                "unit_id": "figure-99",
                "type": "FIGURE_CANDIDATE",
                "pdf_page_start": 90,
                "pdf_page_end": 90,
                "printed_page_label": None,
                "heading": "Synthetic dependency target",
                "label": "Figure 99",
            }
        ]
        manifest, pages = self.make_manifest(
            page_text_overrides={14: "Selected boot evidence. See Figure 99.\n"},
            extra_structural_units=extra,
        )
        artifacts = self.build(manifest=manifest, normalized_pages=pages)
        page90 = "st_ds5319_rev20-page-0090"
        included = {entry["unit_id"]: entry for entry in artifacts["pack"]["included_units"]}
        self.assertIn(page90, included)
        self.assertTrue(any(reason.startswith("DEPENDENCY_FROM:") for reason in included[page90]["inclusion_reasons"]))

    def test_ambiguous_reference_does_not_gain_dependency_authority(self):
        extra = [
            {
                "unit_id": "figure-99-a",
                "type": "FIGURE_CANDIDATE",
                "pdf_page_start": 90,
                "pdf_page_end": 90,
                "printed_page_label": None,
                "heading": "First target",
                "label": "Figure 99",
            },
            {
                "unit_id": "figure-99-b",
                "type": "FIGURE_CANDIDATE",
                "pdf_page_start": 91,
                "pdf_page_end": 91,
                "printed_page_label": None,
                "heading": "Second target",
                "label": "Figure 99",
            },
        ]
        manifest, pages = self.make_manifest(
            page_text_overrides={14: "Selected boot evidence. See Figure 99.\n"},
            extra_structural_units=extra,
        )
        artifacts = self.build(manifest=manifest, normalized_pages=pages)
        included = {entry["unit_id"] for entry in artifacts["pack"]["included_units"]}
        self.assertNotIn("st_ds5319_rev20-page-0090", included)
        self.assertNotIn("st_ds5319_rev20-page-0091", included)

    def test_missing_required_section_fails_closed(self):
        manifest, pages = self.make_manifest()
        manifest["structural_units"] = [
            unit for unit in manifest["structural_units"]
            if not (unit.get("type") == "SECTION_CANDIDATE" and unit.get("label") == "2.3.8" and unit.get("heading") == "Boot modes")
        ]
        manifest["manifest_digest"] = manifest_digest(manifest)
        with self.assertRaises(SemanticPackError):
            self.build(manifest=manifest, normalized_pages=pages)

    def test_source_lock_drift_fails_closed(self):
        manifest, pages = self.make_manifest()
        drifted = copy.deepcopy(self.policy)
        drifted["source"]["digest"] = "d" * 64
        with self.assertRaises(SemanticPackError):
            self.build(manifest=manifest, normalized_pages=pages, policy=drifted)

    def test_policy_change_changes_catalog_and_pack_identity(self):
        manifest, pages = self.make_manifest()
        left = self.build(manifest=manifest, normalized_pages=pages)
        changed = copy.deepcopy(self.policy)
        changed["page_rules"][0]["categories"].append("ELECTRICAL")
        right = self.build(manifest=manifest, normalized_pages=pages, policy=changed)
        self.assertNotEqual(left["catalog"]["catalog_digest"], right["catalog"]["catalog_digest"])
        self.assertNotEqual(left["pack"]["pack_digest"], right["pack"]["pack_digest"])

    def test_materialized_context_contains_only_pack_pages(self):
        manifest, pages = self.make_manifest()
        artifacts = self.build(manifest=manifest, normalized_pages=pages)
        text = materialize_evidence_text(
            normalized_pages=pages,
            catalog=artifacts["catalog"],
            pack=artifacts["pack"],
        )
        self.assertIn("physical-page 0", text)
        self.assertIn("physical-page 14", text)
        self.assertNotIn("physical-page 90 ", text)
        self.assertNotIn("synthetic DS5319 page 90\n", text)

    def test_structural_policy_metadata_remains_non_authoritative_for_production(self):
        artifacts = self.build()
        self.assertFalse(artifacts["pack"]["canonical_dataset_admission"])
        self.assertFalse(artifacts["pack"]["production_admission"])
        self.assertFalse(artifacts["binding"]["canonical_dataset_admission"])
        self.assertFalse(artifacts["binding"]["production_admission"])


if __name__ == "__main__":
    unittest.main()
