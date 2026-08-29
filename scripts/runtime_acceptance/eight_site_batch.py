from __future__ import annotations

import copy
import time

from common import AcceptanceError, Client, assert_job_image, build_image

SCENARIO = "eight-site-batch"


def run(client: Client) -> dict:
    target = client.discover_target(site_count=8)
    with client.deterministic_program(base_time_ms=5000):
        session_id = client.begin_session()
        image = build_image("runtime-acceptance-8site-64KiB.bin", multiplier=41, offset=17)
        status, accepted = client.request(
            "POST",
            "/api/batches",
            json_body={
                "session_id": session_id,
                "targets": [
                    {
                        "facility_id": target.facility_id,
                        "ppu_id": target.ppu_id,
                        "site_ids": list(range(1, 9)),
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
            },
            headers={"Idempotency-Key": client.idem("8site-batch")},
        )
        if status != 202 or accepted.get("ok") is not True:
            raise AcceptanceError("8-Site Batch creation failed")
        batch_id = str(accepted["batch"]["batch_id"])
        deadline = time.monotonic() + 60.0
        job_ids: dict[int, str] = {}
        max_running = 0
        eight_running_snapshot = None
        while True:
            batch = client.batch_status(batch_id)
            running = []
            for site in batch["sites"]:
                site_id = int(site["site_id"])
                if site.get("current_job_id"):
                    job_ids[site_id] = str(site["current_job_id"])
                if site["state"] == "running":
                    running.append(site_id)
            max_running = max(max_running, len(running))
            if len(running) == 8:
                eight_running_snapshot = copy.deepcopy(batch)
            if batch["state"] in {"success", "error", "partial", "cancelled"}:
                break
            if time.monotonic() >= deadline:
                raise AcceptanceError("8-Site Batch did not become terminal")
            time.sleep(0.05)

        if eight_running_snapshot is None or max_running != 8:
            raise AcceptanceError(f"never observed 8 simultaneous RUNNING Sites; max={max_running}/8")
        active_ids = {
            int(site["site_id"]): str(site["current_job_id"])
            for site in eight_running_snapshot["sites"]
        }
        if set(active_ids) != set(range(1, 9)) or len(set(active_ids.values())) != 8:
            raise AcceptanceError("8-Site RUNNING snapshot did not contain eight distinct active Jobs")
        if batch["state"] != "success":
            raise AcceptanceError(f"expected Batch success, got {batch['state']}")
        if batch["asset"]["sha256"] != image.sha256:
            raise AcceptanceError("8-Site Batch Asset SHA mismatch")
        if any(site["state"] != "success" for site in batch["sites"]):
            raise AcceptanceError("not every 8-Site Batch member succeeded")
        stats = batch["operation_statistics"]["program"]
        expected = {
            "logical_executions": 8,
            "attempts": 8,
            "retries": 0,
            "successful_executions": 8,
            "failed_executions": 0,
            "error_executions": 0,
        }
        for name, value in expected.items():
            if stats[name] != value:
                raise AcceptanceError(f"8-Site Batch statistic {name}={stats[name]}, expected {value}")
        if set(job_ids) != set(range(1, 9)):
            raise AcceptanceError(f"did not observe all eight Site Job IDs: {job_ids}")
        for site_id, job_id in job_ids.items():
            assert_job_image(client.job_status(target, job_id), image, site_id=site_id)

    return {
        "result": "PASS",
        "facility_id": target.facility_id,
        "ppu_id": target.ppu_id,
        "sites": list(range(1, 9)),
        "session_id": session_id,
        "batch_id": batch_id,
        "image_sha256": image.sha256,
        "job_ids": job_ids,
        "maximum_simultaneous_running_sites": max_running,
        "batch_state": batch["state"],
        "operation_statistics": stats,
    }
