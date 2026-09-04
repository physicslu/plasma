from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
CHECKOUT_SHA = "11d5960a326750d5838078e36cf38b85af677262"
UPLOAD_ARTIFACT_SHA = "ea165f8d65b6e75b540449e92b4886f43607fa02"


def _text(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


def test_persistent_workflow_rejects_non_main_before_self_hosted_execution() -> None:
    workflow = _text(".github/workflows/persistent-integration-host.yml")
    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "main-dispatch-guard:" in workflow
    guard = workflow.split("main-dispatch-guard:", 1)[1].split("persistent-acceptance:", 1)[0]
    assert "runs-on: ubuntu-latest" in guard
    assert 'test "$GITHUB_EVENT_NAME" = "workflow_dispatch"' in guard
    assert 'test "$GITHUB_REPOSITORY" = "physicslu/plasma"' in guard
    assert 'test "$GITHUB_REF" = "refs/heads/main"' in guard

    persistent = workflow.split("persistent-acceptance:", 1)[1]
    checkout = f"actions/checkout@{CHECKOUT_SHA}"
    assert "needs: main-dispatch-guard" in persistent
    assert "github.event_name == 'workflow_dispatch'" in persistent
    assert "github.repository == 'physicslu/plasma'" in persistent
    assert "github.ref == 'refs/heads/main'" in persistent
    assert "runs-on: [self-hosted, linux, x64, plasma-integration]" in persistent
    assert 'test "$(id -u)" -ne 0' in persistent
    assert persistent.index("Assert trusted event identity before checkout") < persistent.index(checkout)
    assert "actions/checkout@v4" not in persistent
    assert "ref: ${{ github.sha }}" in persistent
    assert "persist-credentials: false" in persistent
    assert persistent.index(checkout) < persistent.index("Run fail-closed persistent-host preflight")
    assert persistent.index("Run fail-closed persistent-host preflight") < persistent.index(
        "Set up repository validation dependencies"
    )


def test_persistent_preflight_is_fail_closed_and_does_not_install_host_privilege() -> None:
    source = _text("scripts/persistent-integration-host-preflight.py")
    compile(source, "scripts/persistent-integration-host-preflight.py", "exec")
    for token in (
        'EXPECTED_EVENT = "workflow_dispatch"',
        'EXPECTED_REF = "refs/heads/main"',
        'if event_name != EXPECTED_EVENT:',
        'if repository != expected_repository:',
        'if ref != EXPECTED_REF:',
        'checked_out_sha = _run(["git", "rev-parse", "HEAD"])',
        "checked_out_sha != event_sha",
        '"pre_merge_pr_gate_claim": "NONE"',
        '"qualification_state": "RUNNER_ENROLLED"',
        '"z2_hardware_claim": "NONE"',
        'if uid == 0:',
        '"rootless Docker cannot prove the required real root:root ownership parity"',
        '"this runner is not a sandbox"',
        'if path.exists() and path.is_symlink():',
        'if _inside(resolved, workspace):',
        'if _inside(resolved, runner_temp):',
        'if info.st_uid != uid or info.st_gid != gid:',
        'if mode & 0o022:',
        '"--platform",\n            "linux/arm/v7"',
        '"--network",\n            "none"',
        '"--cap-drop",\n            "ALL"',
        '"no-new-privileges:true"',
        "@sha256:",
    ):
        assert token in source
    for forbidden in (
        '"sudo"',
        "CAP_DAC_OVERRIDE",
        "CAP_FOWNER",
        "setup-qemu",
        "binfmt",
    ):
        assert forbidden not in source


def test_host_readiness_is_non_provisioning_and_github_independent() -> None:
    source = _text("scripts/persistent-integration-host-readiness.py")
    compile(source, "scripts/persistent-integration-host-readiness.py", "exec")
    for token in (
        '"qualification_state": "UNPROVISIONED"',
        'report["qualification_state"] = "HOST_READY"',
        '"mutates_host_configuration": False',
        '"z2_hardware_claim": "NONE"',
        'if uid == 0:',
        '"rootless Docker cannot prove the required real root:root ownership parity"',
        '"this host is not a sandbox"',
        '"docker", "image", "inspect", ARM_IMAGE',
        '"--pull=never"',
        '"--network",\n            "none"',
        '"--cap-drop",\n            "ALL"',
        '"no-new-privileges:true"',
        '"persistent root must be provisioned before readiness is run',
        '"configuration_mutated": False',
    ):
        assert token in source
    persistent_root = source.split("def _persistent_root", 1)[1].split("def _write_report", 1)[0]
    assert ".mkdir(" not in persistent_root
    for forbidden in (
        "GITHUB_EVENT_NAME",
        "GITHUB_REPOSITORY",
        "GITHUB_REF",
        "GITHUB_SHA",
        "GITHUB_WORKSPACE",
        "RUNNER_TEMP",
        '"sudo"',
        "apt-get",
        "dnf install",
        "yum install",
        "systemctl",
        "docker pull",
        "setup-qemu",
        "binfmt",
        "CAP_DAC_OVERRIDE",
        "CAP_FOWNER",
        "ufw",
    ):
        assert forbidden not in source


def test_persistent_workflow_retains_exact_identity_and_preflight_evidence() -> None:
    workflow = _text(".github/workflows/persistent-integration-host.yml")
    assert 'sha="$GITHUB_SHA"' in workflow
    assert 'test "$(git rev-parse HEAD)" = "$sha"' in workflow
    assert "plasma-persistent-preflight.json" in workflow
    assert "plasma-persistent-environment-fingerprint.json" in workflow
    assert "plasma-static-ipv4-persistent-repeatability.json" in workflow
    assert "Record canonical persistent L4 qualification summary" in workflow
    assert "scripts/persistent-integration-qualification-summary.py" in workflow
    assert "plasma-persistent-l4-qualification.json" in workflow
    assert "name: plasma-persistent-integration-${{ github.sha }}" in workflow
    assert f"actions/upload-artifact@{UPLOAD_ARTIFACT_SHA}" in workflow
    assert "actions/upload-artifact@v4" not in workflow
    evidence = workflow.split("- name: Upload persistent-host acceptance reports", 1)[1]
    assert "if: always()" in evidence
    assert "if-no-files-found: warn" in evidence
    for forbidden in (
        "systemctl",
        "plasmactl deploy",
        "plasmactl restart",
        "ssh ",
        "pull_request_target",
    ):
        assert forbidden not in workflow.lower()


def test_qualification_summary_fails_closed_and_emits_exact_l4_binding(tmp_path: Path) -> None:
    source = _text("scripts/persistent-integration-qualification-summary.py")
    compile(source, "scripts/persistent-integration-qualification-summary.py", "exec")
    for token in (
        '"UNPROVISIONED"',
        '"HOST_READY"',
        '"RUNNER_ENROLLED"',
        '"L4_PASS"',
        '"STALE"',
        '"REVOKED"',
        '"becomes_stale_when_main_sha_changes": True',
        '"becomes_stale_when_bound_host_fingerprint_changes": True',
        '"administrative_revocation_overrides_pass": True',
        '"fixed_time_to_live": "NONE"',
        '"GitHub Actions job-start log bound to github_run.run_id"',
        '"z2_hardware_claim": "NONE"',
    ):
        assert token in source

    sha = "a" * 40
    preflight = {
        "status": "PASS",
        "qualification_state": "RUNNER_ENROLLED",
        "z2_hardware_claim": "NONE",
        "identity": {
            "event_sha": sha,
            "checked_out_sha": sha,
            "ref": "refs/heads/main",
            "main_only": True,
        },
        "host": {
            "hostname": "integration-a",
            "uid": 1001,
            "gid": 1001,
            "kernel_release": "test-kernel",
            "machine": "x86_64",
            "os_release": {"ID": "test"},
        },
        "persistent_root": {
            "path": "/state/plasma-ci",
            "filesystem": "ext2/ext3",
            "mode": "0700",
        },
        "docker": {"server_version": "1", "root_dir": "/var/lib/docker", "rootless": False},
        "armv7": {"image": "pinned", "machine": "armv7l"},
        "network": {"default_route_signature_sha256": "route"},
    }
    fingerprint = {"git_sha": sha, "z2_network_backend_claim": "NONE"}
    repeatability = {
        "overall_result": "PASS",
        "run_count": 2,
        "runs": [{"git_sha": sha}, {"git_sha": sha}],
        "manual_cleanup": False,
        "sudo": False,
    }
    paths = {}
    for name, value in (
        ("preflight", preflight),
        ("fingerprint", fingerprint),
        ("repeatability", repeatability),
    ):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = path
    output = tmp_path / "qualification.json"
    env = os.environ.copy()
    env.update(
        {
            "GITHUB_SHA": sha,
            "GITHUB_REPOSITORY": "physicslu/plasma",
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_WORKFLOW": "Persistent integration host acceptance",
            "RUNNER_NAME": "plasma-integration-a",
            "RUNNER_OS": "Linux",
            "RUNNER_ARCH": "X64",
        }
    )
    subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts/persistent-integration-qualification-summary.py"),
            "--preflight",
            str(paths["preflight"]),
            "--fingerprint",
            str(paths["fingerprint"]),
            "--repeatability",
            str(paths["repeatability"]),
            "--report",
            str(output),
        ],
        check=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "PASS"
    assert result["qualification_state"] == "L4_PASS"
    assert result["qualified_sha"] == sha
    assert result["runner"]["name"] == "plasma-integration-a"
    assert result["host_binding"]["hostname"] == "integration-a"
    assert result["staleness_contract"]["exact_sha_bound"] is True
    assert result["z2_hardware_claim"] == "NONE"
    assert set(result["evidence"]) == {"preflight", "environment_fingerprint", "repeatability"}
    assert all(len(entry["sha256"]) == 64 for entry in result["evidence"].values())


def test_persistent_host_security_document_keeps_l4_claim_bounded() -> None:
    doc = _text("docs/architecture/persistent-integration-host-qualification.md")
    for token in (
        "main-only",
        "rootful Docker daemon",
        "not a sandbox",
        "defense-in-depth",
        "runner group",
        "workflow_dispatch",
        "post-merge qualification",
        "not a required PR gate",
        "immutable commit SHA",
        "ephemeral",
        "pull_request_target",
        "PYNQ-Z2",
        "does **not** prove",
    ):
        assert token in doc


def test_runner_enrollment_runbook_preserves_lifecycle_and_secret_boundary() -> None:
    doc = _text("docs/development/persistent-integration-runner-enrollment.md")
    for token in (
        "UNPROVISIONED",
        "HOST_READY",
        "RUNNER_ENROLLED",
        "L4_PASS",
        "STALE",
        "REVOKED",
        "rootful Docker daemon",
        "host-privileged",
        "not a general-purpose worker for arbitrary pull requests",
        "registration token",
        "Never paste a registration token into a repository file",
        "plasma-integration",
        "main",
        "plasma-persistent-l4-qualification.json",
        "job-start log",
        "runner-version evidence source",
        "does **not** prove",
        "PYNQ-Z2",
    ):
        assert token in doc
    for forbidden in (
        "pull_request_target",
        "registration_token=",
        "token: gh",
    ):
        assert forbidden not in doc
