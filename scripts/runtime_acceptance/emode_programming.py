from __future__ import annotations

from common import AcceptanceError, Client, assert_job_image, build_image

SCENARIO = "emode-programming"


def run(client: Client) -> dict:
    target = client.discover_target(minimum_sites=1)
    with client.deterministic_program(base_time_ms=500):
        session_id = client.begin_session()
        image = build_image("runtime-acceptance-emode-64KiB.bin", multiplier=31, offset=11)
        cache = client.cache_image(target, session_id, image)
        status, submitted = client.request(
            "POST",
            f"{client.target_url(target)}/api/jobs",
            json_body={
                "site_id": 1,
                "operation": "program",
                "session_id": session_id,
                "asset_sha256": image.sha256,
                "execution_owner_id": "runtime-acceptance-emode",
            },
            headers={"Idempotency-Key": client.idem("emode-job")},
        )
        if status not in {200, 201, 202} or submitted.get("ok") is not True:
            raise AcceptanceError("EMode Job submission failed")
        job_id = str(submitted["job"]["job_id"])
        job = client.wait_job(target, job_id)
        assert_job_image(job, image, site_id=1)

        check_status, checked = client.request(
            "POST",
            f"{client.target_url(target)}/api/programming-assets/check",
            json_body={
                "session_id": session_id,
                "asset_name": image.name,
                "asset_type": "image",
                "asset_format": "binary",
                "asset_size": image.size,
                "asset_sha256": image.sha256,
            },
            headers={"Idempotency-Key": client.idem("emode-cache-hit")},
        )
        if check_status not in {200, 201} or checked["programming_asset"]["cache_hit"] is not True:
            raise AcceptanceError("same-session same-Image cache HIT was not observed")

    return {
        "result": "PASS",
        "facility_id": target.facility_id,
        "ppu_id": target.ppu_id,
        "site_id": 1,
        "session_id": session_id,
        "image": {"name": image.name, "size": image.size, "sha256": image.sha256},
        "job_id": job_id,
        "initial_cache_hit": cache["initial_cache_hit"],
        "uploaded": cache["uploaded"],
        "same_session_cache_hit": True,
        "terminal_state": job["state"],
    }
