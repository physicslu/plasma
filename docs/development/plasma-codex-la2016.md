# PLASMA Issue #981 — Codex Agent → KINGST LA2016 bounded hardware acceptance

**Gate 1 approved. Gate 2 merge approval is mandatory before triggering the real instrument.** Owner confirmed the 2026-10-16 **PWM1 → same LA2016 CH0** physical jumper remains installed. All PR CI is host-only/offline, never runs on hardware-enabled SWPC.

## What this actually proves

Previous [real archived LA loopback](../evidence/la2016-pwm-loopback/2026-10-16/README.md) and earlier dedicated-worker USB DAC permission checks do not prove that a real Codex Agent can initiate a new acquisition. This procedure requires a **real, noninteractive `codex exec`** to create an exact, user-scoped capability **request** (JSON), then a **separate trusted supervisor** validates its contents and runs the only allowed KINGST CLI operations, parses *fresh* .sr samples and verifies PWM1 OFF. GitHub Actions alone never substitutes a fixed script result for a Codex agent result. Codex is the request originator; only the supervisor exercises instrument USB.

Two fixed cases at 1 MHz samplerate, 1.40 V was the archived threshold (not a fresh analog voltage measurement):

| Profile | Requested PWM1 | Expected CH0 cycle | Minimum complete cycles |
| --- | --- | --- | --- |
| A | 1 kHz, 50% | 1000 samples/cycle, 500 High | 20 |
| B | 2 kHz, 25% | 500 samples/cycle, 125 High | 20 |

Period/high durations must match within **±1 sample** (1 µs). Each case demands a *new* OFF command then a separate CH0 OFF capture with ≥20,000 all-Low samples. Supervisor issues a final OFF again. Only after **both** cases + final OFF success and a real Codex JSON request may it report `PASS_REAL_AGENT_LA2016_LOOPBACK`. A stale archived .sr, empty data, wrong duty/frequency, absent OFF readback, missing agent request, or changed test profile is always NO-GO.

The supervisor saves fresh raw .sr captures temporarily on SWPC, but uploads only a sanitized report, digital CH0 transition CSVs, exit_code and SHA256SUMS to GitHub. Report includes hashes of the private .sr files; it never publishes raw USB logs, unique device serial, bus/device address or passwords. The transition CSVs are deliberately reconstructed from samples, not model-generated.

## Actual trust separation

- Exact owner Issue #981 comment `/plasma-codex la2016 981` is authorizer-checked on **GitHub-hosted** runner; reference must be merged `main` pinned to a commit SHA. PR code can never run on the hardware worker. Readonly repository checkout, no persistent Git credentials; dedicated `SWPC-plasma-codex` Linux identity and nonroot groups checked.
- `scripts/plasma-codex-la2016.py` builds a **fixed prompt** referring only to public archived evidence and the previously confirmed single-device wiring. It launches an actual `codex --ask-for-approval never exec --sandbox read-only`.
- **Mandatory bubblewrap mount isolation**: agent namespace is mounted read-only, `--dev /dev` substitutes minimal devfs and hides real `/dev/bus/usb`, serial and MMIO nodes; only `agent` output subdirectory and the dedicated Codex session directory are writable. Private Z2 credentials and SSH account folder are masked, no sudo escalation. If `bwrap` cannot run on SWPC, **NO-GO**. Codex network connectivity remains needed for the model; this is not full network confinement or a defense against compromise of its own Codex credentials. Runner labels/prompt-only rules are **not** isolation.
- The agent emits only JSON, **not arbitrary commands or arguments**. Strict parser refuses unknown keys, swapped/extra/boolean profiles, different instruments, skipping shutdown or arbitrary argv. It cannot forge the out-of-sandbox `pwm-off-confirmed` marker. No agent output is executed as shell or Python.
- Separate supervisor requires the exact previous SHA256-pinned KINGST AppImage at `/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage`, a uniquely mapped current `77a1:01a2` USB node, RW DAC and no detected `fuser` owner. The supervisor holds `/run/lock/plasma-la2016.lock` for the entire acquisition. Lock is **advisory**; noncooperating programs and process-visibility limitations remain hazards. Stop if instrument ownership cannot be established.
- Driver uses only `kingst-la2016:conn=<current-sysfs-bus.dev>` and fixed one-case CLI arguments. Existing archive showed no LA FPGA upload. Do not silently choose an unrelated system sigrok binary or supply old bus/device addresses.
- Instrument supervisor has per-invocation timeouts. Every normal exception and termination attempts PWM OFF. A separate, detached **125-second deadman** makes an independent bounded OFF attempt if the supervisor dies/hangs before confirming shutdown. A deadman is *not* an absolute guarantee in the event of SWPC loss, USB/kernel hangs, and SIGKILL during USB transfer. There is no USB hub power or DUT fallback. Owner should remain able to verify PWM1 OFF locally.

## Operator, dependencies and approval boundaries

Known from the 2026-10-17 passive inventory: USB VID/PID `77a1:01a2` and RW DAC were detected under `plasma-codex`, but pinned AppImage installation was **NOT_CONFIGURED** and bubblewrap availability was **NOT TESTED**. Therefore **do not assume the hardware test can start**. Before any PWM emission, supervisor checks the pin, bwrap + codex CLI, unique physical USB enumeration and a free device. Missing prerequisites → NO-GO without PWM emission; do not replace pinned driver with unknown binary.

Once a specifically reviewed PR gets Gate 2 merged, an approved owner can dispatch **one** run with the exact GitHub Issue command:

`/plasma-codex la2016 981`

Operator may watch a temporary sanitized tmux:

`tmux -S /run/plasma-codex/la2016-<RUN_ID>.sock attach-session -r -t plasma-la2016-<RUN_ID>`

No Z2 FPGA Manager/Bitstream, USB Hub switching, JTAG, external DUT, reset, voltage change or IC Flash operations are permitted in this task. The only electrical output is LA2016 PWM1 connected to the same instrument's CH0 as physically confirmed by the owner.

## Evidence semantics and limitations

- `agent_exec=PASS` means actual Codex process returned zero and the exact JSON request parsed successfully; the model may not improvise test parameters.
- `result=PASS_REAL_AGENT_LA2016_LOOPBACK` requires fresh per-case measured signal and all-Low OFF recordings, plus command-level final shutdown success.
- `NO_GO` or `NO_GO_PWM_SHUTDOWN` means **no verified hardware success**, not that the hardware is necessarily powered off. Look at on-host watchdog/final OFF outcome and manually confirm PWM safety when ambiguous.
- A Python/codex timeout does not establish physical PWM shutdown; independent observation is strictly stronger than a CLI `--set enabled=off` success, which only reports the driver's command state.
- This is same-device digital timing validation, not an independent analog voltage/frequency calibration and **not** a Z2 or PLASMA SWD test.

All physical actuation is deferred until Gate 2 and actual preflight pass. No PR auto-merge, no unreviewed Codex software updates or new firmware provisioning. Reuse existing SHA256 archive verifier for historical cases; regression here uses synthetic .sr archives with the same metadata and CH0 data ABI.
