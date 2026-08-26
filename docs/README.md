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
- **Current** — [Domain Naming and Identity Policy](architecture/domain-naming-migration.md)
- **Current** — [Web Product Modes](architecture/web-product-modes.md)
- **Current** — [Web REST API Contract](architecture/web-rest-api-contract.md)
- **Current** — [Configuration Architecture](architecture/configuration-architecture.md)
- **Current** — [Batch Domain Model](architecture/batch-domain-model.md)
- **Current** — [Server-side Batch Runtime](architecture/server-side-batch-runtime.md)
- **Current** — [Gateway Communication and Recovery](architecture/gateway-communication-recovery.md)
- **Current** — [PMode Factory Console v2](architecture/pmode-factory-console-v2.md)
- **Current** — [Engineering Programming Workspace](architecture/engineering-programming-workspace.md)
- **Current** — [Engineering Programming Observability](architecture/engineering-programming-observability.md)
- **Current** — [Engineering Settings UI Design System](architecture/engineering-settings-ui-design-system.md)
- **Current** — [IC Selector Architecture](architecture/ic-selector.md)
- **Current** — [Device Support and Validation](architecture/device-support-validation.md)
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
- **Current** — [Fleet Demo Deployment](development/fleet-demo.md)
- **Current** — [Mock Continuous Delivery](development/mock-cd.md)
- **Current** — [Mock Runtime Operator Guide](development/mock-runtime-operator-guide.md)
- **Current** — [Operator Acceptance Test Matrix](development/operator-acceptance-test-matrix.md)
- **Current** — [Programming Image Observability Test Plan](development/programming-image-observability-test-plan.md)
- **Current** — [FPGA Development Guide](development/fpga-development-guide.md)
- **Current** — [FPGA Verification Guide](development/fpga-verification-guide.md)
- **Reference** — [Mock Runtime Foundation Notes](development/mock-runtime-foundation-notes.md)
- **Plan** — [Device Support Catalog Implementation Plan](development/device-support-implementation-plan.md)
- **Plan** — [OpenOCD Part-number Expansion Plan](development/openocd-part-number-expansion-plan.md)
- **Plan** — [Development Debt Register](development/todo.md)

## Deployment

- **Current** — [Deployment Index](deployment/README.md)
- **Current** — [Web Runtime Hygiene](deployment/web-runtime-hygiene.md)
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
