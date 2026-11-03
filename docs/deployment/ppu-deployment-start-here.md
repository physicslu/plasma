# PPU Deployment — Start Here

Entry page for how a PYNQ-Z2 PPU is provisioned and updated today. It links the authoritative documents and adds no rules. When this page disagrees with a linked document or the code, the linked document/code wins.

**Operator workflow: [Install Bundle → Run Job → Get Result](../architecture/ppu-install-run-result.md).** Inside Install, B1 Receive, B2 Admission and B3 Install/Verify remain distinct proofs. B3 with `fpga_load:false` stages only; explicit authorized `fpga_load:true` may load FPGA and atomically publish the verified Active Set after Root Identity PASS. Neither install nor Active means a Programming Job ran. There is **no separate B4 operator stage**.

## Two deployment routes

There are exactly two PPU deployment routes. Everything else listed below is a prerequisite, an internal step, a payload format or a design record of one of them — not a separate route.

| Route | Purpose | Entry | Transaction | Authoritative document |
| --- | --- | --- | --- | --- |
| **A. Product deployment** | Install / upgrade / roll back the PPU Runtime + OpenOCD and deliver Bundle v3 Asset Sets. | Console (EMode → PPU Sites → Runtime Deployment) → Console BFF → Plasma Manager → Bootstrap on `:18081`: upload (`POST /v1/uploads`, `…/chunks`, `…/commit`), then `POST /v1/deployments` | One Bootstrap Deployment Coordinator: one `deployment.lock`, one `deployment.json` journal | [Bootstrap factory and HIL](ppu-bootstrap-factory-and-hil.md#console-first-install--upgrade-path) |
| **B. Engineering deployment** | Development-only installation of engineering modules (for example WordPort / OpenOCD Python integration, SWPC A/B Runner). Not a product install path and carries no product qualification. | SWPC `scripts/ppu-deploy` over SSH | Its own SSH transaction (SHA pinning, mutual exclusion, verify, rollback) | [ppu-deploy](../development/ppu-deploy-engineering-modules.md) |

### What sits inside Route A

| Item | Role within Route A | Authoritative document |
| --- | --- | --- |
| **Factory Bootstrap** (`plasma-bootstrap.service`) | **Step 0 prerequisite**, not a route: one-time local/SSH installation of the factory/recovery service that later receives every Route A deployment. Independent of the Product Runtime. | [Bootstrap factory and HIL](ppu-bootstrap-factory-and-hil.md#factory-bootstrap-installation) |
| **`plasmactl install z2-ps`** | **Internal executor**: Bootstrap verifies the release kit and invokes the kit-local `plasmactl z2-ps`. Running it by hand is the manual clean-install / recovery form of the *same* transaction — it routes through the same `ppu-bootstrap-deployment.py` Coordinator and journal. | [Z2 PS release kit](z2-ps-installer.md), [Shared CLI / Console transaction model](ppu-bootstrap-factory-and-hil.md#shared-cli--console-transaction-model), [plasmactl profiles](plasmactl-deployment-profiles.md) |
| **Bundle v3 assets (B1–B3)** | **Payload format**, not a route: Asset Sets (Python, native C, FPGA BIN/HWH + Manifest, Programming Profiles, firmware) go through the same Bootstrap API and Coordinator as the Runtime kit: **B1** upload via `POST /v1/uploads` + `/v1/uploads/<id>/chunks` + `/v1/uploads/<id>/commit`; **B2** Admission via `POST /v1/deployments`; **B3** Install/Verify via `POST /v1/deployments` (`kind: bundle`, explicit `fpga_load: false|true`); `false` stages only, while authorized `true` may load FPGA and publish the verified Active Set after Identity PASS. Actual Z2 qualification is independent. | [Bundle v3 contract](../architecture/ppu-canonical-bundle-packages.md), [Generic Asset Set B3](ppu-bundle-v3-generic-assets-gate1.md), [Single Active Asset Set](ppu-single-active-asset-set-gate1.md), [FPGA Image Asset Handoff](ppu-fpga-asset-handoff-gate1.md) |
| **Single deployment entry** | **Design record** of Route A: the decision for one installation endpoint and one Coordinator lock/journal. Reference only; it is realized by Route A. | [Single deployment entry](../architecture/ppu-unified-deployment-gate1.md) |

The Runtime release kit (`plasma-z2-ps-kit-*.tar.gz`) and Bundle v3 are currently two payload formats accepted by the same Route A Bootstrap API: both are uploaded via `/v1/uploads` and then submitted to `POST /v1/deployments`, which dispatches by request body (`scripts/ppu-bootstrap-service.py` `start_deployment`). Unifying them into one format is a separate decision and is not part of this page.

## Provisioning order for a PPU

1. **Factory Bootstrap (Route A step 0).** Install or refresh the factory Bootstrap once from an accepted `main` build (`ppu-bootstrap-factory-bundle` CI artifact). See *Factory Bootstrap installation* and *Single-Z2 R&D refresh* in [Bootstrap factory and HIL](ppu-bootstrap-factory-and-hil.md).
2. **Device enrollment.** Verify the board/FPGA identity yourself, then provision the root-owned `/etc/plasma/ppu-package-target.json` (mode `0600`: `platform`, `board`, `fpga_part`) and the device pairing credential. See [Target platform identity](../architecture/ppu-target-platform-identity.md).
3. **Manager registry.** Add the PPU connection (Gateway endpoint `:18080`) to the Manager registry; Manager derives the Bootstrap endpoint on `:18081`. A registry entry is not programming registration.
4. **Runtime deployment (Route A).** Install/upgrade the PPU Runtime + OpenOCD from the Console (EMode → PPU Sites → Runtime Deployment). Rollback and reboot persistence are evidenced on the physical Z2 per the Bootstrap document.
5. **Assets (Route A, Bundle v3).** Install Bundle: B1 upload/commit (`/v1/uploads`) → B2 admission → B3 install/verify (`POST /v1/deployments`, `fpga_load` explicitly `false` or `true`). `false` stages only; successful authorized `true` can publish Active after verified FPGA Identity. There is no separate B4 operator step (see [glossary](../glossary.md#b1b2b3)).
6. **FPGA image.** An explicitly authorized B3 `fpga_load:true` routes through protected Root loading and [hardware admission checks](z2-minimal-six-check-admission.md). Programming-flow FPGA selection/loading under [ADR-0004](../adr/0004-fpga-image-lifecycle-and-job-driven-loading.md) remains a separate unqualified integration. No implicit load from upload or install-only.
7. **Engineering modules (Route B, optional, development).** Use `ppu-deploy` over SSH when an engineering module is needed. `ppu-deploy api-status` only reads Route A Bootstrap status; it does not install through Route A.

## Ports

Real `z2-ps`: `:18080` Plasma Product Runtime Gateway, `:18081` independent Bootstrap/recovery service. The former SWPC host `127.0.0.1:18081` diagnostics ingress is retired. Full matrix: [Port profile matrix](port-profile-matrix.md).

## Not qualified

Bootstrap HTTP is qualified only on a controlled private commissioning link; transport confidentiality and publisher authenticity are not qualified (SHA-256 proves integrity only). FPGA/PL behaviour, Site electrical behaviour, target power and real IC programming are not qualified by any deployment route.
