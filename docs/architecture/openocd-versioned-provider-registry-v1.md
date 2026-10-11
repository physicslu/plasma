# OpenOCD Versioned Provider Registry v1

**Research-only source metadata foundation. No PPU/Z2/FPGA/SWD, real IC, Programming Profile, Production Mapping, runtime deployment or vendor binary distribution.**

## Key engineering rule

A source Commit does not uniquely identify a compiled binary, and the same reported OpenOCD runtime ID can refer to different artifacts. Software test results are scoped to one particular source commit, architecture, artifact SHA256 and payload SHA256. This is never proof that the binary is actually installed or can program a target.

The read-only versioned provider registry produces a **list** of possible software engines for each exact admitted Production ICPN. It can model multiple providers per device but current evidence only establishes one each; it must never invent a competing provider. Current output is:

| Cohort | Provider | Mapping state | Exact parts |
| --- | --- | --- | ---: |
| Existing Catalog upstream route | openocd-upstream | mapped (routing only) | 4,164 |
| STM32H5 | openocd-st-h5-research | candidate | 190 |
| STM32C5 | openocd-st-c5-stldr-research | candidate | 172 |
| N6/WB0/WL3 remaining | none established | no_mapping | 103 |

Each record keeps hardware_runtime_ready=false, executable=false, installed_binary_sha256=null, installed_runtime_id=null, production_write_authorized=false, and no qualified hardware operations. The registry is not wired to Job or Batch execution.

## H5 software build provenance

The evidence ledger is data/device-catalog/research/st-h5-offline-runtime-evidence-v1.json and is Git-blob locked to source commit c8d973bdad9a6fddb51459eda109b3b95d23b57a.

| Build | CI run | Reported runtime ID | Artifact SHA-256 | Scope |
| --- | --- | --- | --- | --- |
| x86_64 host | 38020833350 | 0.12.0-c8d973bdad9a | 1758f03aef0a9ce6bbd212343622b174a85f0bda446bb2e26763113f460a64db | Build and dummy-JTAG Tcl parse |
| ARMv7 QEMU | 38034789548 | 0.12.0-c8d973bdad9a | f3a60db251a53bd18bf2a5acb80625abfc47c2eb298bb8a3a17112827cb502cd | ARMv7 emulated build and dummy-JTAG Tcl parse |

The source builds used the same reported runtime ID, but DIFFERENT archive and payload SHA256 values. The software-only identity comparison requires both full digests and the architecture to match; a runtime ID alone never transfers qualification. The measured installed executable SHA256 is unknown in BOTH cases.

C5 does **not** inherit H5 software build credit. Its STLDR loader-table, Tcl array defects, loader RAM/work-area compatibility, license and installation are not qualified. Its 139 exact / 33 base-only DFP matches are research-only.

## Progression, not automatic authorization

A future runtime provider must first prove its exact installed binary SHA256, version, ABI/dependencies, target driver/configuration and Site ownership. This source-only registry does not select a production route, execute OpenOCD or change existing Catalog backend mapping. Physical PPU/SWD/electrical and erase/program/verify evidence remain independent later gates.

The downstream IC Selector may present provider/source/version/build-scoped research information but must label installed runtime as unverified until a trusted actual PS runtime inventory exists. A source proof is never a programming guarantee.

## Run offline tests

    PYTHONPATH=software/python python -m unittest discover -s software/python/tests -p test_openocd_versioned_provider_registry_v1.py -v

Dedicated GitHub CI checks all 4,629 ICPNs and the three provider cohorts, source locks, duplicate provider rejection, runtime-artifact mismatch rejection and all hardware/production gates closed. No ST binary is distributed by the PR.
