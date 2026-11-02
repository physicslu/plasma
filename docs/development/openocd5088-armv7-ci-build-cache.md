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

This PR is independent of #1264. It must pass separate Gate 2 merge approval
before its workflow can speed subsequent #1264 PR pushes.
