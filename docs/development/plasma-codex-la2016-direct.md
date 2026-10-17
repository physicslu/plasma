# PLASMA Issue #981 — LA2016 Codex Direct Execution A/B (Gate 1 only)

**Status: proposed, not deployed.** Owner has explicitly approved **Gate 1 development and offline tests** only. Gate 2 is required for merge; a **separate one-shot explicit owner approval** is required before ever creating the hardware-triggering Issue comment.

## Hypothesis and controlled comparison

The archival real 2026-10-16 `KINGST PWM1 → same LA2016 CH0` loopback was functional PASS using the pinned sigrok AppImage and host Codex. On 2026-10-17 the reviewed Python JSON Supervisor pathway was NO_GO, followed by a read-only diagnosis showing `pinned_appimage=PASS`, `usb_metadata_dac_owner=PASS`, `runner_codex_cli=PASS`, `bwrap_usb_isolation=PASS`, `codex_readonly_request=AGENT_REQUEST_SCHEMA`. This establishes a failure in JSON request validation, **not** a Codex CLI failure or a physical test result.

This A/B experiment **does not remove the old implementation**. It adds a parallel direct path using the **same** dedicated SWPC `plasma-codex` worker, pinned AppImage SHA `b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475`, same loopback wiring, same PWM profiles, same sampling resolution, but **no intermediate JSON request/action dispatch**.

| Dimension | Existing indirect path | Proposed direct path |
| --- | --- | --- |
| Github | Exact owner Issue #981 command, hosted authorizer | Separate exact owner command, hosted authorizer |
| Linux worker | Dedicated `SWPC-plasma-codex` | Same worker |
| Codex | Return fixed JSON action request | Executes sigrok commands itself in its own tool calls |
| Hardware CLI | Reviewed Python Supervisor constructs settings | Codex dynamically discovers and runs pinned sigrok-cli |
| Device isolation | bwrap hides ALL USB nodes from model | bwrap exposes ONLY one dynamically resolved LA2016 USB character node |
| File access | Read-only workspace | Read-only host with dedicated isolated temp and writable evidence folder |
| OFF | Parent shutdown + detached deadline watchdog | **Minimal independent OFF deadline guard** + final host OFF attempt |
| Acceptance | Supervisor captures/measures and reports | Agent records four original .sr; **separate deterministic post-test verifier** checks period, duty, OFF-low and SHA256 |

**This isolates one hypothesis**, but a positive direct-mode result would not prove that the Python Supervisor was the only problem. It demonstrates that the same worker can run a real Codex-controlled LA2016 capture without the JSON mediator.

## Implementation

- `scripts/plasma-codex-la2016-direct.py`: one run entry, exact owner event matcher, SHA-pinned AppImage, USB sysfs identity and passive `fuser` check, rootless bubblewrap LA-only mount namespace, actual Codex CLI, minimal timed OFF guard and final OFF attempt, post-test waveform verification, sanitized report.
- `.github/workflows/plasma-codex-la2016-direct.yml`: GitHub-hosted authorization and fully offline PR CI; **no self-hosted job is enabled for PR or push**. The dedicated SWPC Runner is reached only on exact owner-created Issue comment on merged, pinned `main`.
- `scripts/tests/test-plasma-codex-la2016-direct.py`: offline negative authorization tests, exact archived waveform replay, wrong-duty rejects, malformed archive rejects, OFF command structure, namespace construction, no unverified worker.
- No deletion or modification of old `scripts/plasma-codex-la2016.py`, original workflow, Z2 or programming runtime.

After Gate 2 merge, a separately owner-authorized **single physical** Issue #981 trigger would be:

```text
/plasma-codex la2016-direct 981
```

Do not post this command without a fresh explicit owner approval for **one bounded real LA2016 PWM test**.

## Outer security boundary vs Codex shell privileges

Codex is purposely a **direct actuator**, not merely an intent generator. Codex's inner sandbox must permit native USB ioctls; the command selects `--sandbox danger-full-access` **inside** an already established rootless `bubblewrap` mount namespace. The wrapper uses host read-only mount, mounts fresh `/dev`, bind-exposes only the single validated LA2016 USB device, masks private Z2 SSH/credential directories, and only makes the private evidence folder, temporary directory and Codex's own auth directory writable. No root/privileged Linux group is added; no host-level `sudo`, Docker, USB Hub power, Z2 login, FPGA Manager or DUT controls are invoked by the host wrapper.

This gives OS-level **filesystem/device** isolation, but is not complete security against all network paths. The Codex process still needs network egress for the model API; the current proposal uses a reviewed fixed prompt banning Z2 and other hosts, masks private credentials, and does not claim an enforced per-destination network firewall. In addition, the `plasma-codex-io` host group can access more physical devices *outside* the sandbox; the launcher must always run inside the device-limited namespace. Therefore this proposal must pass the actual **LA-only namespace preflight on the same Runner** before any PWM actuation; a hosted CI construction test alone cannot prove Linux mount/kernel compatibility or external electrical isolation.

No runtime workflow is executed until the separate hardware test authorization. Do not confuse a successful hosted CI with a real device grant validation.

## Independent OFF and evidentiary integrity

- Before running Codex, the parent must verify the current USB connection is unique, AppImage SHA matches, USB node accessible/not busy, and bwrap child can see exactly one LA USB node but no `/dev/mem` or `/dev/ttyUSB*`.
- The parent arms an independent detached 135-second OFF timer (removes GitHub tracking tag); if Codex dies or stalls before a host-confirmed shutdown receipt, it attempts `PWM1:enabled=off`.
- The parent permits no more than 118 seconds of Codex runtime. It attempts a second bounded OFF in its `finally` path whether the model succeeded, failed, timed out, or failed evidence validation.
- The timer or `finally` cannot guarantee actual physical OFF after host crash, USB disconnect, kernel hang, malformed device state or power loss. Prior to real usage, an independent operator must verify wiring and an emergency instrument OFF method. No hardware-power toggle is granted.
- Codex uses explicit PWM ON and OFF commands; four independent original captures: `1000hz-on.sr`, `1000hz-off.sr`, `2000hz-on.sr`, `2000hz-off.sr`. All non-digital model logs and last messages stay **private** on SWPC and are **not uploaded** to GitHub Actions.
- The trusted post-test verifier uses only bounded sigrok archives: CH0 metadata, 1 MHz sampling, 16-bit words, ≥20 complete cycles, expected periods and highs within ±1 sample, 20,000 or more OFF samples **all LOW**, distinct file sizes and SHA256 checks. The reported PASS requires both cases plus the host OFF command; the parent computes hashes on exact original .sr archives.
- Return NO_GO on missing, malformed, busy, ambiguous or mismatched evidence. No synthetic or archived replay is accepted in an actual Runner job. PR CI safely runs the identical verifier against **existing** archived captures as test fixtures, never reuses them as new device acceptance.

**Comparison boundary:** The earlier diagnostic's `SIGROK_FIRMWARE_PATH=NOT_CONFIGURED_INFORMATIONAL` did not imply failing firmware. An AppImage's presence/digest is not proof the live sigrok CLI can open the device. The direct physical acceptance is exactly what will test that.

## Gate structure

1. **Gate 1 (approved):** introduce the new parallel workflow/script/host-only regression tests and this documentation; submit PR; finish all hosted offline CI. No SWPC execution.
2. **Gate 2 (not yet authorized):** owner reviews exact PR HEAD, latest main, mergeability, complete CI; merge only after explicit approval.
3. **Hardware acceptance (not yet authorized):** separate explicit one-shot owner approval, then one exact Issue command on merged main. Do not retry on failure without fresh approval.
4. Only if real direct A/B acceptance passes: consider a **separate** PR retiring JSON Supervisor; never silently delete the old route.

## Open design/qualification limitations

- Outer `bubblewrap` LA-only USB bind mounting on this specific SWPC kernel is unqualified until the one-shot real Runner job. The existing read-only probe verified an **all-USB-hidden** namespace, which is not the same case.
- Native sigrok/AppImage extraction needs a writable temporary directory, provided by isolated `/tmp`. The firmware lookup environment may require additional local qualification; no firmware is installed or uploaded by this proposal.
- Runtime USB permission alone is insufficient if a different process holds the device. Race conditions beyond an advisory `fuser`+file lock require physical acceptance.
- Codex may still fail or refuse shell work, or produce invalid files. Those are honest NO_GO, not evidence that the old Supervisor is needed.
