# PR #1428: reload repair and Path 3 admission — 2026-11-15

Source: `5316cdd907df2834e2cd0b17cb798abd99f39b1a`, Draft [PR #1428](https://github.com/physicslu/plasma/pull/1428). Owner Work Order SHA256: `917e6ae2f5b5da336b270d0492ea0dc91068eb3635ab6d04fdc73cdbd29b4eea`. Path 3, `SWPC-plasma-codex`, [run 43614887886 / job 132507745645](https://github.com/physicslu/plasma/actions/runs/43614887886/job/132507745645).

## Reload diagnosis and repair

The original [Web validation run 43611021844](https://github.com/physicslu/plasma/actions/runs/43611021844) failed 4 of 192 Playwright tests. Artifact `14120935075` ZIP SHA256 was independently verified as `5e9d0209cdef80159ce83f7f2df79c3fcd239620b469554d05ce792db2c48a61`.

The two reload traces contain 1,384 journal GETs each within approximately 20 seconds (one request was interrupted in the UNKNOWN trace); successful responses rule out an unavailable Manager endpoint as their cause. `setManagedTopology` recreated `logManagedBatch`, then `pollManagedBatch`, then the topology/restore effect, repeatedly cancelling and restarting observation. The logger now takes topology as an explicit observation argument, so these callbacks remain stable. Restored terminal records also reach the Factory Log.

Start and Batch recovery holds load before asynchronous Fleet/Route discovery. A Start remains immutable through an accepted running Batch, reload, missing journal, unknown outcome and rejected PASS evidence. An older tab's persisted Batch ID without a Start also blocks resubmission until read. A journal response with another Batch/Start identity cannot overwrite the hold. The readiness warning exposes `OUTCOME_UNKNOWN` before IC selection; only a definitive refusal or verified terminal journal can clear the ordinary hold.

The obsolete PMode Flash Cycle/disabled Retry assertions now check three selected E/P/V controls and enabled Manager Retry at both widths. Negative regressions cover an unavailable journal with and without the older Start record, read-only recovery, bounded reload observation, and a mismatched Start response. A 4xx log assertion was scoped to the Factory Log because the same reason is also rendered in its operator warning.

## Validation

Final local validation: **PASS** — lint (0 errors, 2 existing warnings), build plus **288** source/SSR/unit tests, artifact validation, **202** Manager regression tests, **194/194** full Playwright and **24/24** final focused Playwright. The full run collected tests before the last added mismatch negative; the focused run covers that case and all affected cases on the final source. Their union covers all **195 current E2E cases**. These are host-only results; exact log hashes are in `observation.json`. The isolated E2E configuration uses port 4273 and an unused Gateway proxy port to reproduce hosted CI's absent-Gateway condition without stopping the live lab Gateway on 18080. No snapshot expectations were rewritten.

The trusted workflow requires the candidate checkout to remain at its pinned SHA and commits/pushes its source diff in the post-step. The resulting publication SHA and hosted CI on that commit cannot be observed from inside the still-running Codex step. Do not interpret this report as completed publication or Gate 2 readiness.

## Hardware: NOT_RUN after read-only admission

Pinned SSH/sudo access to the enrolled Z2 succeeded. Same-boot Root journal, protected source verification, paired bitstream/manifest hashes, Golden hash, absence of seals/admission records/live OpenOCD, and available MMIO/per-Site locks were observed. PPU `z2-hil`, boot `4cefdc0c-f586-4d19-b126-1d8e1108c8f1`, image `z2-independent-swd-v5-d0add58c`; the selected PS-local ABI-v5 engine remains at **2 MHz**. The existing PPU runtime release identifies source `6323ad90ae34920cc8b34291846476c5bd40137f`. This is distinct from the candidate source.

**The deployed active Provider declares `plasma.ppu.provider-capabilities.v1` with `sites:[1]`.** Reconstructing Resource Set v2 from its actual stored, hash-checked package bytes using the candidate parser fails `ROUTE_CAPABILITIES_INVALID`. The live report's `state=VERIFIED` and resource hash therefore do not establish candidate v2 compatibility. No v1 Flash was substituted for the required v2 HIL.

The live SWPC Manager/BFF listening sockets on 18280/18190 belong to UID 1000 (`gordon`); the runner is UID 998. Its own Control Station profile is absent and `sudo -n -l` requires a password. The workspace contract excludes reading another operator's private profile/credentials. A safe synchronized candidate Control Station/PPU upgrade through the existing enrolled owner's deployment route is required; replacing that controller identity or upgrading Z2 alone would not resolve this compatibility boundary. This is an observed access/configuration blocker, not an additional approval Gate or a general deployment ban.

LA2016 AppImage SHA and current USB RW access passed; native Driver `--show` succeeded. **5 MHz SWD / 100 MHz waveform, new Erase/Program/Verify, Job/Batch/Receipt/SAFE_OFF, Site 2 and multi-Site HIL are NOT_RUN.** No independent current Site 2 fixture was established. No FPGA load, engine-selection change, service restart, controller re-enrollment, DUT write, PWM output or recovery occurred. Historical [2 MHz Site 1 evidence](../site1-hil-la2016-2026-11-14/QUALIFICATION.md) is preserved without reclassification; neither digital LA status nor software admission proves analog voltage or target-power SAFE_OFF.

Exact identities and raw-evidence hashes are in `observation.json`. Raw non-secret engineering evidence remains under the runner's `.plasma-path3-evidence` artifact directory. No private credentials or raw Codex transcript are included in this source report. PR remains Draft; no merge authorized or attempted. Gate 2 remains outstanding after publication, final-commit CI and unresolved hardware acceptance.
