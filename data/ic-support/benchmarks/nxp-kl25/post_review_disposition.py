#!/usr/bin/env python3
"""Validate explicit human disposition and candidate-review artifacts.

This module validates shape, lineage, digests and coverage.  It never decides
whether a statement is true or whether manufacturer evidence entails it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CONTRACT = json.loads((HERE / "post-review-disposition-contract.json").read_text())
DIMENSIONS = tuple(CONTRACT["candidate_review_dimensions"])
PASS = {"semantic_support": "SUPPORTED", "citation_entailment": "COMPLETE", "atomicity": "PASS", "scope": "PASS", "terminology": "PASS"}
TRANSFORMS = {"REPLACE_WITH_MANUFACTURER_FACT", "SPLIT", "NARROW", "CITATION_SUPPLEMENT_FOR_CANONICAL"}


class DispositionError(RuntimeError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise DispositionError(message)


def canonical_digest(value: dict[str, Any], digest_key: str) -> str:
    payload = {k: v for k, v in value.items() if k != digest_key}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: root must be object")
    return value


def validate_disposition(view: dict[str, Any], verdict: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    require(artifact.get("source") == CONTRACT["source"], "frozen Gate 5.8 source binding mismatch")
    require(artifact.get("artifact_digest") == canonical_digest(artifact, "artifact_digest"), "disposition digest mismatch")
    facts = {(u["primary_unit_id"], f["fact_id"]): f for u in view["units"] for f in u["facts"]}
    verdicts = {(v["primary_unit_id"], v["fact_id"]): v for v in verdict["fact_verdicts"]}
    require(set(facts) == set(verdicts), "review view/verdict fact set mismatch")
    seen: set[tuple[str, str]] = set()
    candidate_ids: set[str] = set()
    actions: dict[str, int] = {}
    for item in artifact.get("dispositions", []):
        key = (item.get("primary_unit_id"), item.get("fact_id"))
        require(key in facts and key not in seen, f"unknown or duplicate disposition: {key}")
        seen.add(key)
        require(item.get("fact_digest") == facts[key]["fact_digest"], f"{key}: fact digest mismatch")
        action = item.get("action")
        require(action in {"ACCEPT", "REJECT", *TRANSFORMS}, f"{key}: invalid action")
        projection = item.get("projection_state")
        require(projection in CONTRACT["projection_states"], f"{key}: invalid projection state")
        candidates = item.get("candidates")
        require(isinstance(candidates, list), f"{key}: candidates must be array")
        if action == "REJECT":
            require(not candidates and projection == "BLOCKED", f"{key}: REJECT must be BLOCKED without candidates")
        else:
            require(candidates, f"{key}: {action} requires candidate lineage")
        if action == "ACCEPT":
            require(all(verdicts[key][d] == PASS[d] for d in DIMENSIONS), f"{key}: only full PASS may be ACCEPT")
        for candidate in candidates:
            cid = candidate.get("candidate_id")
            require(isinstance(cid, str) and cid not in candidate_ids, f"duplicate candidate id: {cid}")
            candidate_ids.add(cid)
            require(candidate.get("candidate_digest") == canonical_digest(candidate, "candidate_digest"), f"{cid}: digest mismatch")
            evidence = candidate.get("evidence")
            require(isinstance(evidence, list) and evidence, f"{cid}: manufacturer evidence required")
            for ref in evidence:
                source_id = ref.get("source_id")
                require(ref.get("source_sha256") == CONTRACT["manufacturer_sources"].get(source_id), f"{cid}: source binding mismatch")
        actions[action] = actions.get(action, 0) + 1
    require(seen == set(facts), f"disposition must cover exact 140-fact set; missing={len(set(facts)-seen)}")
    return {"fact_count": len(facts), "candidate_count": len(candidate_ids), "action_counts": actions}


def validate_candidate_review(artifact: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    candidates = {c["candidate_id"]: c for d in artifact["dispositions"] for c in d["candidates"]}
    rows = review.get("candidate_reviews")
    require(isinstance(rows, list), "candidate_reviews must be array")
    observed: set[str] = set()
    admitted: set[str] = {
        c["candidate_id"]
        for d in artifact["dispositions"]
        if d["action"] == "ACCEPT"
        for c in d["candidates"]
    }
    for row in rows:
        cid = row.get("candidate_id")
        require(cid in candidates and cid not in observed, f"unknown or duplicate candidate review: {cid}")
        observed.add(cid)
        require(row.get("candidate_digest") == candidates[cid]["candidate_digest"], f"{cid}: stale candidate review")
        require(isinstance(row.get("reviewer_rationale"), str) and row["reviewer_rationale"].strip(), f"{cid}: rationale required")
        if all(row.get(d) == PASS[d] for d in DIMENSIONS):
            admitted.add(cid)
    required = {c["candidate_id"] for d in artifact["dispositions"] if d["action"] in TRANSFORMS for c in d["candidates"]}
    require(required <= observed, f"transformed candidates require explicit local review: {sorted(required-observed)}")
    require(review.get("review_digest") == canonical_digest(review, "review_digest"), "candidate review digest mismatch")
    return {"reviewed_candidates": len(observed), "manufacturer_review_pass_candidates": sorted(admitted)}
