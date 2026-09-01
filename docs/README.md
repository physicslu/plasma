# Plasma Documentation Index

本頁是 `docs/` 的 canonical 文件入口。執行中的程式、設定 schema、REST／wire contract 與自動測試優先於描述性文字；若兩者不一致，先停止操作、以實作與測試確認事實，再在同一個變更中修正文檔。

## 文件狀態

| 標記 | 意義 |
|---|---|
| **Current** | 描述目前已實作或目前必須遵守的契約。 |
| **Reference** | 設計背景、驗證邊界或維護方式；不得取代 Current contract。 |
| **Plan** | 尚未全部實作的核准方向；不能宣稱為現有能力。 |
| **Historical** | 僅供遷移背景；不是相容性或執行契約。 |

## Operator

- **Current** — [Plasma Console Operator Guide](operator/plasma-console-guide.md)：PMode／EMode、Batch Summary、操作與異常復原。

## Architecture and contracts

- **Current** — [Facility / PPU / Site Domain Model](architecture/ppu-facility-sites.md)
- **Current** — [PPU Execution Ownership](architecture/ppu-execution-ownership.md)
- **Current** — [Domain Naming and Identity Policy](architecture/domain-naming-migration.md)
- **Current** — [Web Product Modes](architecture/web-product-modes.md)
- **Current** — [Web REST API Contract](architecture/web-rest-api-contract.md)
- **Current** — [Configuration Architecture](architecture/configuration-architecture.md)
- **Current** — [Batch Domain Model](architecture/batch-domain-model.md)
- **Current** — [Server-side Batch Runtime](architecture/server-side-batch-runtime.md)
- **Current** — [Batch Persistence and Gateway Restart Recovery](architecture/batch-persistence-recovery.md)
- **Current** — [Gateway Communication and Recovery](architecture/gateway-communication-recovery.md)
- **Current** — [Production Real-Path Loopback Diagnostics](architecture/diagnostics-real-path-loopback.md)
- **Current** — [Control Plane Routing Architecture](architecture/control-plane-routing-architecture.md)：定義 Control Console、BFF、Plasma Manager、PPU Gateway、Plasma Server 的責任邊界，以及 Managed Mode 的 Programming／Loopback 共用 production route。
- **Reference** — [Remote Write Security Boundary](architecture/remote-write-security-boundary.md)
- **Current** — [PMode Factory Console v2](architecture/pmode-factory-console-v2.md)
- **Current** — [Engineering Programming Workspace](architecture/engineering-programming-workspace.md)
- **Current** — [Engineering Programming Observability](architecture/engineering-programming-observability.md)
- **Current** — [Engineering Settings UI Design System](architecture/engineering-settings-ui-design-system.md)
- **Current** — [IC Selector Architecture](architecture/ic-selector.md)
- **Current** — [Device Support and Validation](architecture/device-support-validation.md)
- **Plan** — [IC Support Reusable Profile Architecture](architecture/ic-support-profile-architecture.md)
- **Current** — [IC Support Coverage Normalization](architecture/ic-support-coverage-normalization.md)：以 derived inventory 將 production exact ICPN 正規化為 Base Device、Programming Profile 與 backend readiness，避免把商業料號數量誤當成燒錄演算法數量。
- **Current** — [IC Support Runtime Resolver Foundation](architecture/ic-support-runtime-resolver.md)：定義 exact ICPN → reusable IC Support profiles 的 runtime-consumable resolver，並維持 Profile resolved 與 backend/runtime implemented 的 fail-closed 邊界。
- **Current** — [Profile-driven OpenOCD Plan Compiler](architecture/ic-support-openocd-plan-compiler.md)：將 evidence-backed Programming Profile 與 Memory Geometry 編譯成 deterministic OpenOCD dry-run plan；C8／CB geometry 分流，但硬體 execution 維持 fail-closed。
- **Current** — [OpenOCD Compiled-Plan Executor](architecture/ic-support-openocd-plan-executor.md)：驗證 PS-side canonical OpenOCD plan → isolated software subprocess boundary；production hardware gate 仍關閉，PL/native programming 不在本階段範圍。
- **Current** — [Mock Runtime v1.1](architecture/mock-runtime-v1.1.md)
- **Current** — [Mock Synthetic Image Contract](architecture/mock-synthetic-image.md)
- **Current** — [Optional Manager Control Plane](architecture/manager-optional-control-plane.md)
- **Current** — [Manager Read-only Fleet Aggregation](architecture/manager-readonly-fleet-aggregation.md)
- **Historical** — [Historical Multi-Programmer / Multi-Site Naming](architecture/multi-programmer-sites.md)

## Development and validation

- **Current** — [Documentation Maintenance](development/documentation-maintenance.md)
- **Current** — [AI-assisted Git Workflow](development/ai-git-development-workflow.md)
- **Current** — [Codex Cloud Environment](development/codex-cloud-environment.md)
- **Current** — [Local AI Development Guide](development/local-ai-development-guide.md)
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
- **Current** — [Product Deployment Foundation](deployment/product-deployment-foundation.md)：定義跨平台 Control Station（macOS／Linux／Windows）、Z2 PPU、SWPC integration host 的產品部署責任邊界，以及 immutable release 與跨平台 read-only readiness audit。
- **Current** — [Product Release Format v1](deployment/product-release-format.md)：定義 product version、release manifest、角色／平台 artifact matrix、SHA-256 integrity、safe verification 與 clean-extraction acceptance。
- **Current** — [Control Station Runtime Packaging](deployment/control-station-runtime-packaging.md)：定義 source-tree-independent Vinext standalone Console/BFF、Manager Python zipapp、runtime manifest 與 Control Station release payload。
- **Current** — [PPU Runtime Packaging](deployment/ppu-runtime-packaging.md)：定義 Z2 PS Phase-1 source-tree-independent PPU Python zipapp、`linux-armv7l` immutable release、PS-only fail-closed configuration、systemd topology與 Managed PS Loopback 驗收邊界。
- **Reference** — [PPU ARMv7 Runtime Lab](deployment/ppu-armv7-runtime-lab.md)：定義 integration-host QEMU ARMv7 一鍵 runtime/resource 診斷、live／ready／PS Loopback 路徑隔離與非 Z2-HIL 證據邊界。
- **Reference** — [Control Station Runtime Acceptance Evidence](deployment/control-station-runtime-acceptance.md)：定義 macOS／Linux／Windows clean-runtime CI 的證據範圍與不可延伸宣稱的邊界。
- **Current** — [macOS Control Station Installer Pilot](deployment/macos-control-station-installer-pilot.md)：定義 unsigned `.pkg`、per-user `launchd` LaunchAgents、absolute Node/Python runtime binding，以及 install/start/restart/stop-start/basic-uninstall acceptance；不代表 signing/notarization readiness。
- **Current** — [Windows Control Station Installer Pilot](deployment/windows-control-station-installer-pilot.md)：定義 unsigned MSI、WinSW-backed Windows SCM services、`Program Files`／`ProgramData` 邊界，以及 install/start/restart/stop-start/basic-uninstall acceptance；不代表 signing 或真正 Windows operator-host readiness。
- **Current** — [SWPC Public Preview / Mock Environment](deployment/swpc-public-preview.md)：定義 `plasma.open4th.com` 為 SWPC 公開 Preview／Mock frontend ingress；Browser 維持 same-origin routing，且該 hostname 不得重新成為 PPU Gateway/API base。
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
