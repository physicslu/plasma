from __future__ import annotations

import time

from common import AcceptanceError, Client, assert_job_image, build_image

SCENARIO = "pmode-batch"


def run(client: Client) -> dict:
    target = client.discover_target(minimum_sites=2)
    with client.deterministic_program(base_time_ms=3000):
        session_id = client.begin_session()
        image = build_image("runtime-acceptance-pmode-64KiB.bin")
        batch_request = {
            "session_id": session_id,
            "targets": [
                {
                    "facility_id": target.facility_id,
                    "ppu_id": target.ppu_id,
                    "site_ids": [1, 2],
                }
            ],
            "operations": ["program"],
            "execution_policy": {
                "repeat_count": 1,
                "site_retry_limit": 0,
                "failed_site_stop_threshold": None,
            },
            "asset": {
                "asset_name": image.name,
                "asset_type": "image",
                "asset_format": "binary",
                "asset_size": image.size,
                "asset_sha256": image.sha256,
                "asset_base64": image.base64,
            },
        }
        status, accepted = client.request(
            "POST",
            "/api/batches",
            json_body=batch_request,
            headers={"Idempotency-Key": client.idem("pmode-batch")},
        )
        if status != 202 or accepted.get("ok") is not True:
            raise AcceptanceError("PMode Batch creation failed")
        batch_id = str(accepted["batch"]["batch_id"])
        job_ids: dict[int, str] = {}
        deadline = time.monotonic() + 60.0
        while True:
            batch = client.batch_status(batch_id)
            for site in batch["sites"]:
                if site.get("current_job_id"):
                    job_ids[int(site["site_id"])] = str(site["current_job_id"])
            if batch["state"] in {"success", "error", "partial", "cancelled"}:
                break
            if time.monotonic() >= deadline:
                raise AcceptanceError("PMode Batch did not become terminal")
            time.sleep(0.05)

        if batch["state"] != "success":
            raise AcceptanceError(f"expected Batch success, got {batch['state']}")
        if batch["asset"]["sha256"] != image.sha256:
            raise AcceptanceError("Batch Asset SHA mismatch")
        if sorted(int(site["site_id"]) for site in batch["sites"]) != [1, 2]:
            raise AcceptanceError("Batch membership mismatch")
        if any(site["state"] != "success" for site in batch["sites"]):
            raise AcceptanceError("not every Batch Site succeeded")
        stats = batch["operation_statistics"]["program"]
        if stats["logical_executions"] != 2 or stats["attempts"] != 2:
            raise AcceptanceError("Batch Program statistics do not match two-Site execution")
        if set(job_ids) != {1, 2}:
            raise AcceptanceError(f"did not observe both Site Job IDs: {job_ids}")
        for site_id, job_id in job_ids.items():
            assert_job_image(client.job_status(target, job_id), image, site_id=site_id)

    return {
        "result": "PASS",
        "facility_id": target.facility_id,
        "ppu_id": target.ppu_id,
        "sites": [1, 2],
        "session_id": session_id,
        "batch_id": batch_id,
        "image_sha256": image.sha256,
        "job_ids": job_ids,
        "batch_state": batch["state"],
        "logical_executions": stats["logical_executions"],
        "attempts": stats["attempts"],
    }
