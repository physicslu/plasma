# Control Station Runtime Acceptance Evidence

> Status: **PR #223 acceptance definition**. CI evidence is produced by `.github/workflows/control-station-runtime.yml` and is valid only for the commit that the workflow tests.

The acceptance runner is:

```text
scripts/control-station-runtime-acceptance.py
```

It performs one end-to-end application-runtime packaging cycle on the current Control Station host OS:

```text
Vinext standalone build
  -> Control Station runtime assembly
  -> Manager zipapp assembly
  -> role/platform release artifact
  -> detached archive SHA-256 verification
  -> internal SHA256SUMS verification
  -> clean extraction
  -> packaged Manager startup
  -> packaged Console/BFF startup
  -> same-origin BFF request
  -> Manager relay
  -> expected unreachable test PPU response
```

The unused PPU endpoint is deliberate. The expected final response is Manager's structured `504 ppu_transport_error`, relayed through the Console/BFF. That result proves the packaged Console can reach the packaged Manager and that the BFF route is executing after clean extraction without claiming any real PPU or hardware acceptance.

A passing workflow does not authorize or prove service installation, service-manager registration, persistent configuration migration, upgrade/rollback, Z2 deployment, FPGA execution, or IC programming.
