"""Adversarial provenance tests for owner-initiated CI Kit workflow_dispatch."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "plasma_trusted_z2_artifact_owner_dispatch_test",
    ROOT / "scripts/plasma_trusted_z2_ci_artifact.py",
)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

SOURCE = "37a7823d89973dd0f6656ed276a7a290eb033f98"
RUN_ID = 42451604271


def fixtures(event="workflow_dispatch"):
    run = {
        "id": RUN_ID, "status": "completed", "conclusion": "success",
        "event": event, "head_branch": "main", "head_sha": SOURCE,
        "path": ".github/workflows/z2-ps-release.yml",
        "run_attempt": 1,
        "actor": {"login": "physicslu"},
        "triggering_actor": {"login": "physicslu"},
        "repository": {"full_name": "physicslu/plasma", "id": 1007530655},
        "head_repository": {"full_name": "physicslu/plasma"},
    }
    artifact = {
        "id": 13605648473,
        "name": "plasma-z2-ps-kit-0.2.1-" + SOURCE[:12],
        "expired": False, "size_in_bytes": 118166562,
        "digest": "sha256:" + "a" * 64,
        "workflow_run": {
            "id": RUN_ID, "head_sha": SOURCE,
            "head_branch": "main", "repository_id": 1007530655,
        },
    }
    return run, {"total_count": 1, "artifacts": [artifact]}


def test_owner_main_manual_dispatch_and_push_share_strict_artifact_validation():
    for event in ("workflow_dispatch", "push"):
        run, listing = fixtures(event)
        result = mod.admit(run, listing, source_sha=SOURCE, run_id=RUN_ID)
        assert result["status"] == "TRUSTED_CI_ARTIFACT_ADMITTED"
        assert result["artifact_id"] == 13605648473


@pytest.mark.parametrize("change", [
    {"actor": {"login": "someone-else"}},
    {"triggering_actor": {"login": "someone-else"}},
    {"actor": {}}, {"triggering_actor": {}},
    {"run_attempt": 2}, {"run_attempt": True},
    {"event": "pull_request"}, {"event": "issue_comment"},
    {"head_branch": "feature"}, {"head_sha": "0" * 40},
    {"path": ".github/workflows/another.yml"},
    {"status": "in_progress"}, {"conclusion": "failure"},
    {"head_repository": {"full_name": "someone/other"}},
])
def test_manual_dispatch_denies_ambiguous_actor_provenance_or_source(change):
    run, listing = fixtures()
    run.update(change)
    with pytest.raises(mod.ArtifactDenied):
        mod.admit(run, listing, source_sha=SOURCE, run_id=RUN_ID)


def test_manual_dispatch_still_denies_wrong_artifact_identity():
    run, listing = fixtures()
    listing["artifacts"][0]["workflow_run"]["head_sha"] = "f" * 40
    with pytest.raises(mod.ArtifactDenied, match="KIT_ARTIFACT_PROVENANCE_DENIED"):
        mod.admit(run, listing, source_sha=SOURCE, run_id=RUN_ID)
