"""Host-only integrity check for the permanent Site2 first Flash evidence chain."""
from __future__ import annotations
import hashlib
import json
import re
from .test_ppu_bundle_v3_packages_contract import ROOT

PATH=ROOT/"docs/evidence/site2-first-flash-2026-11-07/evidence.json"
RUNS={42348102004,42354483913,42354639724,42354798488,
      42354899860,42354991188,42355729976,42356019198}
SHA64=re.compile(r"[0-9a-f]{64}\Z")

def test_first_real_site2_evidence_is_complete_and_consistent():
    data=json.loads(PATH.read_text(encoding="utf-8"))
    assert data["schema"]=="plasma.site2.first-flash-evidence.v1"
    assert data["site_id"]==2 and data["target"]=="STM32F103C8T6"
    assert len(data["original_flash_source_sha"])==40
    assert {r["run"] for r in data["evidence"]}==RUNS
    assert len(data["evidence"])==8
    for r in data["evidence"]:
        assert r["run_url"]==f"https://github.com/physicslu/plasma/actions/runs/{r['run']}"
        assert SHA64.fullmatch(r["original_stdout_sha256"])
        assert SHA64.fullmatch(r.get("zip",r.get("archive_zip_sha256","")))
        if "original_stdout_line" in r:
            # This is the original (non-redacted) one-line stdout; Runner
            # captured it with a trailing LF. Missing or modified bytes FAIL.
            raw=(r["original_stdout_line"]+"\n").encode("utf-8")
            assert hashlib.sha256(raw).hexdigest()==r["original_stdout_sha256"]
        elif r["run"]==42354899860:
            assert "device_id_observed" in r["sensitive_fields_omitted"]
            assert "original_stdout_line" not in r
    identities=data["immutable_identities"]
    first=data["first_flash"]
    flash=next(r["typed_evidence"] for r in data["evidence"]
               if r["run"]==42356019198)
    assert first["result"]=="PASS" and first["submission_count"]==1
    assert first["attempts"]==1 and first["no_auto_retry"] is True
    assert identities["firmware_bytes"]==18768
    assert identities["firmware_sha256"]==identities["readback_sha256"]
    assert flash["flash_result"]=="PASS" and flash["safe_off"] is True
    assert flash["attempts"]==1 and flash["submission_count"]==1
    assert flash["readback_sha256"]==identities["firmware_sha256"]
    assert flash["image_sha256"]==identities["firmware_sha256"]
    assert flash["bytes_verified"]==18768
    assert flash["job_id"]==identities["flash_job_id"]
    assert flash["post_site2_idle"] is True
    assert flash["post_site2_admission_record"] is False
    assert flash["post_site2_seal"] is False
    assert flash["post_openocd_processes"]==0
    opf=next(r["typed_evidence"] for r in data["evidence"]
             if r["run"]==42355729976)
    assert opf["asset_set_sha256"]==identities["active_asset_set_sha256"]
    assert opf["opf_static"]=="PASS"
    assert opf["engine_binary_sha256"]==identities["selected_openocd_binary_sha256"]
    assert opf["engine_admission_sha256"]==identities["selected_admission_sha256"]
    admission=next(r["typed_evidence"] for r in data["evidence"]
                   if r["run"]==42354991188)["observation"]
    assert admission["result"]=="ADMITTED"
    assert admission["revoke"]=="PASS"
    assert admission["record_present"] is False

def test_negative_switch_receipt_is_not_erased():
    data=json.loads(PATH.read_text(encoding="utf-8"))
    run=next(r for r in data["evidence"] if r["run"]==42354639724)
    assert run["exit_code"]==1
    assert run["typed_evidence"]["error_code"]=="NameError"
    assert run["typed_evidence"]["flash"]=="NOT_RUN"
    followup=next(r for r in data["evidence"] if r["run"]==42354798488)
    assert followup["typed_evidence"]["observation"]["selection"]=="NEW"
