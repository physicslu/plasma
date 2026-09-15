from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONTROL = ROOT / "scripts" / "z2like-demo-qemu-control-plane.py"
KIT = ROOT / "scripts" / "z2like-demo-qemu-kit.py"
KIT_BUILDER = ROOT / "scripts" / "z2like-demo-qemu-build-kit.py"
WORKFLOW = ROOT / ".github" / "workflows" / "z2like-demo-browser-live-acceptance.yml"


def test_control_plane_is_commit_and_scripts_tree_pinned() -> None:
    source = CONTROL.read_text(encoding="utf-8")
    assert 'rev-parse", "HEAD"' in source
    assert 'f"{expected_commit}:scripts"' in source
    assert 'SCRIPTS_VOLUME_PREFIX = "plasma-z2like-demo-scripts-"' in source
    assert '"source_commit": commit' in source
    assert '"scripts_tree_sha": scripts_tree' in source
    assert 'PROVENANCE_FILE = ".plasma-control-plane-provenance.json"' in source


def test_reconciliation_preserves_only_canonical_durable_state() -> None:
    source = CONTROL.read_text(encoding="utf-8")
    for volume in (
        "plasma-z2like-demo-product",
        "plasma-z2like-demo-config",
        "plasma-z2like-demo-bootstrap",
        "plasma-z2like-demo-runtime",
        "plasma-z2like-demo-logs",
    ):
        assert volume in source
    assert "durable mount drift" in source
    assert "refusing automated container replacement" in source
    assert '"durable_state_preserved": True' in source
    assert "sudo" not in source


def test_control_plane_replacement_is_rollback_capable_and_private() -> None:
    source = CONTROL.read_text(encoding="utf-8")
    assert 'backup = f"{CONTAINER}-rollback-{commit[:12]}"' in source
    assert '_docker("rename", CONTAINER, backup' in source
    assert '_docker("rename", backup, CONTAINER' in source
    assert '"--network",\n        NETWORK' in source
    assert '"--ip",\n        PPU_IP' in source
    assert 'f"{scripts_volume}:/sim:ro"' in source
    create = source[source.index("def _create_container(") : source.index("def reconcile(")]
    assert ":/source:ro" not in create
    assert '"-p"' not in create
    assert '"--publish"' not in create


def test_exact_kit_owns_simulation_installer_adapter() -> None:
    builder = KIT_BUILDER.read_text(encoding="utf-8")
    consumer = KIT.read_text(encoding="utf-8")
    assert '"z2like-demo-qemu-installer.py"' in builder
    assert 'installer = kit_scripts / "z2like-demo-qemu-installer.py"' in consumer
    assert 'installer = SCRIPT_DIR / "z2like-demo-qemu-installer.py"' not in consumer
    assert '"kit_local_simulation_installer": str(installer)' in consumer


def test_browser_live_reconciles_control_plane_before_preflight_and_build() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    reconcile = workflow.index("Reconcile exact-commit QEMU control plane")
    preflight = workflow.index("Preflight canonical SWPC/QEMU target")
    build = workflow.index("Build canonical ARMv7 Z2 PS kit")
    assert reconcile < preflight < build
    assert 'scripts/z2like-demo-qemu-control-plane.py \\\n            --expected-commit "$GITHUB_SHA"' in workflow
    assert 'runs-on: [self-hosted, linux, x64, plasma-integration]' in workflow
    assert "persist-credentials: false" in workflow
