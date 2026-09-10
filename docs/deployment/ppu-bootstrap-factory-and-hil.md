# PPU Bootstrap Factory Provisioning and HIL Qualification

Status: engineering qualification contract for Console-managed PPU Runtime lifecycle.

## Responsibility boundary

The factory/recovery layer is intentionally smaller and more stable than the Plasma Product Runtime.

- Factory image owns Embedded Linux/PYNQ, network reachability, machine identity, the Bootstrap bundle, and recovery access.
- `plasma-bootstrap.service` owns authenticated Runtime artifact admission and deployment orchestration.
- Plasma Runtime owns Gateway/Server/programming execution after activation.
- Control Console/Manager owns desired Runtime state and operator workflow.
- FPGA image lifecycle is reserved only. `fpga_update=false`; this procedure does not load a bitstream, touch Site power, or program an IC.

The Bootstrap bundle is **not** a Plasma Runtime release. A PPU may report `runtime_absent` while Bootstrap remains healthy and manageable.

## Factory bundle

CI workflow `PPU bootstrap regression` publishes artifact `ppu-bootstrap-factory-bundle` containing:

- `plasma-ppu-bootstrap-<bootstrap-version>-<git-sha12>.tar.gz`
- matching portable `.sha256` sidecar
- sandbox install evidence

The bundle contains only the Bootstrap scripts and installer. It intentionally contains no Runtime, control token, FPGA image, Device Catalog, or IC Programming Image.

SHA-256 proves artifact integrity only. Publisher authenticity/signature is not yet qualified and must not be claimed.

The same workflow publishes a separate `ppu-bootstrap-hil-tools` artifact containing the read-only HIL evidence collector and this procedure. The HIL tool is qualification-only and is **not** installed into `/opt/plasma/bootstrap` by the factory installer.

## Factory provisioning

On a stock PYNQ-Z2 / Embedded Linux target, copy the CI-produced bundle and sidecar to a temporary directory. Verify before extraction:

```bash
sha256sum -c plasma-ppu-bootstrap-*.tar.gz.sha256
tar -xzf plasma-ppu-bootstrap-*.tar.gz
cd plasma-ppu-bootstrap-*/
```

Install only the Bootstrap layer. The bind address must be the explicit commissioning-interface IPv4 address assigned to this PPU:

```bash
sudo /usr/bin/python3 scripts/ppu-bootstrap-installer.py \
  --source-root "$PWD/scripts" \
  --host <PPU_COMMISSIONING_IP> \
  --enable-now
```

Expected ownership after this step:

```text
/opt/plasma/bootstrap/                  factory/recovery scripts
/var/lib/plasma-bootstrap/              device-local Bootstrap state
/etc/systemd/system/plasma-bootstrap.service
```

This step must **not** create `/opt/plasma/current` on a factory PPU that has no Product Runtime.

Provision the device-local control token separately:

```bash
sudo /usr/bin/python3 /opt/plasma/bootstrap/ppu-bootstrap-service.py provision-token
```

Treat the printed value as a one-time factory pairing credential. Do not place it in repo files, shell history, CI artifacts, screenshots, or general application logs. Production device-certificate / publisher-signature policy remains a separate security closure item.

Validate Bootstrap without requiring Plasma Runtime:

```bash
systemctl is-active plasma-bootstrap.service
curl -fsS http://<PPU_COMMISSIONING_IP>:18081/v1/health
curl -fsS http://<PPU_COMMISSIONING_IP>:18081/v1/status
```

For a fresh factory PPU the expected Runtime state is `runtime_absent` and `capabilities.fpga_update` remains `false`.

## Qualification-only evidence collector

Copy `ppu-bootstrap-hil-evidence.py` from the CI artifact `ppu-bootstrap-hil-tools` to a temporary location on the PPU, for example `/tmp/plasma-bootstrap-hil/`. Do not install it as a system service.

The collector is read-only. It records:

- Linux architecture, Python version and `/etc/os-release`;
- `plasma-bootstrap.service`, `plasma-server.service`, and `plasma-web.service` state;
- safe `/opt/plasma/current` release identity;
- Bootstrap `/v1/status`;
- Gateway `/api/health/ready`;
- mode-checked Bootstrap API and deployment-engine journals.

It never activates a release, restarts a service, reboots the PPU, changes network state, loads FPGA content, touches Site power, or programs an IC.

Factory checkpoint:

```bash
sudo /usr/bin/python3 /tmp/plasma-bootstrap-hil/ppu-bootstrap-hil-evidence.py \
  factory \
  --ppu-ip <PPU_COMMISSIONING_IP> \
  --output /tmp/plasma-bootstrap-hil/factory.json
```

A PASS requires Bootstrap active/ready, no `/opt/plasma/current`, Runtime state `runtime_absent`, and `fpga_update=false`. Server/Gateway are not required at the factory checkpoint.

## Console first-install / upgrade path

Register the PPU in Plasma Manager using the future Plasma Gateway endpoint on port 18080. The Bootstrap transport is derived from the same registered host on port 18081; the Browser does not choose `gateway_host` and does not retain the device token after pairing.

Operator path:

```text
Browser
  -> Control Console BFF
  -> Plasma Manager
  -> device-bound Bootstrap credential
  -> PPU Bootstrap :18081
  -> verified Z2 PS kit admission
  -> kit-local plasmactl z2-ps
  -> durable Bootstrap deployment coordinator
  -> existing immutable Z2 installer
  -> Plasma Runtime :18080/:9900
```

The canonical Z2 PS kit must contain `ppu-bootstrap-deployment.py`. A kit without the coordinator is rejected as incomplete. CLI and Console activation therefore share the same durable deployment journal and restart policy.

In **PPU / Site Management -> Runtime Deployment**:

1. select the pending PPU;
2. confirm Bootstrap status and immutable `device_id`;
3. enter the one-time Bootstrap pairing token;
4. select the CI-produced Z2 PS kit and matching SHA-256 sidecar;
5. set PPU ID, Facility ID, and Display Name;
6. start Runtime deployment;
7. wait until deployment reports `succeeded` and Runtime reports `runtime_active`.

Normal deployment is fail-closed while any Site is actively executing. It is also blocked when Runtime or deployment state is `recovery_required`. A commissioned PPU must enter the explicit maintenance/disabled lifecycle before normal upgrade; stale or unknown fleet state is not treated as idle.

## Evidence layers must remain separate

Two independent evidence surfaces are required during HIL:

1. **PPU-local checkpoint JSON** proves real Linux/ARMv7, systemd state, active release identity, Gateway readiness, and durable journals.
2. **Managed PS Loopback acceptance** proves `Control Console BFF -> Manager -> real PPU Gateway -> Plasma Server -> PS -> return`.

Neither proves the other. A local PPU PASS is not Managed Mode evidence, and a Managed PS Loopback PASS does not prove reboot persistence or rollback state.

## Real Z2 HIL evidence A: normal lifecycle

### A1. Factory baseline

Before first Runtime installation, collect:

```bash
sudo /usr/bin/python3 /tmp/plasma-bootstrap-hil/ppu-bootstrap-hil-evidence.py \
  factory \
  --ppu-ip <PPU_COMMISSIONING_IP> \
  --output /tmp/plasma-bootstrap-hil/a1-factory.json
```

### A2. Console deployment

Perform the first install or normal upgrade through Console/Manager only. Do not invoke the installer directly for this evidence transaction.

After Console reports `succeeded`, record the exact release identity selected from Bootstrap status or `/opt/plasma/current`, then collect:

```bash
sudo /usr/bin/python3 /tmp/plasma-bootstrap-hil/ppu-bootstrap-hil-evidence.py \
  runtime-active \
  --ppu-ip <PPU_COMMISSIONING_IP> \
  --expected-release-id <EXPECTED_RELEASE_ID> \
  --output /tmp/plasma-bootstrap-hil/a2-runtime-active.json
```

A PASS requires:

- Bootstrap, Server and Gateway services active;
- `/opt/plasma/current` resolves safely under `/opt/plasma/releases` and equals `<EXPECTED_RELEASE_ID>`;
- Bootstrap Runtime state is `runtime_active` with the same release ID;
- Gateway readiness is HTTP 200 with `ok=true`, `gateway=alive`, `execution=ready`;
- deployment-engine journal is trusted and `runtime_active`;
- Bootstrap API journal is trusted and `succeeded`.

### A3. Managed PS control-path proof

From the Control Station, use the existing managed acceptance runner against the Console BFF:

```bash
python3 scripts/runtime_acceptance/run.py ps-loopback \
  --base-url http://<CONTROL_STATION>/api/manager/ppu \
  --environment managed-software \
  --evidence-root artifacts/runtime-acceptance/bootstrap-z2
```

A PASS proves the selected PPU alias and Manager pass-through evidence. This diagnostic is PS-only and does not touch PL/Site/power/IC.

### A4. Reboot persistence

Reboot the PPU as an explicit HIL action. Do not edit Runtime state during boot recovery. After the PPU returns, collect:

```bash
sudo /usr/bin/python3 /tmp/plasma-bootstrap-hil/ppu-bootstrap-hil-evidence.py \
  runtime-after-reboot \
  --ppu-ip <PPU_COMMISSIONING_IP> \
  --expected-release-id <EXPECTED_RELEASE_ID> \
  --output /tmp/plasma-bootstrap-hil/a4-runtime-after-reboot.json
```

Then repeat the managed `ps-loopback` acceptance from the Control Station. Acceptance requires the same release identity and service/control-path recovery without manual repair.

## Real Z2 HIL evidence B: controlled rollback

Do not simulate rollback by unplugging Ethernet, killing arbitrary processes, deleting `/opt/plasma/current`, or corrupting a production release by hand. Those actions do not provide deterministic evidence and can invalidate the recovery baseline.

Rollback qualification requires a purpose-built negative HIL release that:

1. passes archive/manifest/integrity admission;
2. reaches activation;
3. deterministically fails Runtime readiness;
4. causes the existing Z2 installer to restore the previous release/config/service snapshots;
5. leaves Bootstrap reachable and records the failed API transaction;
6. confirms the previous Runtime is active after reboot.

Use an already-qualified Runtime A as the rollback target. Do not use first installation as the rollback proof because rollback-to-no-Runtime is a different recovery case.

Immediately after the controlled failure, collect:

```bash
sudo /usr/bin/python3 /tmp/plasma-bootstrap-hil/ppu-bootstrap-hil-evidence.py \
  rollback-restored \
  --ppu-ip <PPU_COMMISSIONING_IP> \
  --expected-release-id <RUNTIME_A_RELEASE_ID> \
  --output /tmp/plasma-bootstrap-hil/b1-rollback-restored.json
```

A PASS requires the active/Bootstrap release to be Runtime A, the deployment-engine journal to be `rolled_back`, and the Bootstrap API journal to be `failed`.

Reboot once more, then collect:

```bash
sudo /usr/bin/python3 /tmp/plasma-bootstrap-hil/ppu-bootstrap-hil-evidence.py \
  rollback-after-reboot \
  --ppu-ip <PPU_COMMISSIONING_IP> \
  --expected-release-id <RUNTIME_A_RELEASE_ID> \
  --output /tmp/plasma-bootstrap-hil/b2-rollback-after-reboot.json
```

Repeat managed PS Loopback after reboot. The negative artifact identity, SHA-256, previous release identity, deterministic failure reason, restored release identity, both journal identities/states, and post-reboot Managed PS evidence must be retained together.

Until this controlled failure injection actually runs on PYNQ-Z2, **real-hardware rollback is NOT QUALIFIED**.

## Crash/restart semantics

Two durable state layers exist deliberately on the production Console deployment path:

- deployment engine journal: tracks verify/stage/activate/health/rollback transaction state;
- Bootstrap API journal: tracks queued/running/succeeded/failed operator transaction state.

`plasmactl z2-ps` activation is routed through the deployment coordinator, and the canonical Z2 PS kit is required to contain that coordinator. The two journals therefore describe different layers of the same Console-initiated deployment rather than independent test-only implementations.

If the Bootstrap API observes its own `queued`/`running` record after service restart, it promotes that API transaction to `recovery_required` and rejects a new normal deployment. If the deployment coordinator next observes a non-terminal engine transaction, it likewise promotes the engine journal to `recovery_required` before admitting another deployment. A later deployment must never silently overwrite unknown activation state.

## Proof boundary

CI can prove Python 3.10 compatibility, state-machine behavior, canonical call graph, Z2 kit packaging, bundle generation, sandbox installation, Manager policy, and Browser -> BFF -> Manager -> independent Bootstrap admission flow.

CI cannot prove stock-PYNQ systemd behavior, ARMv7 native Runtime execution on the physical board, physical reboot persistence, Ethernet behavior on the actual PPU, or real rollback. Those claims require the HIL steps above.

This project does not qualify FPGA bitstream update, PS-to-PL execution, Site electrical behavior, target power, real IC programming, or physical 8-Site concurrency.