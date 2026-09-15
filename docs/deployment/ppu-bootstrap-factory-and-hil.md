# PPU Bootstrap Factory Provisioning and Z2 HIL

Status: software contract ready for CI qualification; real PYNQ-Z2 deployment/reboot/rollback evidence remains a hardware qualification step.

## Responsibility boundary

The factory/recovery Bootstrap is intentionally independent from the Plasma Product Runtime.

- Factory image owns Embedded Linux/PYNQ, network reachability, machine identity, Bootstrap bundle and recovery access.
- `plasma-bootstrap.service` owns authenticated Runtime artifact admission and deployment orchestration.
- Plasma Runtime owns Gateway/Server/programming execution after activation.
- Control Console/Manager owns desired Runtime deployment and operator workflow.
- FPGA lifecycle is reserved only: `fpga_update=false`. Bootstrap does not load a bitstream, change Site power or program an IC.

A factory PPU can therefore report `runtime_absent` while Bootstrap remains healthy and manageable.

## Real Z2 port profile

On the real `z2-ps` profile:

```text
<Z2-LAN-IP>:18080  Plasma Product Runtime Gateway
<Z2-LAN-IP>:18081  independent Bootstrap / recovery service
```

This is profile-specific. SWPC Z2-like `:18081` remains its restricted diagnostics/status ingress and is not the Bootstrap service.

Bootstrap HTTP is currently qualified only for a controlled private commissioning link. Transport confidentiality and publisher authenticity are **not qualified**. SHA-256 proves integrity only.

## Factory Bootstrap installation

Use the CI artifact `ppu-bootstrap-factory-bundle`. Verify its detached SHA-256 before extraction, then install only the factory layer:

```bash
sha256sum -c plasma-ppu-bootstrap-*.tar.gz.sha256
tar -xzf plasma-ppu-bootstrap-*.tar.gz
cd plasma-ppu-bootstrap-*/

sudo /usr/bin/python3 scripts/ppu-bootstrap-installer.py \
  --source-root "$PWD/scripts" \
  --host <Z2_LAN_IP> \
  --enable-now
```

Expected ownership:

```text
/opt/plasma/bootstrap/                 Bootstrap scripts
/var/lib/plasma-bootstrap/             private Bootstrap state
/etc/systemd/system/plasma-bootstrap.service
```

A clean factory install must not create `/opt/plasma/current`.

Provision the device-local pairing token separately:

```bash
sudo /usr/bin/python3 /opt/plasma/bootstrap/ppu-bootstrap-service.py provision-token
```

Treat the printed token as a one-time factory credential. Do not put it in repository files, screenshots, CI artifacts or general logs.

Validate Bootstrap while Product Runtime is absent:

```bash
systemctl is-active plasma-bootstrap.service
curl -fsS http://<Z2_LAN_IP>:18081/v1/health
curl -fsS http://<Z2_LAN_IP>:18081/v1/status
```

Expected state: `bootstrap.state=bootstrap_ready`, `runtime.state=runtime_absent`, `capabilities.fpga_update=false`.

## HIL artifact provenance

Before touching a physical PYNQ-Z2, manually dispatch both **PPU bootstrap regression** and **Z2 PS release candidate** from the same `main` commit. The Real Z2 qualification record must retain both workflow run IDs, the accepted 40-character source commit, and the downloaded artifact SHA-256 values.

The factory bundle `manifest.json` must report that exact source commit in `git_sha`. The Z2 PS kit must resolve to the same accepted source identity through its release metadata. A factory bundle from one commit and a Runtime kit from another commit are not an admissible HIL input pair even when both workflows are independently green.

This provenance requirement exists so reboot/rollback evidence can be tied to one reproducible software baseline rather than an accidental mixture of CI artifacts.

## Console first install / upgrade path

Register the PPU in Manager with its future Gateway endpoint on `:18080`. Manager derives the Bootstrap endpoint from the same host on real `z2-ps`; the Browser never selects `gateway_host` and does not receive the stored device token.

```text
Browser
  -> Console BFF
  -> Plasma Manager
  -> device-bound Bootstrap credential
  -> PPU Bootstrap :18081
  -> verified Z2 PS kit admission
  -> kit-local plasmactl z2-ps
  -> durable ppu-bootstrap-deployment journal
  -> current P3 ppu-z2-installer wrapper/core
  -> Plasma Runtime :18080 / :9900
```

In **EMode -> PPU Sites -> Runtime Deployment**:

1. Select the registered PPU.
2. Confirm Bootstrap status and immutable `device_id`.
3. Enter the one-time pairing token.
4. Select the CI-produced `plasma-z2-ps-kit-*.tar.gz` and matching `.sha256` sidecar.
5. Confirm PPU ID, Facility ID and Display Name.
6. Start Runtime deployment.
7. Wait for Bootstrap deployment state `succeeded` and Runtime state `runtime_active`.

Lifecycle gates are fail-closed:

- `pending`: first install is allowed if no Site execution is active.
- `commissioned`: normal Runtime maintenance is rejected; Disable the PPU first.
- `disabled`: requires a current trusted idle observation.
- `recovery_required`: normal deployment is rejected until explicit recovery resolves the uncertain state.

The Console mirrors these gates for operator feedback; Manager/Bootstrap remain authoritative.

## Shared CLI / Console transaction model

`plasmactl z2-ps` also routes activation through `ppu-bootstrap-deployment.py`. CLI and Console therefore share the same durable deployment journal and current P3 installer semantics rather than maintaining two activation implementations.

The current P3 installer remains authoritative for immutable release staging, canonical `/etc/plasma/ppu.yaml` preservation, bounded runtime activation, readiness verification and rollback.

## Required real Z2 HIL before appliance qualification

CI can prove software contracts, Python compatibility, artifact integrity, Browser/BFF/Manager routing, fail-closed state machines and factory bundle composition. CI cannot prove real PYNQ systemd behavior, ARMv7 runtime execution, Ethernet behavior, reboot persistence or physical rollback.

Before claiming **Z2 appliance deployment qualified**, run and retain evidence for:

1. Factory baseline: Bootstrap active while Runtime is absent.
2. Console first install through `Browser -> BFF -> Manager -> Bootstrap`.
3. Runtime active: Gateway readiness and managed PS loopback pass.
4. Reboot: Bootstrap and the same Runtime release recover without manual repair.
5. Normal upgrade from a disabled/current/trusted/idle PPU.
6. Controlled activation failure: installer restores the previous known-good Runtime and deployment journal reports rollback/failure consistently.
7. Reboot again: restored Runtime remains selected and managed PS loopback passes.

Do not simulate rollback by corrupting `/opt/plasma/current`, deleting files, unplugging Ethernet or killing arbitrary processes. Such failures do not provide deterministic activation-rollback evidence.

## Qualification claims deliberately not made

This work does **not** qualify:

- publisher signature/authenticity;
- Bootstrap transport confidentiality outside the private commissioning link;
- FPGA bitstream update or PS-to-PL execution;
- Site electrical behavior or target power;
- real IC programming;
- physical multi-Site concurrency.

Those require separate design and evidence.
