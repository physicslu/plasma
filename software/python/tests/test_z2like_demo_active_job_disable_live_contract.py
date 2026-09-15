from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "z2like-demo-active-job-disable-live-acceptance.py"
INSTALLER = ROOT / "scripts" / "z2like-demo-qemu-installer.py"
WORKFLOW = ROOT / ".github" / "workflows" / "z2like-demo-active-job-disable-live-negative.yml"
BROWSER_WORKFLOW = ROOT / ".github" / "workflows" / "z2like-demo-browser-live-acceptance.yml"
H021 = ROOT / "handover" / "H021-z2like-demo-browser-runtime-deployment-plan-2026-09-14.md"


class Z2LikeDemoActiveJobDisableLiveContractTests(unittest.TestCase):
    def test_live_gate_is_chained_after_successful_browser_runtime_deployment(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_run:", workflow)
        self.assertIn('"z2like-demo Browser Runtime live acceptance"', workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", workflow)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", workflow)
        self.assertIn("github.event.workflow_run.head_repository.full_name == 'physicslu/plasma'", workflow)
        self.assertIn("PLASMA_ACCEPTED_SHA: ${{ github.event.workflow_run.head_sha }}", workflow)
        self.assertIn("PLASMA_UPSTREAM_BROWSER_RUN_ID: ${{ github.event.workflow_run.id }}", workflow)
        self.assertIn("runs-on: [self-hosted, linux, x64, plasma-integration]", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn('--expected-commit "$PLASMA_ACCEPTED_SHA"', workflow)
        self.assertIn('--upstream-browser-run-id "$PLASMA_UPSTREAM_BROWSER_RUN_ID"', workflow)
        self.assertNotIn("\n  push:\n", workflow)

    def test_browser_runtime_gate_is_triggered_by_active_gate_deployment_inputs(self) -> None:
        workflow = BROWSER_WORKFLOW.read_text(encoding="utf-8")
        for path in (
            '.github/workflows/z2like-demo-active-job-disable-live-negative.yml',
            'scripts/z2like-demo-active-job-disable-live-acceptance.py',
            'scripts/z2like-demo-qemu-installer.py',
            'software/python/tests/test_z2like_demo_active_job_disable_live_contract.py',
        ):
            self.assertIn(f'- "{path}"', workflow)

    def test_gate_uses_configured_mock_not_legacy_mutable_mock_runtime(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        installer = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('payload.get("provider") == "configured_mock"', source)
        self.assertNotIn("/api/manager/ppu/api/mock/runtime", source)
        self.assertNotIn("_get_mock_runtime", source)
        self.assertNotIn("_set_mock_runtime", source)
        self.assertIn("CONFIGURED_MOCK_ERASE_OBSERVATION_DELAY_S = 10.0", installer)
        self.assertIn('"      delays:"', installer)
        self.assertIn('f"        erase: {erase_delay_s:.1f}"', installer)
        self.assertIn("_simulation_config_for_count_without_observable_erase_delay", installer)

    def test_gate_reuses_existing_browser_security_helpers(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('with_name("z2like-demo-browser-live-acceptance.py")', source)
        self.assertIn("_wait_public_deployment", source)
        self.assertIn("_read_pairing_token", source)
        self.assertIn("_local_ingress_acceptance", source)
        self.assertIn("_wait_current_idle", source)
        self.assertIn("session.capability_value()", source)

    def test_active_job_must_be_observed_before_disable_probe(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        observed = source.index("_wait_manager_observes_job(session, args.alias, job_id)")
        disable = source.index('body={"lifecycle": "disabled"}', observed)
        self.assertLess(observed, disable)
        self.assertIn('code="ppu_busy"', source)
        self.assertIn('"disable_while_active_site_job": "BLOCKED_PPU_BUSY"', source)

    def test_cleanup_is_bounded_without_runtime_profile_mutation(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("_cancel_job(", source)
        self.assertIn("_wait_job_terminal(", source)
        self.assertIn("_live._wait_current_idle", source)
        self.assertIn('"configured_mock_runtime_mutated": False', source)
        self.assertNotIn("mock_runtime_profile_restored", source)
        self.assertNotIn("force_commission", source)
        self.assertNotIn("force-commission", source)

    def test_report_never_exposes_pairing_or_capability_values(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('token = ""', source)
        self.assertIn('"pairing_secret_exposed": False', source)
        self.assertIn('"maintenance_capability_exposed": False', source)
        self.assertNotIn('"pairing_token":', source)
        self.assertNotIn('"maintenance_capability":', source)

    def test_remaining_qualification_debt_stays_explicit(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        handover = H021.read_text(encoding="utf-8")
        for boundary in (
            "forced stale/non-idle maintenance proof rejection",
            "15-minute capability expiry wall-clock rejection",
            "real PYNQ-Z2 deployment/reboot/rollback",
        ):
            self.assertIn(boundary, source)
            self.assertIn(boundary, handover)
        self.assertIn("active-Site-Job disable rejection", handover)
        self.assertIn("Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED", handover)


if __name__ == "__main__":
    unittest.main()
