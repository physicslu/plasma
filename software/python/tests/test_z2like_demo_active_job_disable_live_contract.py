from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "z2like-demo-active-job-disable-live-acceptance.py"
WORKFLOW = ROOT / ".github" / "workflows" / "z2like-demo-active-job-disable-live-negative.yml"
DOC = ROOT / "docs" / "deployment" / "z2like-demo-active-job-disable-live-negative.md"


class Z2LikeDemoActiveJobDisableLiveContractTests(unittest.TestCase):
    def test_live_gate_is_post_merge_swpc_only(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("github.event_name != 'pull_request'", workflow)
        self.assertIn("github.repository == 'physicslu/plasma'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("runs-on: [self-hosted, linux, x64, plasma-integration]", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn('--expected-commit "$GITHUB_SHA"', workflow)

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
        self.assertIn("LIVE_ERASE_BASE_TIME_MS = 30_000", source)

    def test_cleanup_is_bounded_and_restores_mock_runtime(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("_cancel_job(", source)
        self.assertIn("_wait_job_terminal(", source)
        self.assertIn("restore original Mock Runtime profile", source)
        self.assertIn("_live._wait_current_idle", source)
        self.assertIn('"mock_runtime_profile_restored": "PASS"', source)
        self.assertNotIn("force_commission", source)
        self.assertNotIn("force-commission", source)

    def test_report_never_exposes_pairing_or_capability_values(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('token = ""', source)
        self.assertIn('"pairing_secret_exposed": False', source)
        self.assertIn('"maintenance_capability_exposed": False', source)
        self.assertNotIn('"pairing_token":', source)
        self.assertNotIn('"maintenance_capability":', source)

    def test_document_keeps_remaining_qualification_debt_explicit(self) -> None:
        doc = DOC.read_text(encoding="utf-8")
        self.assertIn("forced stale/non-idle maintenance proof rejection", doc)
        self.assertIn("15-minute capability expiry wall-clock rejection", doc)
        self.assertIn("Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED", doc)
        self.assertIn("active Site Job", doc)


if __name__ == "__main__":
    unittest.main()
