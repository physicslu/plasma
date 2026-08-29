from __future__ import annotations

import time
import urllib.parse

from common import AcceptanceError, Client, TERMINAL_JOB_STATES, build_image

SCENARIO = "job-cancel"


def run(client: Client) -> dict:
    target = client.discover_target(minimum_sites=1)
    with client.deterministic_program(base_time_ms=8000):
        session_id = client.begin_session()
        image = build_image("runtime-acceptance-cancel-64KiB.bin", multiplier=31, offset=11)
        client.cache_image(target, session_id, image)
        status, submitted = client.request(
            "POST",
            f"{client.target_url(target)}/api/jobs",
            json_body={
                "site_id": 1,
                "operation": "program",
                "session_id": session_id,
                "asset_sha256": image.sha256,
                "execution_owner_id": "runtime-acceptance-cancel",
            },
            headers={"Idempotency-Key": client.idem("cancel-job")},
        )
        if status not in {200, 201, 202} or submitted.get("ok") is not True:
            raise AcceptanceError("cancel acceptance Job submission failed")
        job_id = str(submitted["job"]["job_id"])

        deadline = time.monotonic() + 15.0
        while True:
            job = client.job_status(target, job_id)
            if job["state"] == "running":
                break
            if job["state"] in TERMINAL_JOB_STATES:
                raise AcceptanceError(f"Job became terminal before cancel: {job['state']}")
            if time.monotonic() >= deadline:
                raise AcceptanceError("Job did not reach running state before cancel deadline")
            time.sleep(0.1)

        encoded = urllib.parse.quote(job_id, safe="")
        cancel_status, cancel_response = client.request(
            "POST",
            f"{client.target_url(target)}/api/jobs/{encoded}/cancel",
            json_body={},
            headers={"Idempotency-Key": client.idem("cancel-request")},
        )
        if cancel_status != 200 or cancel_response.get("ok") is not True:
            raise AcceptanceError("Job cancel request was not accepted")
        final_job = client.wait_job(target, job_id, timeout=30.0)
        if final_job["state"] != "cancelled":
            raise AcceptanceError(f"expected cancelled terminal state, got {final_job['state']}")
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
        "job_id": job_id,
        "running_observed": True,
        "cancel_request_accepted": True,
        "terminal_state": final_job["state"],
    }
