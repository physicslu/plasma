from __future__ import annotations

import time
import urllib.parse

from common import AcceptanceError, Client, TERMINAL_BATCH_STATES, build_image

SCENARIO = "job-cancel"


def run(client: Client) -> dict:
    target = client.discover_target(minimum_sites=1)
    with client.deterministic_program(base_time_ms=8000):
        session_id = client.begin_session()
        image = build_image("runtime-acceptance-cancel-64KiB.bin", multiplier=31, offset=11)
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
            headers={"Idempotency-Key": client.idem("cancel-batch")},
        )
        if status != 202 or accepted.get("ok") is not True:
            raise AcceptanceError("cancel acceptance Batch submission failed")

        batch_id = str(accepted["batch"]["batch_id"])
        job_id: str | None = None
        deadline = time.monotonic() + 15.0
        while True:
            batch = client.batch_status(batch_id)
            sites = batch.get("sites") or []
            if len(sites) != 1 or int(sites[0]["site_id"]) != 1:
                raise AcceptanceError("cancel acceptance Batch membership mismatch")
            site = sites[0]
            if site.get("current_job_id"):
                job_id = str(site["current_job_id"])
            if site.get("state") == "running" and job_id:
                job = client.job_status(target, job_id)
                if job.get("state") == "running":
                    break
            if batch.get("state") in TERMINAL_BATCH_STATES:
                raise AcceptanceError(
                    f"Batch became terminal before cancel: {batch.get('state')}"
                )
            if time.monotonic() >= deadline:
                raise AcceptanceError("Batch Job did not reach running state before cancel deadline")
            time.sleep(0.1)

        encoded_batch = urllib.parse.quote(batch_id, safe="")
        cancel_status, cancel_response = client.request(
            "POST",
            f"/api/batches/{encoded_batch}/cancel",
            json_body={},
            headers={"Idempotency-Key": client.idem("cancel-request")},
        )
        if cancel_status != 200 or cancel_response.get("ok") is not True:
            raise AcceptanceError("Batch cancel request was not accepted")
        cancel_snapshot = cancel_response.get("batch") or {}
        if str(cancel_snapshot.get("batch_id") or "") != batch_id:
            raise AcceptanceError("Batch cancel response identity mismatch")
        if cancel_snapshot.get("cancel_requested") is not True:
            raise AcceptanceError("Batch cancel response did not record cancel_requested")

        deadline = time.monotonic() + 30.0
        while True:
            final_batch = client.batch_status(batch_id)
            if final_batch.get("state") in TERMINAL_BATCH_STATES:
                break
            if time.monotonic() >= deadline:
                raise AcceptanceError("cancelled Batch did not become terminal")
            time.sleep(0.1)

        if final_batch.get("state") != "cancelled":
            raise AcceptanceError(
                f"expected cancelled Batch terminal state, got {final_batch.get('state')}"
            )
        final_sites = final_batch.get("sites") or []
        if len(final_sites) != 1 or final_sites[0].get("state") != "cancelled":
            raise AcceptanceError("cancelled Batch did not converge to cancelled Site state")
        if final_batch.get("cancel_requested") is not True:
            raise AcceptanceError("terminal cancelled Batch lost cancel_requested evidence")
        if not job_id:
            raise AcceptanceError("cancel acceptance Batch never exposed an underlying Job ID")

        final_job = client.wait_job(target, job_id, timeout=30.0)
        if final_job.get("state") != "cancelled":
            raise AcceptanceError(
                f"expected underlying Job cancelled state, got {final_job.get('state')}"
            )
        result = final_job.get("result") or {}
        if result.get("state") != "cancelled":
            raise AcceptanceError("cancelled Job has non-cancelled result")

    return {
        "result": "PASS",
        "facility_id": target.facility_id,
        "ppu_id": target.ppu_id,
        "site_id": 1,
        "session_id": session_id,
        "image_sha256": image.sha256,
        "batch_id": batch_id,
        "job_id": job_id,
        "submission_route": "/api/batches",
        "cancel_route": f"/api/batches/{batch_id}/cancel",
        "running_observed": True,
        "cancel_request_accepted": True,
        "batch_state": final_batch["state"],
        "site_state": final_sites[0]["state"],
        "job_state": final_job["state"],
    }
