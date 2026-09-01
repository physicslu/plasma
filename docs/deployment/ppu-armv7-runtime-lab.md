# PPU ARMv7 Runtime Lab

The SWPC ARMv7 Runtime Lab is a software-only diagnostic harness for the packaged PPU runtime. It automates the manual QEMU/Docker procedure used to validate ARMv7 execution and to isolate Gateway memory growth by request path.

## Scope

The lab proves only SWPC/QEMU ARMv7 userspace behavior. It does not claim PYNQ-Z2 hardware, systemd boot/reboot, PS-to-PL, Site I/O, target power, real IC programming, or native Z2 memory stability.

The default runtime build directory is repository-local:

```text
$PLASMA_REPO/.work/ppu-runtime
```

The default report is:

```text
$PLASMA_REPO/.work/reports/ppu-armv7-runtime-lab.json
```

The runtime directory is created on the integration host and mounted read-only into Docker. The container must not write the host runtime artifact; this prevents root-owned runtime files from contaminating the repository workspace. The JSON report is emitted by the container and written by the host process so it also remains host-owned.

## One-command run

From the repository root on the integration host:

```bash
source software/python/.venv/bin/activate
python scripts/ppu-armv7-runtime-lab.py
```

The script performs:

1. Docker availability check.
2. ARMv7 QEMU/binfmt preflight.
3. Automatic ARM binfmt installation with the digest-pinned `tonistiigi/binfmt` image if the preflight fails.
4. Host-side PPU runtime build and validation using `software/python/.venv/bin/python`.
5. ARMv7 Python 3.12 container launch using a digest-pinned image.
6. A pure Python standard-library `ThreadingHTTPServer` control experiment with cumulative checkpoints at 1,000, 5,000, and 10,000 requests. This control does not import Plasma.
7. Plasma Server and Gateway startup.
8. Readiness polling instead of fixed startup sleeps.
9. Three isolated Plasma request-path tests, each defaulting to 1,000 requests:
   - `/api/health/live`
   - `/api/health/ready`
   - `/api/engineering/diagnostics/loopback` with `endpoint=ps`
10. Per-path latency, Gateway/Server RSS, thread count, and FD count measurement.
11. A 30-second post-load stability snapshot.
12. Host-owned JSON evidence output and deterministic process/container cleanup.

To shorten only the Plasma request-path portion of an exploratory run:

```bash
python scripts/ppu-armv7-runtime-lab.py --requests 100
```

The control checkpoints can also be reduced explicitly:

```bash
python scripts/ppu-armv7-runtime-lab.py \
  --requests 100 \
  --control-checkpoints 100,500,1000
```

## Interpretation

The Plasma paths separate likely sources of memory growth:

```text
health/live grows
  -> HTTP ThreadingHTTPServer / QEMU request-thread lifecycle is suspect

health/live stable, health/ready grows
  -> asyncio.run + PlasmaClient status/TCP lifecycle is suspect

live/ready stable, PS Loopback grows
  -> diagnostic payload / protocol exchange path is suspect
```

The pure-stdlib control adds a stronger negative control. If its request-normalized RSS growth is close to Gateway `/api/health/live`, that supports the hypothesis that the observed growth is caused primarily by the ARMv7 QEMU + `ThreadingHTTPServer` environment rather than Plasma-specific request logic. A mismatch keeps the Gateway implementation itself under investigation.

The report deliberately separates result semantics:

```text
functional_result = PASS
resource_result   = INVESTIGATE
overall_result    = INVESTIGATE
```

`functional_result=PASS` means the packaged runtime, health paths, and PS Loopback functioned correctly. It does not convert unresolved QEMU/native-memory questions into a resource PASS.

RSS observed under QEMU is not a Z2-native RAM measurement. Relative growth, control-vs-Gateway slopes, and path-to-path differences are useful diagnostic evidence; absolute Z2 resource acceptance must be repeated on real PYNQ-Z2 hardware.

## Integration-host reboot note

ARM binfmt registration can be lost across host reboot. The lab owns this preflight and attempts to reinstall the ARM handler automatically, so the operator should not need to manually repeat the prior `tonistiigi/binfmt --install arm` command.

If automatic registration fails, the run fails closed instead of reporting ARMv7 acceptance.
