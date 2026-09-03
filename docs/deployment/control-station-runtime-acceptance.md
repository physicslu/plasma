# Control Station Runtime Acceptance Evidence

> Status: **Current clean-runtime acceptance definition**. CI evidence is produced by `.github/workflows/control-station-runtime.yml` and is valid only for the commit that the workflow tests.

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
  -> packaged Manager startup with temporary operator-local registry state
  -> packaged Console/BFF startup in Managed Mode
  -> synthetic local Plasma Gateway contract endpoint
  -> Browser-style same-origin Registry BFF
  -> Add PPU as Pending
  -> Manager current trusted identity/topology observation
  -> Validate & Enable
  -> Remove PPU
  -> durable registry state verification
```

The synthetic PPU is a process-local Plasma Gateway API contract fixture, not hardware. It exposes the canonical PPU fleet health, identity and Site status surfaces required for Manager validation. The acceptance therefore proves that the **packaged** Console/BFF and **packaged** Manager can execute the complete Manager-owned PPU Registry lifecycle after clean extraction, including file-backed runtime state.

The final registry is intentionally empty after Remove, and the acceptance verifies the persisted `manager-registry.json` state rather than trusting only the HTTP response.

A passing workflow does **not** prove or authorize real PPU hardware, Z2 PS/PL execution, physical Site configuration, FPGA execution, IC programming, installer upgrade/rollback, network discovery, or production security approval. Those remain separate acceptance gates.
