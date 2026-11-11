# NOT_VERIFIED / NOT_CAPTURED — Console Browser Resource Reuse HIL, 2026-11-11

Nothing was re-run to fill these gaps.

| Item | Status | What exists instead |
| --- | --- | --- |
| Browser screenshot of the Console result | NOT_CAPTURED | The owner's report of the Console display (`PASS`, `RESOURCE_REUSE: PPU_VERIFIED`, `SAFE_OFF VERIFIED`). |
| Proof that the run was started from the browser UI | NOT_VERIFIED | No record separates a browser request from a scripted one: the Manager run record carries no client identity, the Console/BFF service logs no requests, and the Manager logged one unrelated relay line in 00:20–00:25Z. Browser origin rests on the owner's statement. |
| JavaScript bundle version loaded in the browser | NOT_CAPTURED | The installed release is `728e55e529b5` and the Console service has not restarted since 2026-11-10T14:11:36Z. |
| Raw OpenOCD log | NOT_CAPTURED | The Job directory holds only `job_state.json` and `result.json`; no OpenOCD-named file newer than 2026-11-11T00:00Z was found; the Site Worker, Server and Web units wrote nothing to the system journal in the Job window. The Job result reports `openocd_rc` 0. |
| Independent Flash dump | NOT_CAPTURED | The Job's `readback_sha256` equals the image SHA256, with `bytes_verified` 18,768. |
| FPGA not reloaded | NOT independently verified for this Job | No snapshot was taken immediately before the Job. Supporting evidence is listed in the README; the nearest earlier snapshot is 2026-11-10T14:14:30Z. A reload that left the identity file, deployment records and service processes untouched would not show in it. |
| G13 request signature | NOT_VERIFIED directly | No signed request or Gateway admission log was captured. The Job was accepted under controller generation 2, mode `NORMAL`. |
| Site seal | NOT_VERIFIED directly | No file named `*seal*`, `*outcome*` or `*quarantine*` exists under the searched Runtime, Bootstrap, `/run/plasma*` and `/etc/plasma` trees (depth 5); the Gateway reports Site 2 `idle` with no current Job and no lease owner. The Site Worker's internal seal state was not queried. |
| Manager plan record | NOT_CAPTURED as a separate file | Plans are not journaled. The plan is embedded in the run record (`plan_id` `9521e014…`). Plans requested but never run leave no record, so their count is unknown. |
| On-disk `job_state.json` / `result.json` on Z2 | Not copied | The Gateway response for the Job was saved; the two files were listed by name, size and mtime only. |
| Full Manager journal file | Not committed | Only the matching run record is committed, with the file's SHA256 and a one-line summary per run. |
| SWPC–Z2 clock offset | NOT_VERIFIED | Timeline entries from the two hosts are ordered as recorded. |
| DUT behaviour after flashing (USB CDC), DUT electrical state | NOT_VERIFIED | Not observed. |
| Scope | — | One Site, one IC, one Job. Not an 8-Site or repeatability result. |
