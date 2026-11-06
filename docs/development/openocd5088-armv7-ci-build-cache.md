# OpenOCD 5088 ARMv7 candidate CI build cache (Gate 1)

Workflow: .github/workflows/swd-openocd5088-armv7-candidate.yml.
Required job identity remains armv7-source-locked-candidate. The cache is a
CI build optimization, not production trust, FPGA admission or HIL proof.

## Invalidation contract

The content-addressed key covers the isolated ARMv7 build recipe (upstream
commit, configure flags, image tag, apt dependencies, explicit toolchain epoch),
the native injector, every C/H file named in its COPIES tuple, and the cache
key/verification implementation. It excludes docs, the HIL deployment template,
and the independent admission script because none feeds the C compiler.
Site admission changes instead run the existing Python PS source-test job,
including unprivileged admit/revoke denial checks; they do not trigger the
ARMv7 OpenOCD candidate workflow. OpenOCD C/H, build/verification tooling
and the ARMv7 workflow itself still trigger source-locked candidate checks.

The arm32v7/ubuntu:22.04 image tag and apt packages are not fully immutable.
Maintainers MUST bump OPENOCD5088_TOOLCHAIN_EPOCH when the toolchain, Ubuntu
image, apt repository, QEMU or runner environment changes. Do not describe
a cache hit as hermetic reproduction. Restore keys are exact, with no loose
restore-keys. An absent cache triggers a build. A corrupted cache fails closed.

Only the executable, Tcl source tree, and input-bound SHA256 manifest are
cached. The admission script, logs, test results and evidence are never cached.

## Each eligible PR run

1. Run host-only positive and negative cache/key contract tests.
2. Calculate Build Key, restore; on miss rebuild ARMv7 and seal manifest.
3. Always validate binary/Tcl digest, ELF32 ARM, adapter discovery/selection,
   unowned/unadmitted init denial, and shared-library allowlist in ARMv7 QEMU.
4. Always package the current admission script and new logs/SHA256/evidence.
   Evidence plasma_source_sha uses github.event.pull_request.head.sha, not the
   synthetic PR merge SHA, while tested checkout remains GitHub's PR merge.
5. Publish the unchanged candidate tarball/sidecar and only then save cache
   on a miss. Preserve the required check and evidence schema.

## Trust and hardware boundaries

Cache integrity plus repeated smoke tests is not a signed build attestation
and does not defeat a malicious trusted cache producer. hardware_runtime_ready
stays false; Z2 HIL and Blue Pill DPIDR remain NOT_RUN. No SWPC, Z2, FPGA,
DUT, deployment, merge or production qualification is authorized.

## Concurrent PR push race

GitHub may start another PR run before the first run has finished saving its
cache. In that case two jobs can both miss the *same* exact key and perform
duplicate builds; the later cache-save may report an already-reserved key.
That does not establish a cache HIT. For acceptance, run a subsequent
documentation-only PR push **after** the first run has completed and saved the
cache, and check the logs show the exact key restored and compilation skipped.
Keep the integrity, QEMU negative checks, and per-HEAD evidence mandatory.

This PR is independent of #1264. It must pass separate Gate 2 merge approval
before its workflow can speed subsequent #1264 PR pushes.

## Native OpenOCD source-build routing
The existing Python source-test workflow has a separate `swd-openocd-native`
job. Native OpenOCD rebuilds for C/H, injector, native compilation-test changes,
or changes to the native job's own YAML block. A Python-test-only edit to
`python-tests.yml` skips that build. Missing/unreadable PR base or a missing
native job stanza fails closed by requiring the build. The native job allows
45 minutes because hosted Ubuntu APT downloads exhausted its previous 20-minute
cap before C compilation started; this does not relax validation.
