from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "z2like-demo-browser-live-acceptance.yml"


def test_live_report_is_uploaded_even_on_failure() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "Upload live acceptance evidence" in source
    assert "if: always()" in source
    assert "report.json" in source
    assert "retention-days: 14" in source
