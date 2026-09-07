#!/usr/bin/env python3
from __future__ import annotations

import re
from typing import Any

import build_evidence_pack as builder

LEGACY_CONTEXT_STRATEGY = "pack_materialized_v0"
COMPACT_CONTEXT_STRATEGY = "cross_pack_physical_page_dedup_v1"

_EVIDENCE_BLOCK = re.compile(
    r"=== BEGIN (?P<source_id>[A-Za-z0-9_.-]+) PDF_PAGE (?P<page>[0-9]+) "
    r"SHA256 (?P<sha256>[0-9a-f]{64}) ===\n"
    r"(?P<body>.*?)\n"
    r"=== END (?P=source_id) PDF_PAGE (?P=page) ===",
    re.DOTALL,
)


class SemanticContextError(builder.KL25EvidencePackError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SemanticContextError(message)


def _parse_pack_blocks(
    *,
    pack_id: str,
    pack: dict[str, Any],
    text: str,
) -> list[dict[str, Any]]:
    refs = pack.get("page_refs")
    require(isinstance(refs, list) and refs, f"{pack_id}: page_refs required for compact context")

    matches = list(_EVIDENCE_BLOCK.finditer(text))
    require(len(matches) == len(refs), f"{pack_id}: materialized evidence block count mismatch")
    reconstructed = "\n\n".join(match.group(0) for match in matches) + "\n"
    require(reconstructed == text, f"{pack_id}: materialized evidence framing is not canonical")

    blocks: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for index, (ref, match) in enumerate(zip(refs, matches, strict=True)):
        require(isinstance(ref, dict), f"{pack_id}: page_refs[{index}] must be an object")
        source_id = ref.get("source_id")
        page = ref.get("pdf_page_number")
        expected_sha = ref.get("page_text_sha256")
        require(isinstance(source_id, str) and source_id, f"{pack_id}: page_refs[{index}] source_id missing")
        require(isinstance(page, int) and not isinstance(page, bool) and page >= 1, f"{pack_id}: page_refs[{index}] page invalid")
        require(isinstance(expected_sha, str) and re.fullmatch(r"[0-9a-f]{64}", expected_sha) is not None, f"{pack_id}: page_refs[{index}] sha256 invalid")

        parsed_source = match.group("source_id")
        parsed_page = int(match.group("page"))
        parsed_sha = match.group("sha256")
        body = match.group("body")
        key = (source_id, page)

        require(key not in seen, f"{pack_id}: duplicate physical page in one Evidence Pack: {source_id}:p{page}")
        seen.add(key)
        require((parsed_source, parsed_page) == key, f"{pack_id}: evidence block identity mismatch at index {index}")
        require(parsed_sha == expected_sha, f"{pack_id}: evidence block header digest mismatch for {source_id}:p{page}")
        require(builder.sha256_text(body) == expected_sha, f"{pack_id}: evidence block content digest mismatch for {source_id}:p{page}")

        blocks.append(
            {
                "source_id": source_id,
                "pdf_page_number": page,
                "page_text_sha256": expected_sha,
                "block": match.group(0),
            }
        )
    return blocks


def describe_legacy_context(context: str) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "strategy": LEGACY_CONTEXT_STRATEGY,
        "gate3_artifacts_mutated": False,
        "context_sha256": builder.sha256_text(context),
        "context_bytes": len(context.encode("utf-8")),
    }


def assemble_compact_model_context(
    manifest: dict[str, Any],
    *,
    packs: dict[str, dict[str, Any]],
    evidence_text: dict[str, str],
) -> tuple[str, dict[str, Any]]:
    """Build inference-only context with cross-pack physical-page deduplication.

    Gate-3 packs and evidence payloads remain byte-for-byte authoritative. This
    function validates the admitted materialization first, then removes only
    repeated physical-page occurrences for the model request. A repeated
    source/page identity with a different digest or body fails closed.
    """

    legacy_context = builder.assemble_model_context(
        manifest,
        packs=packs,
        evidence_text=evidence_text,
    )

    listed = manifest.get("packs")
    require(isinstance(listed, list) and listed, "pre-AI manifest packs required")

    unique: dict[tuple[str, int], dict[str, Any]] = {}
    page_occurrences = 0
    per_pack: list[dict[str, Any]] = []

    for item in listed:
        require(isinstance(item, dict), "pre-AI pack manifest item must be an object")
        pack_id = item.get("pack_id")
        require(isinstance(pack_id, str) and pack_id in packs, f"unsupported pre-AI pack id: {pack_id!r}")
        require(pack_id in evidence_text, f"missing materialized evidence text: {pack_id}")
        blocks = _parse_pack_blocks(pack_id=pack_id, pack=packs[pack_id], text=evidence_text[pack_id])
        page_occurrences += len(blocks)
        per_pack.append(
            {
                "pack_id": pack_id,
                "page_occurrences": len(blocks),
                "evidence_bytes": len(evidence_text[pack_id].encode("utf-8")),
            }
        )
        for block in blocks:
            key = (block["source_id"], block["pdf_page_number"])
            prior = unique.get(key)
            if prior is None:
                unique[key] = block
                continue
            require(
                prior["page_text_sha256"] == block["page_text_sha256"],
                f"cross-pack physical page digest conflict: {key[0]}:p{key[1]}",
            )
            require(prior["block"] == block["block"], f"cross-pack physical page content conflict: {key[0]}:p{key[1]}")

    require(bool(unique), "compact semantic context requires at least one physical page")
    duplicate_occurrences_removed = page_occurrences - len(unique)
    require(duplicate_occurrences_removed >= 0, "compact context duplicate accounting underflow")

    chunks = [
        "PLASMA PRE-AI MANUFACTURER EVIDENCE CONTEXT",
        f"TARGET: {manifest['target']}",
        f"BUNDLE_DIGEST: {manifest['bundle_digest']}",
        "AUTHORITY: manufacturer evidence only; applicability is deterministic and immutable to AI",
        f"CONTEXT_STRATEGY: {COMPACT_CONTEXT_STRATEGY}",
        f"PAGE_OCCURRENCES: {page_occurrences}; UNIQUE_PHYSICAL_PAGES: {len(unique)}",
    ]
    for key in sorted(unique):
        chunks.extend(["", unique[key]["block"]])
    compact_context = "\n".join(chunks) + "\n"

    legacy_bytes = len(legacy_context.encode("utf-8"))
    compact_bytes = len(compact_context.encode("utf-8"))
    require(compact_bytes <= legacy_bytes, "compact context unexpectedly exceeds legacy context size")

    audit = {
        "schema_version": "0.1.0",
        "strategy": COMPACT_CONTEXT_STRATEGY,
        "gate3_artifacts_mutated": False,
        "dedup_identity": ["source_id", "pdf_page_number", "page_text_sha256"],
        "page_occurrences": page_occurrences,
        "unique_physical_pages": len(unique),
        "duplicate_occurrences_removed": duplicate_occurrences_removed,
        "page_occurrence_redundancy_pct": round(
            100.0 * duplicate_occurrences_removed / page_occurrences,
            2,
        ),
        "legacy_context_sha256": builder.sha256_text(legacy_context),
        "legacy_context_bytes": legacy_bytes,
        "context_sha256": builder.sha256_text(compact_context),
        "context_bytes": compact_bytes,
        "context_byte_reduction_pct": round(
            100.0 * (legacy_bytes - compact_bytes) / legacy_bytes,
            2,
        ) if legacy_bytes else 0.0,
        "per_pack": per_pack,
    }
    return compact_context, audit
