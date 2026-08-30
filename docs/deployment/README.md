# Plasma Deployment Notes

Operational integration-host deployment behavior is defined by `scripts/plasmactl`. Product deployment is being separated from that SWPC-specific workflow.

- **Current foundation** — [Product Deployment Foundation](product-deployment-foundation.md): cross-platform Control Station (macOS/Linux/Windows) / Z2 PPU role boundaries, immutable release direction, platform service-manager adapters, and the implemented read-only product readiness audit.
- **Current** — [Product Release Format v1](product-release-format.md): canonical product version metadata, role/platform artifact matrix, `release.json`, detached archive SHA-256, internal `SHA256SUMS`, safe verification, and clean-extraction acceptance.
- **Current** — [Control Station Runtime Packaging](control-station-runtime-packaging.md): source-tree-independent Vinext standalone Console/BFF, Manager Python zipapp, Control Station release orchestration, and macOS/Linux/Windows clean-runtime acceptance.
- **macOS installer pilot** — [macOS Control Station Installer Pilot](macos-control-station-installer-pilot.md): unsigned `.pkg`, immutable `/Library/Application Support/Plasma` runtime, per-user `launchd` LaunchAgents, absolute external Node/Python runtime binding, install/restart/stop-start/basic-uninstall acceptance, and downloadable CI artifact.
- Integration-host installation, configuration, update, verification and service control: [Integration Host Deployment Guide](../development/swpc-deployment.md).
- Web runtime/HMR lifecycle rules: [Web Runtime Deployment Hygiene](web-runtime-hygiene.md).
- Single-service public Mock deployment: [Render Free Public Mock Demo](render-free-public-demo.md).
- Public API smoke acceptance: [Render Public Smoke Acceptance](render-public-smoke.md).
- Public browser acceptance: [Render Public Browser Acceptance](render-public-browser.md).

The current `scripts/plasmactl` contract remains an integration-host contract. It must not be treated as the future Control Station or Z2 product installer. The product Control Station is one OS-neutral role with platform adapters for macOS `launchd`, Linux `systemd`, and Windows Service Control Manager (SCM).

Product release construction is a separate build-side concern. `scripts/product-release.py` consumes an already-built runtime payload and emits a role/platform-specific immutable artifact; it does not build source code or mutate a target host. Control Station packaging adds `scripts/control-station-release.py` as a narrow policy adapter so the validated Vinext standalone `console/node_modules/**` runtime dependency tree can enter the same Common Release Format without weakening the generic release builder's arbitrary-`node_modules` rejection.

The macOS installer pilot is the first host-mutating product adapter. It is deliberately unsigned and non-notarized, keeps Node.js and Python as external prerequisites, and must not be described as production Apple distribution readiness.

Deployment, restart, service mutation, public checkpoint creation and rollback are protected operations. Documentation and tests do not authorize executing them; follow the repository Two-Gate Model and the approved plan for the exact environment and action.
