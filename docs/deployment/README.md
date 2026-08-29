# Plasma Deployment Notes

Operational integration-host deployment behavior is defined by `scripts/plasmactl`. Product deployment is being separated from that SWPC-specific workflow.

- **Plan** — [Product Deployment Foundation](product-deployment-foundation.md): cross-platform Control Station (macOS/Linux/Windows) / Z2 PPU role boundaries, immutable release direction, platform service-manager adapters, and the first read-only product readiness audit.
- Integration-host installation, configuration, update, verification and service control: [Integration Host Deployment Guide](../development/swpc-deployment.md).
- Web runtime/HMR lifecycle rules: [Web Runtime Deployment Hygiene](web-runtime-hygiene.md).
- Single-service public Mock deployment: [Render Free Public Mock Demo](render-free-public-demo.md).
- Public API smoke acceptance: [Render Public Smoke Acceptance](render-public-smoke.md).
- Public browser acceptance: [Render Public Browser Acceptance](render-public-browser.md).

The current `scripts/plasmactl` contract remains an integration-host contract. It must not be treated as the future Control Station or Z2 product installer. The product Control Station is one OS-neutral role with platform adapters for macOS `launchd`, Linux `systemd`, and Windows Service Control Manager.

Deployment, restart, service mutation, public checkpoint creation and rollback are protected operations. Documentation and tests do not authorize executing them; follow the repository Two-Gate Model and the approved plan for the exact environment and action.
