# Plasma Deployment Notes

Operational deployment behavior is defined by `scripts/plasmactl`.

- Integration-host installation, configuration, update, verification and service control: [Integration Host Deployment Guide](../development/swpc-deployment.md).
- Web runtime/HMR lifecycle rules: [Web Runtime Deployment Hygiene](web-runtime-hygiene.md).
- Single-service public Mock deployment: [Render Free Public Mock Demo](render-free-public-demo.md).
- Public API smoke acceptance: [Render Public Smoke Acceptance](render-public-smoke.md).
- Public browser acceptance: [Render Public Browser Acceptance](render-public-browser.md).

Deployment, restart, service mutation, public checkpoint creation and rollback are protected operations. Documentation and tests do not authorize executing them; obtain the required operator approval for the exact environment and action.
