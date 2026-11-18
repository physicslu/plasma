# z2like-demo QEMU retirement — Gate 1 audit

The retired path was Render `plasma-control-station-lab` → protected SWPC ingress → persistent ARMv7 QEMU simulated PPU. It was neither the SWPC x86 `swpc-z2like` surrogate nor the physical PYNQ-Z2 `z2-ps` PPU. The independent GitHub-hosted ephemeral HIL-A1.5 QEMU barrier test remains available; it does not use the retired demo.

Removed: the two demo-specific live-acceptance workflows and the QEMU workflow; its operator profile, ingress, target, kit, installer, control-plane, deployment, e2e and acceptance scripts; the dedicated Render service/startup; and their tests and deployment guide. The public Render Mock demo, Manager, Gateway, PPU Runtime, OpenOCD, Z2 PS and host-only Mock paths remain.

The GitHub Actions control bridge existed solely for the two retired workflows and was removed with its allowlist, contract and documentation. No replacement demo or compatibility wrapper was added.

## External operations pending owner action

Repository changes do not stop the existing Render service, SWPC container/services or Cloudflare Access/Tunnel/DNS. The owner must inventory live resources and separately retire `plasma-control-station-lab`, `z2like-demo.open4th.com`, the `ppu-managed-lab.open4th.com` ingress, related SWPC units/container/volumes and credentials as appropriate. This PR performs none of those actions. Preserve data and verify ownership before any external removal.

## PR #1476 integration

PR #1476 also changes `scripts/plasmactl` to route new read-only Unified CLI commands. This retirement changes only the existing `z2like-demo` profile/help/dispatch lines on current `main`; it does not replace #1476's new command routing. The PRs need a normal rebase or merge of their routing hunks after one lands. Review the combined CLI tests before merging either PR. No force push or merge is implied.
