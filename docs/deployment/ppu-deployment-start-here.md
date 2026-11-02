# PPU Deployment — Start Here

Entry page for how a PYNQ-Z2 PPU is provisioned and updated today. It links the authoritative documents and adds no rules. When this page disagrees with a linked document or the code, the linked document/code wins.

**Admission ≠ installation ≠ activation.** Accepting an archive (admission) does not install it; installing/staging it does not make it active; activating software does not load the FPGA. Each step has its own evidence.

## The routes and their roles

| Route | Role today | Authoritative document |
| --- | --- | --- |
| **Factory Bootstrap** (`plasma-bootstrap.service`, `:18081` on the real Z2) | One-time local/SSH install of the factory/recovery service that later accepts uploads and runs deployment transactions. Independent of the Product Runtime. | [Bootstrap factory and HIL](ppu-bootstrap-factory-and-hil.md) |
| **Console Runtime deployment** | Normal path for installing or upgrading the PPU Runtime + OpenOCD: Browser → Console BFF → Plasma Manager → Bootstrap `:18081` → kit-local `plasmactl z2-ps` → Z2 installer → Runtime `:18080`. | [Bootstrap factory and HIL](ppu-bootstrap-factory-and-hil.md#console-first-install--upgrade-path) |
| **`plasmactl install z2-ps`** | The release-kit installer itself. Bootstrap invokes it kit-locally; running it by hand is the manual clean-install / recovery form. | [Z2 PS release kit](z2-ps-installer.md), [plasmactl profiles](plasmactl-deployment-profiles.md) |
| **Bundle v3 assets** | Delivery of Asset Sets (Python, native C, FPGA BIN/HWH + Manifest, Programming Profiles, firmware) through the same Bootstrap API and single Coordinator. Host-only staging; activation and FPGA loading are not implemented. | [Bundle v3 contract](../architecture/ppu-canonical-bundle-packages.md), [Generic Asset Set B3](ppu-bundle-v3-generic-assets-gate1.md), [Single Active Asset Set](ppu-single-active-asset-set-gate1.md), [FPGA Image Asset Handoff](ppu-fpga-asset-handoff-gate1.md) |
| **`ppu-deploy` engineering modules** | Separate SSH transaction for engineering modules (for example WordPort). Development use, not the product install path. | [ppu-deploy](../development/ppu-deploy-engineering-modules.md) |
| **Single deployment entry (design)** | The convergence decision: one product installation endpoint (`POST /v1/deployments`) and one Coordinator lock/journal. Bundle v3 is the realization of that direction. | [Single deployment entry](../architecture/ppu-unified-deployment-gate1.md) |

## Provisioning order for a PPU

1. **Factory Bootstrap.** Install or refresh the factory Bootstrap once from an accepted `main` build (`ppu-bootstrap-factory-bundle` CI artifact). See *Factory Bootstrap installation* and *Single-Z2 R&D refresh* in [Bootstrap factory and HIL](ppu-bootstrap-factory-and-hil.md).
2. **Device enrollment.** Verify the board/FPGA identity yourself, then provision the root-owned `/etc/plasma/ppu-package-target.json` (mode `0600`: `platform`, `board`, `fpga_part`) and the device pairing credential. See [Target platform identity](../architecture/ppu-target-platform-identity.md).
3. **Manager registry.** Add the PPU connection (Gateway endpoint `:18080`) to the Manager registry; Manager derives the Bootstrap endpoint on `:18081`. A registry entry is not programming registration.
4. **Runtime deployment.** Install/upgrade the PPU Runtime + OpenOCD from the Console (EMode → PPU Sites → Runtime Deployment). Rollback and reboot persistence are evidenced on the physical Z2 per the Bootstrap document.
5. **Assets (Bundle v3).** Deliver Asset Sets: Bundle stage B1 upload/commit → B2 admission → B3 install/verify into staging (see [glossary](../glossary.md#b1b2b3)). B4 activation is not implemented.
6. **FPGA image.** Today FPGA images are loaded only through the existing protected Root Entry procedures with the [six necessary checks](z2-minimal-six-check-admission.md). The decided target is programming-flow loading by the PS FPGA Hardware Manager ([ADR-0004](../adr/0004-fpga-image-lifecycle-and-job-driven-loading.md)), not yet implemented.
7. **Engineering modules (optional, development).** Use `ppu-deploy` over SSH when an engineering module is needed.

## Ports

Real `z2-ps`: `:18080` Plasma Product Runtime Gateway, `:18081` independent Bootstrap/recovery service. The former SWPC host `127.0.0.1:18081` diagnostics ingress is retired. Full matrix: [Port profile matrix](port-profile-matrix.md).

## Not qualified

Bootstrap HTTP is qualified only on a controlled private commissioning link; transport confidentiality and publisher authenticity are not qualified (SHA-256 proves integrity only). FPGA/PL behaviour, Site electrical behaviour, target power and real IC programming are not qualified by any deployment step.
