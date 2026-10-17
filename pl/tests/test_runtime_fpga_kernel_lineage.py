"""Host-only reference-source verification tests; no target access."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from pl.tools.runtime_fpga_kernel_lineage import (
    EvidenceError, REFERENCE_FILES, TARGET_RELEASE, git_blob_object_id, main,
    review, validate_reference_manifest, verify_reference_tree,
)

MANIFEST_PATH = (Path(__file__).resolve().parents[1] /
                 "verification/z2_kernel_source_reference_v1.json")


@pytest.fixture
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def test_public_reference_is_never_a_matching_target(manifest):
    out = review(manifest)
    assert out["verdict"] == "M1_NO_GO"
    assert out["source_to_binary_match"] == "UNRESOLVED"
    assert out["target_source_commit"] is None
    assert not out["hardware_ready"]
    assert not out["reload_authorized"]
    assert not out["reference_files_verified"]
    assert out["registered_bridge_count"] == 0
    assert TARGET_RELEASE.endswith("g3c0eca68c652")
    assert len(REFERENCE_FILES) == 4
    assert "TARGET_KERNEL_COMMIT_NOT_RESOLVED" in out["blockers"]
    assert "AXI_MASTER_QUIESCENCE_AND_INFLIGHT_DRAIN_NOT_MEASURED" in out["blockers"]


@pytest.mark.parametrize("field,value", [
    ("matching_source_commit", "e475cc1c9432587298212570c2af2be66b820c41"),
    ("matching_source_patchset_sha256", "0" * 64),
    ("deployed_kernel_binary_sha256", "0" * 64),
    ("deployed_dtb_sha256", "0" * 64),
    ("source_to_binary_attested", True),
    ("registered_bridge_count", 1),
    ("registered_bridge_count", True),
    ("commit_prefix", "e475cc1c9432"),
    ("config_sha256", "0" * 64),
    ("board", "MYIR"),
    ("kernel_release", "other"),
])
def test_fabricated_target_lineage_or_bridge_promotions_refused(manifest,
                                                               field, value):
    manifest["target_observation"][field] = value
    with pytest.raises(EvidenceError):
        review(manifest)


@pytest.mark.parametrize("field,value", [
    ("source_classification", "TARGET_MATCHED"),
    ("axi_drain_measured", True),
    ("hardware_ready", True),
    ("hardware_ready", 0),
    ("reload_authorized", True),
    ("evidence_class", "TARGET_ATTESTED"),
    ("schema", "unknown"),
])
def test_manifest_cannot_issue_hardware_authority(manifest, field, value):
    manifest[field] = value
    with pytest.raises(EvidenceError):
        validate_reference_manifest(manifest)


@pytest.mark.parametrize("field,value", [
    ("repository", "some-fork/linux"),
    ("tag", "master"),
    ("commit", "3c0eca68c652"),
    ("files", {}),
])
def test_reference_pin_mutation_refused(manifest, field, value):
    manifest["public_reference"][field] = value
    with pytest.raises(EvidenceError):
        validate_reference_manifest(manifest)


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\x00" +
                        data).hexdigest()


def test_git_object_identity_hash_not_plain_file_sha(tmp_path):
    source = tmp_path / "s.c"
    source.write_bytes(b"hello\n")
    assert git_blob_object_id(source) == _git_blob_sha(b"hello\n")
    assert git_blob_object_id(source) != hashlib.sha1(b"hello\n").hexdigest()


def test_complete_synthetic_tree_bytes_pass_but_not_target_attestation(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    pins = {}
    for name in REFERENCE_FILES:
        file_path = source / name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        data = (name + "\n").encode()
        file_path.write_bytes(data)
        pins[name] = _git_blob_sha(data)
    verify_reference_tree(source, pins)
    changed = source / next(iter(pins))
    changed.write_bytes(changed.read_bytes() + b"changed")
    with pytest.raises(EvidenceError, match="drifted"):
        verify_reference_tree(source, pins)


@pytest.mark.parametrize("bad", [
    "../escape.c", "drivers/fpga/../../escape.c", "/dev/uio0",
    "drivers/fpga/fpga-mgr.py", "drivers//fpga/zynq-fpga.c",
])
def test_reject_path_traversal_and_wrong_source_roots(tmp_path, bad):
    with pytest.raises(EvidenceError):
        verify_reference_tree(tmp_path, {bad: "0" * 40})


@pytest.mark.parametrize("sha", ["?", "a" * 39, "A" * 40, None])
def test_refuse_unsafe_git_object_ids(tmp_path, sha):
    with pytest.raises(EvidenceError):
        verify_reference_tree(tmp_path, {"drivers/fpga/zynq-fpga.c": sha})


def test_reject_source_symlink(tmp_path):
    source = tmp_path / "root"
    source.mkdir()
    target = tmp_path / "evil.c"
    target.write_text("content")
    folder = source / "drivers/fpga"
    folder.mkdir(parents=True)
    link = folder / "zynq-fpga.c"
    link.symlink_to(target)
    with pytest.raises(EvidenceError, match="symlink"):
        verify_reference_tree(source, {"drivers/fpga/zynq-fpga.c":
                                       _git_blob_sha(b"content")})


def test_reject_missing_and_oversized_files(tmp_path, monkeypatch):
    source = tmp_path / "root"
    (source / "drivers/fpga").mkdir(parents=True)
    f = source / "drivers/fpga/zynq-fpga.c"
    pins = {"drivers/fpga/zynq-fpga.c": _git_blob_sha(b"a")}
    with pytest.raises(EvidenceError):
        verify_reference_tree(source, pins)
    f.write_bytes(b"a" * 11)
    monkeypatch.setattr("pl.tools.runtime_fpga_kernel_lineage.MAX_REFERENCE_FILE_BYTES", 10)
    with pytest.raises(EvidenceError, match="size ceiling"):
        verify_reference_tree(source, pins)


def test_cli_reports_no_go_and_suppresses_raw_provenance(tmp_path, capsys,
                                                          manifest):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    assert main(["--manifest", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["verdict"] == "M1_NO_GO"
    assert report["reference_files_verified"] is False
    assert not report["reload_authorized"]
    manifest["target_observation"]["source_to_binary_attested"] = True
    path.write_text(json.dumps(manifest))
    assert main(["--manifest", str(path)]) == 2
    bad = json.loads(capsys.readouterr().out)
    assert bad["verdict"] == "M1_NO_GO"
    assert bad["error_class"] == "EvidenceError"
    assert "target_observation" not in bad


def test_cli_missing_reference_checkout_refuses_to_claim_verified(tmp_path,
                                                                   capsys,
                                                                   manifest):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(manifest))
    assert main(["--manifest", str(p), "--reference-root",
                 str(tmp_path / "missing")]) == 2
    r = json.loads(capsys.readouterr().out)
    assert r["reference_files_verified"] is False
    assert r["reload_authorized"] is False
