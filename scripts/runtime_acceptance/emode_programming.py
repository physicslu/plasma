from __future__ import annotations

import time

from common import AcceptanceError, Client, assert_job_image, build_image

SCENARIO = "emode-programming"


def run(client: Client) -> dict:
    target = client.discover_target(minimum_sites=1)
    with client.deterministic_program(base_time_ms=500):
        session_id = client.begin_session()
        image = build_image("runtime-acceptance-emode-64KiB.bin", multiplier=31, offset=11)
        batch_request = {
            "session_id": session_id,
            "targets": [
                {
                    "facility_id": target.facility_id,
                    "ppu_id": target.ppu_id,
                    "site_ids": [1],
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
            headers={"Idempotency-Key": client.idem("emode-batch")},
        )
        if status != 202 or accepted.get("ok") is not True:
            raise AcceptanceError("EMode server-side Batch creation failed")

        batch_id = str(accepted["batch"]["batch_id"])
        job_id: str | None = None
        deadline = time.monotonic() + 60.0
        while True:
            batch = client.batch_status(batch_id)
            sites = batch.get("sites") or []
            if len(sites) != 1 or int(sites[0]["site_id"]) != 1:
                raise AcceptanceError("EMode Batch membership mismatch")
            if sites[0].get("current_job_id"):
                job_id = str(sites[0]["current_job_id"])
            if batch["state"] in {"success", "error", "partial", "cancelled"}:
                break
            if time.monotonic() >= deadline:
                raise AcceptanceError("EMode Batch did not become terminal")
            time.sleep(0.05)

        if batch["state"] != "success":
            raise AcceptanceError(f"expected EMode Batch success, got {batch['state']}")
        asset = batch.get("asset") or {}
        if asset.get("sha256") != image.sha256 or int(asset.get("size_bytes", -1)) != image.size:
            raise AcceptanceError("EMode Batch Asset binding mismatch")
        site = batch["sites"][0]
        if site["state"] != "success":
            raise AcceptanceError(f"expected EMode Site success, got {site['state']}")
        stats = batch["operation_statistics"]["program"]
        if stats["logical_executions"] != 1 or stats["attempts"] != 1:
            raise AcceptanceError("EMode Program statistics do not match one-Site execution")
        if not job_id:
            raise AcceptanceError("EMode Batch did not expose the underlying Job ID")
        job = client.job_status(target, job_id)
        assert_job_image(job, image, site_id=1)

    return {
        "result": "PASS",
        "facility_id": target.facility_id,
        "ppu_id": target.ppu_id,
        "site_id": 1,
        "session_id": session_id,
        "batch_id": batch_id,
        "job_id": job_id,
        "submission_route": "/api/batches",
        "asset_transport": "server-side-batch-envelope",
        "image": {"name": image.name, "size": image.size, "sha256": image.sha256},
        "batch_state": batch["state"],
        "site_state": site["state"],
        "logical_executions": stats["logical_executions"],
        "attempts": stats["attempts"],
    }
