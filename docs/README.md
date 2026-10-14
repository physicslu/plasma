# Plasma Documentation Index

本頁是 `docs/` 的 canonical 文件入口。執行中的程式、設定 schema、REST／wire contract 與自動測試優先於描述性文字；若兩者不一致，先停止操作、以實作與測試確認事實，再在同一個變更中修正文檔。

## 文件狀態

| 標記 | 意義 |
|---|---|
| **Current** | 描述目前已實作或目前必須遵守的契約。 |
| **Reference** | 設計背景、驗證邊界或維護方式；不得取代 Current contract。 |
| **Plan** | 尚未全部實作的核准方向；不能宣稱為現有能力。 |
| **Historical** | 僅供遷移背景；不是相容性或執行契約。 |

## Architecture Decision Records

- **Current** — [ADR Index](adr/README.md)：記錄 Plasma 已核准的長期架構決策與狀態。
- **Current** — [ADR-0001: PYNQ System Python 與 Plasma PPU Runtime 分離](adr/0001-pynq-system-python-plasma-runtime-separation.md)：PYNQ owns System Python；Plasma owns an isolated, Plasma-qualified Python runtime。Bundled Python 是偏好的產品方向，但必須先完成 ARMv7/PYNQ 實機 qualification。
- **Plan / Accepted Policy** — [ADR-0002: OpenOCD 軟體支援、Catalog 顯示與研究優先順序](adr/0002-openocd-software-qualified-catalog-visibility.md)（實作順序：Phase 1 IC Information → Phase 2 Programming → Phase 3 PLASMA Compatibility；預設 Product Catalog 的 SUPPORTED-only 政策維持，尚未完成遷移。）：產品 Catalog 僅顯示指定版本 OpenOCD 已確認具燒錄能力的 ICPN；Socket/PPU/Site HIL 獨立；研究工作優先針對 OpenOCD 支援目標，其餘原廠候選只保留來源。API/UI migration 追蹤 [Issue #849](https://github.com/physicslu/plasma/issues/849)，研究作業優先順序追蹤 [Issue #851](https://github.com/physicslu/plasma/issues/851)。

## Operator

- **Current** — [Plasma Console Operator Guide](operator/plasma-console-guide.md)：PMode／EMode、Batch Summary、操作與異常復原。

## Architecture and contracts

- **Current** — [Facility / PPU / Site Domain Model](architecture/ppu-facility-sites.md)
- **Current** — [PPU Execution Ownership](architecture/ppu-execution-ownership.md)
- **Current** — [Domain Naming and Identity Policy](architecture/domain-naming-migration.md)
- **Current** — [Web Product Modes](architecture/web-product-modes.md)
- **Current** — [Web REST API Contract](architecture/web-rest-api-contract.md)
- **Current** — [Configuration Architecture](architecture/configuration-architecture.md)
- **Current** — [PPU Site Configuration](architecture/ppu-site-configuration.md)：定義 Phase 1 `enabled`／`interface`／`target` desired state、PPU authoritative validation、canonical YAML atomic persistence、active-execution write gate、desired／actual reconciliation 與 Manager/BFF allowlist 邊界。
- **Current** — [CI/CD Validation Architecture](architecture/ci-cd-validation-architecture.md)：定義 risk-based validation topology、Fast／Browser／Runtime／Release gate、Device Catalog Historical／Current 邊界，以及 production Device Catalog → IC Support 的跨 domain dependency。
- **Reference** — [Device Catalog CI Coverage Map](architecture/device-catalog-ci-coverage-map.md)：記錄 Device Catalog workflow authority、trigger、validator、overlap 與 lifecycle；coverage parity 證明前不授權 workflow retirement。
- **Current** — [Batch Domain Model](architecture/batch-domain-model.md)
- **Current** — [Server-side Batch Runtime](architecture/server-side-batch-runtime.md)
- **Current** — [Batch Persistence and Gateway Restart Recovery](architecture/batch-persistence-recovery.md)
- **Current** — [Plasma Gateway Communication and Recovery](architecture/gateway-communication-recovery.md)
- **Current** — [PPU Network Configuration](architecture/ppu-network-configuration.md)：定義 Phase 1 `eth0` desired-state API、Default Gateway／DNS 等 Linux network 參數、驗證、持久化與 Phase 2 activation／reconnect／rollback 邊界；並區分 Plasma Gateway service 與 Linux Default Gateway。
- **Reference** — [Virtual PPU Network Lab](architecture/virtual-ppu-network-lab.md)：以 Linux host 上的 production Plasma Manager 驅動兩個 isolated packaged ARMv7 Virtual PPU，驗證 real managed-IPv4 migration、same-`ppu_id` reconnect、activation commit、Manager registry CAS／journal 與 privilege separation；不代表 PYNQ-Z2 native network backend acceptance。
- **Reference** — [Static IPv4 Fault Injection](architecture/static-ipv4-fault-injection.md)：在 fresh isolated Virtual PPU topology 注入 duplicate candidate、wrong `ppu_id`、reconnect timeout、helper failure 與 Manager pre/post-commit crash，驗證 rollback、`recovery_required`、registry fail-closed 與 restart reconciliation；不代表 PYNQ-Z2 native network backend acceptance。
- **Current** — [Persistent Integration Host Qualification](architecture/persistent-integration-host-qualification.md)：定義 L4 main-only post-merge qualification、self-hosted/rootful-Docker threat model、fail-closed preflight、runner enrollment boundary，以及為何目前不能把長期 runner 當成 arbitrary-PR execution worker。
- **Current** — [Production Real-Path Loopback Diagnostics](architecture/diagnostics-real-path-loopback.md)
- **Current** — [Control Plane Routing Architecture](architecture/control-plane-routing-architecture.md)：定義 Control Console、BFF、Plasma Manager、Plasma Gateway、Plasma Server 的責任邊界，以及 Managed Mode 的 Programming／Loopback 共用 production route。
- **Current** — [Manager Runtime PPU Registry](architecture/manager-runtime-ppu-registry.md)：定義 Manager-owned runtime inventory、Plasma Gateway Endpoint、`pending`／`commissioned`／`disabled` lifecycle、Add／Validate & Enable／Disable／Remove 與 durable state 邊界。
- **Reference** — [Remote Write Security Boundary](architecture/remote-write-security-boundary.md)
- **Current** — [PMode Factory Console v2](architecture/pmode-factory-console-v2.md)
- **Current** — [Engineering Programming Workspace](architecture/engineering-programming-workspace.md)
- **Current** — [Engineering Programming Observability](architecture/engineering-programming-observability.md)
- **Current** — [Engineering Settings UI Design System](architecture/engineering-settings-ui-design-system.md)
- **Plan / Accepted Policy** — [IC Information Phase 1 Evidence Contract](architecture/ic-information-phase1.md)：ADR-0002 三階段實作中，現階段只建構 IC Information 精確料號、逐欄原廠證據與完整度統計；Programming 與 PLASMA Compatibility 後續執行。
- **Current** — [IC Selector Architecture](architecture/ic-selector.md)
- **Implementation / Proposal** — [Installed OpenOCD Evidence Root v1](architecture/runtime-evidence-root-implementation-v1.md)：修正 source-only H5/C5/OpenOCD Provider 顯示資訊在非 editable Python 安裝下的路徑解析，區分 Render full 與 Slim PPU 必備／可省略來源；不授權燒錄。
- **Implementation / Proposal** — [KL25 Installed Backend Lock Root v1](architecture/kl25-runtime-backend-lock-root-v1.md)：以既有 IC Support Root 契約載入固定的 KL25 implementation lock，non-editable 安裝與 fail-closed 測試通過才能合併；不新增 KL25 Operation Admission。
- **Current** — [Selected IC Profile v1](architecture/selected-ic-profile-v1.md)：將 exact ICPN 的 Device operating characteristics、Programming requirements、Backend evidence 與 PLASMA compatibility 分層組合；STM32F103C8T6 為第一個 manufacturer-first pilot。
- **Current** — [Manufacturer Enrichment Coverage Framework v1](architecture/manufacturer-enrichment-coverage-v1.md)：定義 M0–M5 manufacturer enrichment coverage、逐 ICPN missing-dimension 投影、explicit exact-ICPN scope composition 與 fail-closed inheritance 規則；不授權 runtime 或 hardware readiness。
- **Current** — [Manufacturer Device Basic Profile v1](architecture/stm32f1-device-basic-profile-v1.md)：目前以 explicit family profiles 覆蓋 STM32F1／STM32F2／STM32C0／STM32G0／STM32G4／STM32U0／STM32U3／STM32L5／STM32H7RS／STM32WBA5X／STM32N6，共 1,622 個 Production exact ICPN；剩餘 3,007 個 ST exact ICPN 已完成 evidence review，但因 Product Selector/eStore 直接證據不足、衝突或無法無損映射至固定 M1 欄位而 fail-closed。IC Information 固定為 10 欄，所有 Basic Profile 與 Programming Profile、Memory Map、HIL 分離。
- **Current** — [STM32H5 Host-only Readback Guard v1](architecture/st-h5-host-readback-guard-v1.md)：190 顆 H5 合成讀值的安全邊界測試；失敗／fallback／不匹配一律阻擋，不代表實機燒錄資格.
- **Current** — [STM32C5 Host-only STLDR Source Guard v1](architecture/st-c5-host-loader-table-v1.md)：139 exact DFP／33 base-only 的離線 Loader 來源與 Tcl array 測試，不能執行燒錄.
- **Current** — [Versioned OpenOCD Provider Registry v1](architecture/openocd-versioned-provider-registry-v1.md)：將 Upstream／ST 來源與 x86／ARMv7 Artifact SHA-256 分離，沒有實機安裝證據不宣稱可燒錄。
- **Current** — [ICPN Backend Candidate Registry v1](architecture/icpn-backend-candidate-registry-v1.md)：H5／C5 合計 362 顆來源鎖定的唯讀候選資訊，與 Production Backend Mapping、燒錄資格分離。
- **Current** — [Device Support and Validation](architecture/device-support-validation.md)
- **Plan** — [Device Support / Hardware Execution / OpenOCD Architecture](architecture/device-support-hardware-openocd.md)：PoC 維持 PYNQ + Python；Production 將 Programmer Backend、stable Plasma HW API、UIO/MMIO/DMA/IRQ 與 PL protocol engine 分層，並避免 OpenOCD per-bit bit-banging。
- **Plan** — [IC Support Reusable Profile Architecture](architecture/ic-support-profile-architecture.md)
- **Current** — [IC Support Coverage Normalization](architecture/ic-support-coverage-normalization.md)：以 derived inventory 將 production exact ICPN 正規化為 Base Device、Programming Profile 與 backend readiness，避免把商業料號數量誤當成燒錄演算法數量。
- **Current** — [IC Support Runtime Resolver Foundation](architecture/ic-support-runtime-resolver.md)：定義 exact ICPN → reusable IC Support profiles 的 runtime-consumable resolver，並維持 Profile resolved 與 backend/runtime implemented 的 fail-closed 邊界。
- **Current** — [Profile-driven OpenOCD Plan Compiler](architecture/ic-support-openocd-plan-compiler.md)：將 evidence-backed Programming Profile 與 Memory Geometry 編譯成 deterministic OpenOCD dry-run plan；C8／CB geometry 分流，但硬體 execution 維持 fail-closed。
- **Current** — [OpenOCD Compiled-Plan Executor](architecture/ic-support-openocd-plan-executor.md)：驗證 PS-side canonical OpenOCD plan → isolated software subprocess boundary；production hardware gate 仍關閉，PL/native programming 不在本階段範圍。
- **Current** — [Vendor-neutral IC admission governance](architecture/vendor-neutral-ic-admission.md)：以 content-addressed artifact、review、disposition、canonical envelope、operation admission 與 backend binding 建立通用治理邊界；尚未接入 production runtime。
- **Current** — [IC Support Architecture Freeze v1](architecture/ic-support-architecture-freeze-v1.md)：凍結 PR-A／PR-B／PR-C／PR-D 後的 vendor-neutral trust、operation admission、Compiler Registry 與 software/hardware readiness 邊界；不宣稱 HIL 或實體燒錄 readiness。
- **Current** — [Mock Runtime v1.1](architecture/mock-runtime-v1.1.md)
- **Current** — [Mock Synthetic Image Contract](architecture/mock-synthetic-image.md)
- **Current** — [Optional Manager Control Plane](architecture/manager-optional-control-plane.md)
- **Current** — [Manager Read-only Fleet Aggregation](architecture/manager-readonly-fleet-aggregation.md)
- **Historical** — [Historical Multi-Programmer / Multi-Site Naming](architecture/multi-programmer-sites.md)

## Development and validation

- **Current** — [Documentation Maintenance](development/documentation-maintenance.md)
- **Current** — [AI-assisted Git Workflow](development/ai-git-development-workflow.md)
- **Current** — [PLASMA GitHub Actions Control Bridge](development/plasma-actions-control-bridge.md)：定義 Issue #814、actor／workflow allowlist、`dispatch`／`cancel`／`rerun` 命令與最小權限安全邊界。
- **Current** — [Codex Cloud Environment](development/codex-cloud-environment.md)
- **Current** — [Local AI Development Guide](development/local-ai-development-guide.md)
- **Current** — [Persistent Integration Runner Enrollment](development/persistent-integration-runner-enrollment.md)：定義 L4 host readiness、GitHub runner enrollment/restriction、首次 qualification、staleness、upgrade、revoke 與 recovery lifecycle；不把 registration token 或 host provisioning 寫入 repository automation。
- **Reference** — [IC Support Local-AI Benchmark Handover](development/ic-support-ai-benchmark-handover.md)：整理 STM32F103C Qwen 實驗的能力邊界、已知 failure classes、multi-model role separation，以及下一輪獨立 Gemma 比較的 blind-control 條件。
- **Current** — [IC Support Semantic Validator v0](development/ic-support-semantic-validator-v0.md)：把 Qwen／Gemma 已觀察到的機械性 failure class 轉成 deterministic semantic invariants、negative regressions 與 CI gate；未具 execution IR 的規則明確維持未實作狀態。
- **Reference** — [STM32F103 Manufacturer-Derived Programmer Codegen Pilot](development/stm32f103-programmer-codegen-pilot.md)：從 manufacturer-derived baseline／Programming Profile／Execution IR 產生 software-only reference programmer，再與 pinned OpenOCD semantic review 做 post-generation differential；不代表 HIL 或實體燒錄 readiness。
- **Reference** — [STM32F103 Real OpenOCD Binary Software Acceptance](development/stm32f103-openocd-real-binary-acceptance.md)：以真正 source-pinned OpenOCD binary、official dummy adapter 與 `target/stm32f1x.cfg` 驗證 C8 64-KiB Flash-driver registration；`noinit` 保證不進入 adapter／target hardware initialization。
- **Current** — [Multi-machine Development Guide](development/multi-machine-development-guide.md)
- **Current** — [VS Code Remote Workspace Standard](development/vscode-remote-workspace.md)
- **Current** — [Integration Host Deployment Guide](development/swpc-deployment.md)
- **Current** — [Secure Gateway Deployment](development/secure-gateway-deployment.md)
- **Current** — [Fleet Demo Deployment](development/fleet-demo.md)
- **Current** — [Mock Continuous Delivery](development/mock-cd.md)
- **Current** — [Mock Runtime Operator Guide](development/mock-runtime-operator-guide.md)
- **Current** — [Operator Acceptance Test Matrix](development/operator-acceptance-test-matrix.md)
- **Current** — [Programming Image Observability Test Plan](development/programming-image-observability-test-plan.md)
- **Current** — [Runtime Acceptance](testing/runtime-acceptance.md)
- **Current** — [FPGA Development Guide](development/fpga-development-guide.md)
- **Current** — [FPGA Verification Guide](development/fpga-verification-guide.md)
- **Reference** — [Mock Runtime Foundation Notes](development/mock-runtime-foundation-notes.md)
- **Plan** — [Device Support Catalog Implementation Plan](development/device-support-implementation-plan.md)
- **Plan** — [OpenOCD Part-number Expansion Plan](development/openocd-part-number-expansion-plan.md)
- **Plan** — [Development Debt Register](development/todo.md)

## Deployment

- **Current** — [Deployment Index](deployment/README.md)
- **Current** — [`plasmactl` Deployment Profiles](deployment/plasmactl-deployment-profiles.md)：定義統一 operator CLI、`integration`／`local-control-station`／`swpc-z2like` profile ownership、activation rollback 與 qualification boundary。
- **Current** — [Deployment Port / Profile Matrix](deployment/port-profile-matrix.md)：定義 production、SWPC engineering 與 `z2like-demo` scenario 的 profile-specific port ownership、exposure 與安全邊界。
- **Current** — [Local Control Station Reference Deployment](deployment/local-control-station.md)：定義 Linux user-systemd 的 Console/BFF + Manager 本機參考部署、可設定 PPU Endpoint、loopback-only ingress、immutable release 與 rollback；macOS／Windows 保留相同產品契約但使用平台原生 packaging。
- **Current** — [Product Deployment Foundation](deployment/product-deployment-foundation.md)：定義跨平台 Control Station（macOS／Linux／Windows）、Z2 PPU、SWPC integration host 的產品部署責任邊界，以及 immutable release 與跨平台 read-only readiness audit。
- **Current** — [Product Release Format v1](deployment/product-release-format.md)：定義 product version、release manifest、角色／平台 artifact matrix、SHA-256 integrity、safe verification 與 clean-extraction acceptance。
- **Current** — [Control Station Runtime Packaging](deployment/control-station-runtime-packaging.md)：定義 source-tree-independent Vinext standalone Console/BFF、Manager Python zipapp、runtime manifest 與 Control Station release payload。
- **Current** — [PPU Runtime Packaging](deployment/ppu-runtime-packaging.md)：定義 Z2 PS Phase-1 source-tree-independent PPU Python zipapp、`linux-armv7l` immutable release、PS-only fail-closed configuration、systemd topology與 Managed PS Loopback 驗收邊界。
- **Current** — [PYNQ-Z2 PS Installer and Managed Loopback Acceptance](deployment/z2-ps-installer.md)：定義 verified PPU release → immutable side-by-side install、PYNQ/System-Python ownership isolation、explicit Plasma Python >= 3.11 binding、systemd activation/rollback、local readiness 與 real Managed PS Loopback evidence boundary。
- **Reference** — [PPU Bootstrap Factory Provisioning and Z2 HIL](deployment/ppu-bootstrap-factory-and-hil.md)：定義獨立 Bootstrap／recovery service、Console-managed Z2 Runtime deployment、durable rollback/recovery contract，以及 real PYNQ-Z2 HIL qualification 邊界。
- **Current** — [SWPC z2like-demo QEMU ARMv7 Backend](deployment/z2like-demo-qemu.md)：固定 SWPC 為唯一 simulation environment、QEMU ARMv7 simulated Z2 為 `z2like-demo` 唯一 PPU backend，並定義 Bootstrap/Control Station 私有路由與非實機 qualification 邊界。
- **Reference** — [Render Control Station -> SWPC Z2-like PPU Managed PS Loopback](deployment/render-swpc-managed-ps-loopback.md)：定義 Render-hosted Control Station／Manager → restricted HTTPS ingress → SWPC PS-only PPU surrogate 的 public managed qualification，以及 x86_64／ARMv7、PYNQ、PL／hardware 非等價證據邊界。
- **Current** — [SWPC Z2-like Secure Managed Programming Ingress](deployment/swpc-z2like-managed-programming-ingress.md)：在保留 diagnostics ingress 與 loopback-only full Gateway 的前提下，新增 Cloudflare Access service-token 保護、route/method allowlist 的 managed mock Programming ingress；不構成 Z2／PL／real-IC qualification。
- **Current** — [SWPC Z2-like Configured Mock Programming](deployment/swpc-z2like-configured-mock-programming.md)：將 Engineering Programming 綁定到 canonical `lab/swpc-z2like-01/SITE1..SITE8` 與既有 Plasma Server，明確拒絕 non-mock Site，且不建立舊 32-PPU demo topology；僅屬 software/mock qualification。
- **Reference** — [PPU ARMv7 Runtime Lab](deployment/ppu-armv7-runtime-lab.md)：定義 integration-host QEMU ARMv7 一鍵 runtime/resource 診斷、live／ready／PS Loopback 路徑隔離與非 Z2-HIL 證據邊界。
- **Reference** — [2026-09-02 SWPC/QEMU ARMv7 Runtime Evidence](evidence/armv7-runtime/2026-09-02-swpc-qemu/README.md)：歸檔實測 JSON 與工程判讀；僅屬 SWPC/QEMU ARMv7 userspace evidence，不代表 PYNQ-Z2 native memory acceptance。
- **Reference** — [Control Station Runtime Acceptance Evidence](deployment/control-station-runtime-acceptance.md)：定義 macOS／Linux／Windows clean-runtime CI 的證據範圍與不可延伸宣稱的邊界。
- **Current** — [macOS Control Station Installer Pilot](deployment/macos-control-station-installer-pilot.md)：定義 unsigned `.pkg`、per-user `launchd` LaunchAgents、absolute Node/Python runtime binding，以及 install/start/restart/stop-start/basic-uninstall acceptance；不代表 signing/notarization readiness。
- **Current** — [Windows Control Station Installer Pilot](deployment/windows-control-station-installer-pilot.md)：定義 unsigned MSI、WinSW-backed Windows SCM services、`Program Files`／`ProgramData` 邊界，以及 install/start/restart/stop-start/basic-uninstall acceptance；不代表 signing 或真正 Windows operator-host readiness。
- **Historical** — [SWPC Public Preview / Mock Environment](deployment/swpc-public-preview.md)：記錄 `plasma.open4th.com` 過去作為 SWPC Preview／Mock ingress 的退役角色；目前 Mock Demo 已移至 `plasma-demo.open4th.com`，SWPC hostname 保留給 Local Control Station 驗收後切換。
- **Current** — [Web Runtime Hygiene](deployment/web-runtime-hygiene.md)
- **Current** — [Manager BFF Runtime Wiring](deployment/manager-bff-runtime-wiring.md)
- **Current** — [Render Free Public Mock Demo](deployment/render-free-public-demo.md)
- **Current** — [Render Public Smoke Acceptance](deployment/render-public-smoke.md)
- **Current** — [Render Public Browser Acceptance](deployment/render-public-browser.md)

## Component contracts outside `docs/`

- [Python control plane](../software/python/README.md)
- [Protocol v3.3](../software/python/docs/protocol.md)
- [Python architecture](../software/python/docs/architecture.md)
- [Error model](../software/python/docs/errors.md)
- [Python test guide](../software/python/docs/test-guide.md)
- [Web Console](../software/web/README.md)
- [FPGA / PL](../pl/README.md)

## Validation

Run the documentation integrity guard before review:

```bash
python scripts/tests/test-documentation-integrity.py
```

The guard checks Markdown headings and local links, verifies that every `docs/**/*.md` file is listed here, rejects known retired document names and protocol/config drift, and protects the canonical Gateway base-module name.