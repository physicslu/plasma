#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCHEMA_VERSION = "0.1.0"
ARTIFACT_TYPE = "document_structure_manifest"
BUILDER_ID = "plasma-document-preprocessor-v0"
DEFAULT_NORMALIZATION = HERE / "normalization-v0.json"


class PreprocessingError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PreprocessingError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: top-level JSON must be an object")
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalization_digest(contract: dict[str, Any]) -> str:
    return canonical_sha256(contract)


def normalize_page_text(text: str, contract: dict[str, Any]) -> str:
    require(contract.get("line_endings") == "LF", "unsupported line_endings contract")
    require(contract.get("trailing_whitespace") == "strip_per_line", "unsupported trailing_whitespace contract")
    require(contract.get("terminal_newline") == "single", "unsupported terminal_newline contract")
    require(contract.get("unicode_normalization") == "NFC", "unsupported unicode normalization contract")

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFC", text)
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    return "\n".join(lines).rstrip("\n") + "\n"


def split_physical_pages(extracted_text: str) -> list[str]:
    pages = extracted_text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    require(pages, "extracted text contains no pages")
    return pages


_NUMBERED_HEADING = re.compile(r"^\s*(?P<number>\d+(?:\.\d+){0,5})\s+(?P<title>\S.*)$")
_TABLE_LABEL = re.compile(r"^\s*(?P<label>Table\s+\d+[A-Za-z]?)\s*[.:\-]\s*(?P<title>\S.*)$", re.IGNORECASE)
_FIGURE_LABEL = re.compile(r"^\s*(?P<label>Figure\s+\d+[A-Za-z]?)\s*[.:\-]\s*(?P<title>\S.*)$", re.IGNORECASE)
_EXPLICIT_REFERENCE = re.compile(r"\b(?:see|refer(?:\s+to)?|shown\s+in|described\s+in)\s+(?P<label>(?:Table|Figure)\s+\d+[A-Za-z]?)\b", re.IGNORECASE)


def canonical_label(label: str) -> str:
    words = label.strip().split()
    require(len(words) == 2, f"invalid structural label: {label}")
    return f"{words[0].title()} {words[1]}"


def structural_candidates(pages: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    units: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    label_to_units: dict[str, list[str]] = {}

    for page_index, page in enumerate(pages):
        page_unit_id = f"page-{page_index:04d}"
        units.append({
            "unit_id": page_unit_id,
            "type": "PAGE",
            "pdf_page_start": page_index,
            "pdf_page_end": page_index,
            "printed_page_label": None,
            "heading": None,
            "label": None,
            "normalized_content_sha256": sha256_bytes(page.encode("utf-8")),
        })
        for line_index, line in enumerate(page.splitlines()):
            stripped = line.strip()
            if not stripped:
                continue
            match = _NUMBERED_HEADING.match(line)
            unit_type = None
            label = None
            heading = None
            if match:
                unit_type = "SECTION_CANDIDATE"
                label = match.group("number")
                heading = match.group("title").strip()
            else:
                table = _TABLE_LABEL.match(line)
                figure = _FIGURE_LABEL.match(line)
                if table:
                    unit_type = "TABLE_CANDIDATE"
                    label = canonical_label(table.group("label"))
                    heading = table.group("title").strip()
                elif figure:
                    unit_type = "FIGURE_CANDIDATE"
                    label = canonical_label(figure.group("label"))
                    heading = figure.group("title").strip()
            if unit_type:
                unit_id = f"{unit_type.lower()}-{page_index:04d}-{line_index:04d}"
                unit = {
                    "unit_id": unit_id,
                    "type": unit_type,
                    "pdf_page_start": page_index,
                    "pdf_page_end": page_index,
                    "printed_page_label": None,
                    "heading": heading,
                    "label": label,
                    "anchor_line_index": line_index,
                    "anchor_line_sha256": sha256_bytes((stripped + "\n").encode("utf-8")),
                }
                units.append(unit)
                if unit_type in {"TABLE_CANDIDATE", "FIGURE_CANDIDATE"} and isinstance(label, str):
                    label_to_units.setdefault(label.lower(), []).append(unit_id)

            for ref_match in _EXPLICIT_REFERENCE.finditer(line):
                target_label = canonical_label(ref_match.group("label"))
                references.append({
                    "from_unit_id": page_unit_id,
                    "pdf_page_index": page_index,
                    "line_index": line_index,
                    "reference_type": "DOCUMENT_EXPLICIT_CANDIDATE",
                    "target_label": target_label,
                    "target_unit_id": None,
                    "resolution": "UNRESOLVED",
                })

    for reference in references:
        candidates = label_to_units.get(reference["target_label"].lower(), [])
        if len(candidates) == 1:
            reference["target_unit_id"] = candidates[0]
            reference["resolution"] = "UNIQUE_LABEL_MATCH"
        elif len(candidates) > 1:
            reference["resolution"] = "AMBIGUOUS"
        else:
            reference["resolution"] = "NOT_FOUND"
    return units, references


def tool_fingerprint(pdftotext: str = "pdftotext") -> dict[str, Any]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    result = subprocess.run(
        [pdftotext, "-v"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    combined = "\n".join(part.strip() for part in [result.stdout, result.stderr] if part.strip())
    version_line = combined.splitlines()[0] if combined else ""
    require(version_line, "pdftotext version output is empty")
    return {
        "name": "pdftotext",
        "version": version_line,
        "arguments": ["-layout", "-enc", "UTF-8"],
    }


def extract_pdf_text(pdf: Path, pdftotext: str = "pdftotext") -> tuple[str, dict[str, Any]]:
    tool = tool_fingerprint(pdftotext)
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    result = subprocess.run(
        [pdftotext, "-layout", "-enc", "UTF-8", str(pdf), "-"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    require(result.stdout, f"{pdf}: pdftotext produced no text")
    try:
        text = result.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PreprocessingError(f"{pdf}: pdftotext output is not UTF-8") from exc
    return text, tool


def find_locked_source(source_lock: dict[str, Any], source_id: str) -> dict[str, Any]:
    matches = [source for source in source_lock.get("sources", []) if isinstance(source, dict) and source.get("source_id") == source_id]
    require(len(matches) == 1, f"{source_id}: exact source-lock entry required")
    return matches[0]


def verify_locked_pdf(pdf: Path, source: dict[str, Any]) -> None:
    integrity = source.get("integrity")
    require(isinstance(integrity, dict), "source-lock integrity object required")
    require(integrity.get("algorithm") == "sha256", "document preprocessing v0 requires sha256 source lock")
    expected = integrity.get("digest")
    require(isinstance(expected, str) and expected, "locked sha256 required")
    actual = sha256_file(pdf)
    require(actual == expected, f"{pdf}: sha256 {actual} != locked {expected}")
    byte_length = integrity.get("byte_length")
    if isinstance(byte_length, int):
        require(pdf.stat().st_size == byte_length, f"{pdf}: byte length does not match source lock")


def manifest_digest(manifest: dict[str, Any]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    return canonical_sha256(payload)


def build_manifest_from_extracted_text(
    *,
    source_lock_id: str,
    source: dict[str, Any],
    extracted_text: str,
    tool: dict[str, Any],
    normalization: dict[str, Any],
    builder_sha256: str,
) -> dict[str, Any]:
    integrity = source["integrity"]
    raw_pages = split_physical_pages(extracted_text)
    pages = [normalize_page_text(page, normalization) for page in raw_pages]
    units, references = structural_candidates(pages)
    normalized_document = "\f".join(pages)

    manifest: dict[str, Any] = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "source_lock_id": source_lock_id,
        "source": {
            "source_id": source["source_id"],
            "algorithm": integrity["algorithm"],
            "digest": integrity["digest"],
            "byte_length": integrity.get("byte_length"),
        },
        "preprocessor": tool,
        "normalization": {
            "contract_id": normalization["normalization_contract_id"],
            "digest": normalization_digest(normalization),
        },
        "builder": {
            "builder_id": BUILDER_ID,
            "implementation_sha256": builder_sha256,
        },
        "normalized_document_sha256": sha256_bytes(normalized_document.encode("utf-8")),
        "page_count": len(pages),
        "pages": [
            {
                "pdf_page_index": index,
                "printed_page_label": None,
                "normalized_content_sha256": sha256_bytes(page.encode("utf-8")),
            }
            for index, page in enumerate(pages)
        ],
        "structural_units": units,
        "references": references,
        "semantic_classification_performed": False,
        "canonical_dataset_admission": False,
        "production_admission": False,
    }
    manifest["manifest_digest"] = manifest_digest(manifest)
    return manifest


def validate_manifest(
    manifest: dict[str, Any],
    *,
    source_lock: dict[str, Any] | None = None,
    normalization: dict[str, Any] | None = None,
) -> None:
    require(manifest.get("artifact_type") == ARTIFACT_TYPE, "manifest artifact_type mismatch")
    require(manifest.get("schema_version") == SCHEMA_VERSION, "manifest schema_version mismatch")
    require(manifest.get("manifest_digest") == manifest_digest(manifest), "manifest digest mismatch")
    require(manifest.get("semantic_classification_performed") is False, "structural manifest must not assert semantic classification")
    require(manifest.get("canonical_dataset_admission") is False, "structural manifest must deny canonical admission")
    require(manifest.get("production_admission") is False, "structural manifest must deny production admission")

    preprocessor = manifest.get("preprocessor")
    require(isinstance(preprocessor, dict), "preprocessor fingerprint required")
    require(preprocessor.get("name") == "pdftotext", "unsupported preprocessor")
    require(preprocessor.get("arguments") == ["-layout", "-enc", "UTF-8"], "preprocessor arguments mismatch")
    require(isinstance(preprocessor.get("version"), str) and preprocessor["version"], "preprocessor version required")

    if normalization is not None:
        expected = {
            "contract_id": normalization.get("normalization_contract_id"),
            "digest": normalization_digest(normalization),
        }
        require(manifest.get("normalization") == expected, "normalization fingerprint mismatch")

    pages = manifest.get("pages")
    page_count = manifest.get("page_count")
    require(isinstance(page_count, int) and page_count >= 1, "page_count must be positive")
    require(isinstance(pages, list) and len(pages) == page_count, "pages/page_count mismatch")
    indices = [page.get("pdf_page_index") for page in pages if isinstance(page, dict)]
    require(indices == list(range(page_count)), "physical PDF page indices must be contiguous and zero-based")

    units = manifest.get("structural_units")
    require(isinstance(units, list) and units, "structural_units required")
    by_id: dict[str, dict[str, Any]] = {}
    page_unit_by_index: dict[int, dict[str, Any]] = {}
    for unit in units:
        require(isinstance(unit, dict), "structural unit must be object")
        unit_id = unit.get("unit_id")
        require(isinstance(unit_id, str) and unit_id, "structural unit_id required")
        require(unit_id not in by_id, f"duplicate structural unit_id: {unit_id}")
        by_id[unit_id] = unit
        start = unit.get("pdf_page_start")
        end = unit.get("pdf_page_end")
        require(isinstance(start, int) and isinstance(end, int), f"{unit_id}: page span required")
        require(0 <= start <= end < page_count, f"{unit_id}: page span out of range")
        if unit.get("type") == "PAGE":
            require(start == end, f"{unit_id}: PAGE unit must span exactly one page")
            require(start not in page_unit_by_index, f"duplicate PAGE unit for page {start}")
            page_unit_by_index[start] = unit

    require(set(page_unit_by_index) == set(range(page_count)), "every physical page requires exactly one PAGE unit")
    for page in pages:
        index = page["pdf_page_index"]
        require(
            page_unit_by_index[index].get("normalized_content_sha256") == page.get("normalized_content_sha256"),
            f"page {index}: PAGE unit digest mismatch",
        )

    references = manifest.get("references")
    require(isinstance(references, list), "references must be a list")
    for reference in references:
        require(isinstance(reference, dict), "reference must be object")
        from_unit_id = reference.get("from_unit_id")
        require(from_unit_id in by_id, "reference source unit does not exist")
        target_unit_id = reference.get("target_unit_id")
        resolution = reference.get("resolution")
        if resolution == "UNIQUE_LABEL_MATCH":
            require(target_unit_id in by_id, "resolved reference target does not exist")
        elif resolution in {"AMBIGUOUS", "NOT_FOUND", "UNRESOLVED"}:
            require(target_unit_id is None, "unresolved/ambiguous reference must not name a target")
        else:
            raise PreprocessingError(f"invalid reference resolution: {resolution}")

    if source_lock is not None:
        require(manifest.get("source_lock_id") == source_lock.get("source_lock_id"), "manifest/source-lock ID mismatch")
        source = manifest.get("source")
        require(isinstance(source, dict), "manifest source required")
        locked = find_locked_source(source_lock, str(source.get("source_id")))
        integrity = locked.get("integrity")
        require(isinstance(integrity, dict), "locked source integrity required")
        require(source.get("algorithm") == integrity.get("algorithm"), "manifest source algorithm mismatch")
        require(source.get("digest") == integrity.get("digest"), "manifest source digest mismatch")
        if isinstance(integrity.get("byte_length"), int):
            require(source.get("byte_length") == integrity.get("byte_length"), "manifest source byte length mismatch")


def preprocess_locked_pdf(
    *,
    pdf: Path,
    source_lock_path: Path,
    source_id: str,
    normalization_path: Path = DEFAULT_NORMALIZATION,
    pdftotext: str = "pdftotext",
) -> dict[str, Any]:
    source_lock = load_json(source_lock_path)
    source = find_locked_source(source_lock, source_id)
    verify_locked_pdf(pdf, source)
    normalization = load_json(normalization_path)
    extracted_text, tool = extract_pdf_text(pdf, pdftotext)
    manifest = build_manifest_from_extracted_text(
        source_lock_id=source_lock["source_lock_id"],
        source=source,
        extracted_text=extracted_text,
        tool=tool,
        normalization=normalization,
        builder_sha256=sha256_file(Path(__file__)),
    )
    validate_manifest(manifest, source_lock=source_lock, normalization=normalization)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic structural metadata from one source-locked manufacturer PDF")
    parser.add_argument("--source-lock", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--normalization", type=Path, default=DEFAULT_NORMALIZATION)
    parser.add_argument("--pdftotext", default="pdftotext")
    args = parser.parse_args()
    try:
        manifest = preprocess_locked_pdf(
            pdf=args.pdf,
            source_lock_path=args.source_lock,
            source_id=args.source_id,
            normalization_path=args.normalization,
            pdftotext=args.pdftotext,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"IC document preprocessing PASS: {args.source_id} -> {args.output}")
        return 0
    except (OSError, json.JSONDecodeError, PreprocessingError, subprocess.CalledProcessError) as exc:
        print(f"IC document preprocessing FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
