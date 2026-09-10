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
  -> existing immutable Z2 installer
  -> Plasma Runtime :18080/:9900
```

In **PPU / Site Management -> Runtime Deployment**:

1. select the pending PPU;
2. confirm Bootstrap status and immutable `device_id`;
3. enter the one-time Bootstrap pairing token;
4. select the CI-produced Z2 PS kit and matching SHA-256 sidecar;
5. set PPU ID, Facility ID, and Display Name;
6. start Runtime deployment;
7. wait until deployment reports `succeeded` and Runtime reports `runtime_active`.

Normal deployment is fail-closed while any Site is actively executing. It is also blocked when Runtime or deployment state is `recovery_required`.

## Real Z2 HIL evidence A: normal lifecycle

Record before mutation:

```bash
uname -m
cat /etc/os-release
python3 --version
systemctl status plasma-bootstrap.service --no-pager
readlink -f /opt/plasma/current || true
curl -fsS http://<PPU_COMMISSIONING_IP>:18081/v1/status
```

Then perform through Console/Manager:

```text
Runtime A active
 -> deploy Runtime B
 -> Bootstrap deployment succeeded
 -> Gateway readiness ready
 -> reboot PPU
 -> Bootstrap returns
 -> Runtime B returns active/ready
```

After reboot collect:

```bash
systemctl is-active plasma-bootstrap.service
systemctl is-active plasma-server.service
systemctl is-active plasma-web.service
readlink -f /opt/plasma/current
curl -fsS http://<PPU_COMMISSIONING_IP>:18081/v1/status
curl -fsS http://<PPU_COMMISSIONING_IP>:18080/api/health/ready
```

Acceptance requires the active release identity to match the selected verified Z2 PS kit and the services to recover without manual repair.

## Real Z2 HIL evidence B: controlled rollback

Do not simulate rollback by unplugging Ethernet, killing arbitrary processes, deleting `/opt/plasma/current`, or corrupting a production release by hand. Those actions do not provide deterministic evidence and can invalidate the recovery baseline.

Rollback qualification requires a purpose-built negative HIL release that:

1. passes archive/manifest/integrity admission;
2. reaches activation;
3. deterministically fails Runtime readiness;
4. causes the existing Z2 installer to restore the previous release/config/service snapshots;
5. leaves Bootstrap reachable and reports the failed deployment evidence;
6. confirms the previous Runtime is active after reboot.

The negative artifact identity, SHA-256, previous release identity, failure reason, restored release identity, and post-reboot readiness must be retained with the HIL evidence.

Until this controlled failure injection actually runs on PYNQ-Z2, **real-hardware rollback is NOT QUALIFIED**.

## Crash/restart semantics

Two durable state layers exist deliberately:

- deployment engine journal: tracks verify/stage/activate/health/rollback transaction state;
- Bootstrap API journal: tracks queued/running/succeeded/failed operator transaction state.

If either layer observes an interrupted non-terminal transaction after restart, it must preserve the prior transaction identity, promote the state to `recovery_required`, and reject a new normal deployment. A later deployment must never silently overwrite unknown activation state.

## Proof boundary

CI can prove Python 3.10 compatibility, state-machine behavior, bundle generation, sandbox installation, Manager policy, and Browser -> BFF -> Manager -> independent Bootstrap flow.

CI/Render cannot prove stock-PYNQ systemd behavior, ARMv7 native Runtime execution, physical reboot persistence, Ethernet behavior on the actual PPU, or real rollback. Those claims require the HIL steps above.

This project does not qualify FPGA bitstream update, PS-to-PL execution, Site electrical behavior, target power, real IC programming, or physical 8-Site concurrency.
