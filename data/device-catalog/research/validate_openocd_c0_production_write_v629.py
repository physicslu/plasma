#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
from copy import deepcopy
from pathlib import Path

from openocd_backend_evolution_v629 import backend_state, bindings, rewind_v629_backend

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RECEIPT = HERE / "openocd-c0-production-backend-write-v6.29.json"
POLICY = HERE / "openocd-c0-production-backend-dry-run-v6.28.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
C0 = HERE / "stm32c0-commercial-icpn.csv"

FIELDS = (
    "manufacturer","icpn","family","series","base_device","package","pin_count",
    "flash_size","temperature_grade","option_suffix","cmsis_device_name",
    "existing_identifier","existing_identifier_kind","mapping_status",
    "openocd_target_config","source_type","source_reference","source_authority",
    "verification_status",
)

BACKEND_FIELDS = (
    "cmsis_device_name","existing_identifier","existing_identifier_kind",
    "mapping_status","openocd_target_config",
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


def parse_csv(raw: bytes) -> list[dict[str,str]]:
    with io.StringIO(raw.decode("utf-8")) as stream:
        reader=csv.DictReader(stream)
        req(tuple(reader.fieldnames or ()) == FIELDS, "STM32C0 schema drift")
        return list(reader)


def render_csv(rows: list[dict[str,str]]) -> bytes:
    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def render_manifest(value: dict) -> bytes:
    return (json.dumps(value,indent=2)+"\n").encode("utf-8")


def validate() -> dict:
    receipt=json.loads(RECEIPT.read_text(encoding="utf-8"))
    policy=json.loads(POLICY.read_text(encoding="utf-8"))
    scope=receipt["source_dry_run"]

    req(scope["exact_count"] == 5, "receipt exact count drift")
    req(scope["exact_set_sha256"] == policy["scope"]["exact_set_sha256"],
        "v6.28/v6.29 exact-set drift")
    req(scope["binding_sha256"] == policy["scope"]["binding_sha256"],
        "v6.28/v6.29 binding drift")
    req(policy["frozen_postimages"]["lock_state"] == "FROZEN",
        "v6.28 frozen postimage lock lost")

    c0_raw=C0.read_bytes()
    manifest_raw=MANIFEST.read_bytes()
    c0_rows=parse_csv(c0_raw)
    req(len(c0_rows)==226,"C0 row count drift")
    state=backend_state(c0_rows,"STM32C0")

    pre=receipt["frozen_preimages"]
    post=receipt["frozen_postimages"]

    # Reconstruct pre-v6.29 C0 bytes from the current complete state.
    rewound=rewind_v629_backend(c0_rows,"STM32C0")
    pre_c0_raw=render_csv(rewound)
    req(git_blob_sha(pre_c0_raw)==pre["STM32C0"]["git_blob_sha"],
        "rewound C0 does not reproduce frozen preimage blob")
    req(sha256(pre_c0_raw)==pre["STM32C0"]["sha256"],
        "rewound C0 does not reproduce frozen preimage SHA")

    manifest=json.loads(manifest_raw)
    c0_source=next(s for s in manifest["sources"] if s["family"]=="STM32C0")
    req(c0_source["row_count"]==226,"manifest C0 row count drift")

    if state=="pre":
        req(git_blob_sha(c0_raw)==pre["STM32C0"]["git_blob_sha"],"C0 preimage blob drift")
        req(sha256(c0_raw)==pre["STM32C0"]["sha256"],"C0 preimage SHA drift")
        req(git_blob_sha(manifest_raw)==pre["MANIFEST"]["git_blob_sha"],"manifest preimage blob drift")
        req(sha256(manifest_raw)==pre["MANIFEST"]["sha256"],"manifest preimage SHA drift")
        req(receipt["approval"]["owner_approval_received"] is False,
            "prewrite repository unexpectedly records owner approval")
        req(receipt["write_state"]["production_write_applied"] is False,
            "prewrite repository claims applied write")
    else:
        req(state=="post",f"unexpected v6.29 backend state: {state}")
        req(git_blob_sha(c0_raw)==post["STM32C0"]["git_blob_sha"],"C0 postimage blob drift")
        req(sha256(c0_raw)==post["STM32C0"]["sha256"],"C0 postimage SHA drift")
        req(len(c0_raw)==post["STM32C0"]["byte_count"],"C0 postimage byte-count drift")
        req(git_blob_sha(manifest_raw)==post["MANIFEST"]["git_blob_sha"],"manifest postimage blob drift")
        req(sha256(manifest_raw)==post["MANIFEST"]["sha256"],"manifest postimage SHA drift")
        req(len(manifest_raw)==post["MANIFEST"]["byte_count"],"manifest postimage byte-count drift")
        req(receipt["approval"]["owner_approval_received"] is True,"postwrite owner approval missing")
        req(receipt["approval"]["production_write_authorized"] is True,"postwrite authorization missing")
        req(receipt["approval"]["merge_after_green_ci_authorized"] is True,
            "postwrite merge authorization missing")
        req(receipt["write_state"]["production_write_applied"] is True,
            "postwrite receipt not marked applied")
        req(receipt["write_state"]["applied_commit"]==
            "37d61baf8e6d978116836ebdf40940a15ee42cb6",
            "postwrite applied commit drift")

        # Manifest inverse must reproduce the exact preimage.
        pre_manifest=deepcopy(manifest)
        pre_source=next(s for s in pre_manifest["sources"] if s["family"]=="STM32C0")
        pre_source["git_blob_sha"]=pre["STM32C0"]["git_blob_sha"]
        pre_source["sha256"]=pre["STM32C0"]["sha256"]
        pre_manifest_raw=render_manifest(pre_manifest)
        req(git_blob_sha(pre_manifest_raw)==pre["MANIFEST"]["git_blob_sha"],
            "manifest inverse does not reproduce frozen preimage blob")
        req(sha256(pre_manifest_raw)==pre["MANIFEST"]["sha256"],
            "manifest inverse does not reproduce frozen preimage SHA")

    # The only semantic C0 differences between current poststate and historical
    # prestate must be the five approved backend-field updates.
    current_by={row["icpn"]:row for row in c0_rows}
    pre_by={row["icpn"]:row for row in rewound}
    changed=[]
    for icpn,row in current_by.items():
        before=pre_by[icpn]
        diffs={k for k in FIELDS if row[k]!=before[k]}
        if diffs:
            req(diffs <= set(BACKEND_FIELDS),f"{icpn}: non-backend field changed: {sorted(diffs)}")
            changed.append(icpn)
    if state=="post":
        req(set(changed)==set(bindings()),f"postwrite changed exact-set drift: {sorted(changed)}")
    else:
        req(not changed,"prewrite state unexpectedly differs from reconstructed prestate")

    # Validate current Production aggregate state from all manifest sources.
    mapped=no_mapping=0
    rows_by_icpn={}
    for source in manifest["sources"]:
        path=(MANIFEST.parent/source["path"]).resolve()
        raw=path.read_bytes()
        req(git_blob_sha(raw)==source["git_blob_sha"],f"{source['family']}: manifest blob binding drift")
        req(sha256(raw)==source["sha256"],f"{source['family']}: manifest SHA binding drift")
        with path.open(newline="",encoding="utf-8") as handle:
            rows=list(csv.DictReader(handle))
        req(len(rows)==source["row_count"],f"{source['family']}: row count drift")
        for row in rows:
            req(row["icpn"] not in rows_by_icpn,f"{row['icpn']}: duplicate Production ICPN")
            rows_by_icpn[row["icpn"]]=row
            if row["mapping_status"]=="no_mapping":
                no_mapping+=1
            else:
                mapped+=1

    expected=receipt["expected_poststate"]
    if state=="post":
        req(mapped==expected["mapped"]==4059,f"mapped poststate drift: {mapped}")
        req(no_mapping==expected["no_mapping"]==570,f"no_mapping poststate drift: {no_mapping}")
        for icpn,binding in bindings().items():
            row=rows_by_icpn[icpn]
            for field in BACKEND_FIELDS:
                req(row[field]==binding[field],f"{icpn}: {field} postwrite drift")
    else:
        req(mapped==4054,f"mapped prestate drift: {mapped}")
        req(no_mapping==575,f"no_mapping prestate drift: {no_mapping}")

    req(sum(int(s["row_count"]) for s in manifest["sources"])==4629,
        "Production exact total drift")
    req(len(manifest["sources"])==28,"Production source count drift")

    for key,value in receipt["claims"].items():
        req(value is False,f"v6.29 overclaim: {key}")

    summary={
        "transaction_id":receipt["transaction_id"],
        "repository_write_state":state,
        "promotion_exact_count":5,
        "changed_exact_count":len(changed),
        "c0_current_git_blob_sha":git_blob_sha(c0_raw),
        "manifest_current_git_blob_sha":git_blob_sha(manifest_raw),
        "inverse_c0_preimage_git_blob_sha":git_blob_sha(pre_c0_raw),
        "mapped":mapped,
        "no_mapping":no_mapping,
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
