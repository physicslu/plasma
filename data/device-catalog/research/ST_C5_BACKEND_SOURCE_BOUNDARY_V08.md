# STM32C5 v0.8 — Backend Source / Production Admission Boundary

**2026-09-29 · Research only · ST Production remains 2,683 exact ICPNs / 23 source families.**

## Discovery after v0.7

The public official ST C5 eStore category has **172 observed same-card Active exact MPNs** from fully captured 18-page raw evidence (v0.7 pinned SHA). They are still candidate research identities, not Production-ready programming profiles.

The [ST customized OpenOCD fork](https://github.com/STMicroelectronics/OpenOCD/tree/c8d973bdad9a6fddb51459eda109b3b95d23b57a) provides a bounded **target script candidate**, but the raw script is not an immediately deployable Plasma production programming route.

| Pinned source | Git blob SHA / observation |
| --- | --- |
| `tcl/target/stm32c5x.cfg` | `03bce02b166b669ca0d7515656bca68ff4db8b84` |
| `src/flash/nor/stldr_driver.c` | `99d51e696cd5cfa64948e479102472fb126afafa` |
| `src/flash/nor/drivers.c` | `219dfa9a4a87a96d43b5e7496cbab47092f77b7a` |
| ST fork commit / branch | `c8d973bdad9a6fddb51459eda109b3b95d23b57a` / `openocd-cubeide-r7` |

The target script declares SWD/JTAG and `flash bank ... stldr 0x08000000 ...`, with a default RAM work area of `0x8000` and adapter speed 500 kHz. The **actual loader table is empty**:

```tcl
set dev_id_loader {
}
```

On target examination, when no matching loader is supplied it explicitly reports `No STLDR loader file found for device ID`. Its fallback die identifiers include 0x44E, 0x44F and 0x45A, but these values alone do not qualify a 172-MPN mapping or compatible loader algorithms. In addition, the `stldr` driver must actually be present in **the Plasma-chosen OpenOCD build**, not simply the upstream ST fork. GPL/source redistribution obligations must be separately reviewed when incorporating the fork.

An [OpenOCD upstream patch proposing STM32C5x support](https://review.openocd.org/c/openocd/+/9699) was announced on 2026-07-15; this study did not verify `tcl/target/stm32c5x.cfg` on the public OpenOCD main-branch path as of the research date. A submitted upstream patch is not sufficient as a pinned production dependency.

## Alternative vendor tool is not a production shortcut

ST announced C5 support in **STM32CubeProgrammer v2.22**, including internal flash programming. But the [official FAQ](https://www.st.com/content/st_com/en/stm32cubeprogrammer.html) explicitly says CubeProgrammer is **not for production programming under its software package license**. Treat its support as a technology reference; do not silently replace Plasma's backend with this tool for factory production.

## Required next admission gate

1. Obtain usable versioned `stldr`/loader inputs and mapping by confirmed C5 die ID and memory/flash configuration; review their licensing and raw SHA256 provenance.
2. Prove Plasma's selected OpenOCD build actually includes the pinned target script, matching flash driver and loader prerequisites. Validate selection for C531/532/542, C551/552/562 and C591/593/C5A3 without guessing identifiers from the retail MPN alone.
3. Qualify package, flash, RAM, temperature and security variant data against pinned manufacturer datasheets/reference manual; separate normal flash write/erase from option bytes, OTP, TrustZone and destructive operations.
4. Only after identity + lifecycle + metadata + deterministic route gates pass, prepare a **separate exact-ICPN Production publication PR** for explicit owner approval. No physical/HIL success is implied by a source script.

**Current gate:** `catalog_admission_ready=false`, `production_write_authorized=false`, `hardware_hil_qualified=false`.

Replay: `python data/device-catalog/research/validate_st_c5_backend_source_v08.py`.
