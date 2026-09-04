from __future__ import annotations

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


def test_persistent_workflow_retains_exact_identity_and_preflight_evidence() -> None:
    workflow = _text(".github/workflows/persistent-integration-host.yml")
    assert 'sha="$GITHUB_SHA"' in workflow
    assert 'test "$(git rev-parse HEAD)" = "$sha"' in workflow
    assert "plasma-persistent-preflight.json" in workflow
    assert "plasma-persistent-environment-fingerprint.json" in workflow
    assert "plasma-static-ipv4-persistent-repeatability.json" in workflow
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
