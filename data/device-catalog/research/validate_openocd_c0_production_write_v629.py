#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

import prepare_openocd_c0_production_transaction_v628 as v628
from openocd_backend_evolution_v629 import backend_state, rewind_v629_backend

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RECEIPT = HERE / "openocd-c0-production-backend-write-v6.29.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
C0 = HERE / "stm32c0-commercial-icpn.csv"

FIELDS = (
    "manufacturer","icpn","family","series","base_device","package","pin_count",
    "flash_size","temperature_grade","option_suffix","cmsis_device_name",
    "existing_identifier","existing_identifier_kind","mapping_status",
    "openocd_target_config","source_type","source_reference","source_authority",
    "verification_status",
)


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise RuntimeError(msg)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()


def parse(raw: bytes) -> list[dict[str,str]]:
    with io.StringIO(raw.decode("utf-8")) as stream:
        reader=csv.DictReader(stream)
        req(tuple(reader.fieldnames or ()) == FIELDS, "STM32C0 schema drift")
        return list(reader)


def validate() -> dict:
    receipt=json.loads(RECEIPT.read_text(encoding="utf-8"))
    txn,before,after=v628.build()

    req(txn["postimage_lock_state"] == "FROZEN", "v6.28 postimages are not frozen")
    req(txn["promotion_exact_count"] == 5, "v6.28 exact count drift")
    req(txn["promotion_exact_set_sha256"] == receipt["source_dry_run"]["exact_set_sha256"],
        "v6.28/v6.29 exact-set drift")
    req(txn["promotion_binding_sha256"] == receipt["source_dry_run"]["binding_sha256"],
        "v6.28/v6.29 binding drift")

    frozen=receipt["frozen_postimages"]
    req(git_blob_sha(after["STM32C0"]) == frozen["STM32C0"]["git_blob_sha"],
        "regenerated C0 postimage blob drift")
    req(sha256(after["STM32C0"]) == frozen["STM32C0"]["sha256"],
        "regenerated C0 postimage SHA drift")
    req(len(after["STM32C0"]) == frozen["STM32C0"]["byte_count"],
        "regenerated C0 postimage byte-count drift")
    req(git_blob_sha(after["MANIFEST"]) == frozen["MANIFEST"]["git_blob_sha"],
        "regenerated manifest postimage blob drift")
    req(sha256(after["MANIFEST"]) == frozen["MANIFEST"]["sha256"],
        "regenerated manifest postimage SHA drift")
    req(len(after["MANIFEST"]) == frozen["MANIFEST"]["byte_count"],
        "regenerated manifest postimage byte-count drift")

    c0_raw=C0.read_bytes()
    manifest_raw=MANIFEST.read_bytes()
    c0_rows=parse(c0_raw)
    state=backend_state(c0_rows,"STM32C0")

    pre=receipt["frozen_preimages"]
    if state == "pre":
        req(git_blob_sha(c0_raw) == pre["STM32C0"]["git_blob_sha"], "C0 preimage blob drift")
        req(sha256(c0_raw) == pre["STM32C0"]["sha256"], "C0 preimage SHA drift")
        req(git_blob_sha(manifest_raw) == pre["MANIFEST"]["git_blob_sha"], "manifest preimage blob drift")
        req(sha256(manifest_raw) == pre["MANIFEST"]["sha256"], "manifest preimage SHA drift")
        req(receipt["write_state"]["production_write_applied"] is False,
            "receipt claims write applied while repository is prewrite")
    else:
        req(state == "post", f"unexpected v6.29 backend state {state}")
        req(git_blob_sha(c0_raw) == frozen["STM32C0"]["git_blob_sha"], "C0 postimage blob drift")
        req(sha256(c0_raw) == frozen["STM32C0"]["sha256"], "C0 postimage SHA drift")
        req(git_blob_sha(manifest_raw) == frozen["MANIFEST"]["git_blob_sha"], "manifest postimage blob drift")
        req(sha256(manifest_raw) == frozen["MANIFEST"]["sha256"], "manifest postimage SHA drift")
        req(receipt["approval"]["owner_approval_received"] is True, "postwrite state lacks owner approval")
        req(receipt["approval"]["production_write_authorized"] is True, "postwrite state lacks write authorization")
        req(receipt["approval"]["merge_after_green_ci_authorized"] is True,
            "postwrite state lacks merge authorization")
        req(receipt["write_state"]["production_write_applied"] is True,
            "repository is postwrite but receipt does not record applied write")
        req(isinstance(receipt["write_state"]["applied_commit"],str)
            and len(receipt["write_state"]["applied_commit"]) == 40,
            "postwrite receipt missing applied commit")

    historical=rewind_v629_backend(c0_rows,"STM32C0")
    req(backend_state(historical,"STM32C0") == "pre",
        "v6.29 rewind does not reconstruct backend prestate")

    expected=receipt["expected_poststate"]
    req(expected == txn["poststate_if_approved"], "v6.29 expected poststate drift from v6.28")

    for key,value in receipt["claims"].items():
        req(value is False, f"v6.29 overclaim: {key}")

    summary={
        "transaction_id":receipt["transaction_id"],
        "repository_write_state":state,
        "promotion_exact_count":5,
        "c0_current_git_blob_sha":git_blob_sha(c0_raw),
        "manifest_current_git_blob_sha":git_blob_sha(manifest_raw),
        "frozen_c0_postimage_git_blob_sha":frozen["STM32C0"]["git_blob_sha"],
        "frozen_manifest_postimage_git_blob_sha":frozen["MANIFEST"]["git_blob_sha"],
        "expected_poststate":expected,
        "approval":receipt["approval"],
        "write_state":receipt["write_state"],
        "claims":receipt["claims"],
    }
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("OPENOCD_C0_PRODUCTION_WRITE_V629_READY_PASS" if state=="pre"
          else "OPENOCD_C0_PRODUCTION_WRITE_V629_POSTWRITE_PASS")
    return summary


if __name__=="__main__":
    validate()
