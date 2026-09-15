from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "z2like-demo-browser-live-acceptance.py"


def test_report_payload_contains_no_raw_secret_fields() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    report_start = source.index('return {\n            "result": "PASS"')
    report_end = source.index("\n        }\n    finally:", report_start)
    report_source = source[report_start:report_end]
    assert '"token"' not in report_source
    assert '"capability"' not in report_source
    assert '"cookie"' not in report_source
