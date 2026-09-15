# PPU Bootstrap Factory Provisioning and Z2 HIL

Status: physical PYNQ-Z2 first install, Runtime verification, reboot persistence and normal upgrade are evidenced; controlled activation-failure rollback and reboot-after-rollback remain hardware qualification steps.

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

## Controlled activation-failure qualification path

The source-tree-independent Z2 PS kit contains `scripts/ppu-bootstrap-deployment.py`. For physical rollback qualification only, the coordinator accepts:

```text
--qualification-fail-health-check
```

This option is deliberately not routed through the normal `plasmactl z2-ps`, Console, Manager or Bootstrap HTTP operator surface. It is a kit-local HIL mechanism, not a product deployment feature.

The coordinator refuses this qualification injection unless an existing previous release is selected by `/opt/plasma/current`. The injected failure occurs from the installer's post-activation health callback, after the production activation path has been entered. The production installer must therefore perform its ordinary rollback transaction; the qualification mechanism does not rewrite the current symlink, canonical configuration, units or journal itself.

Before using it, the PPU must already be `disabled` with current trusted idle observation, and the candidate kit must be a verified CI artifact. Resolve the installed Plasma Python from the existing evidence and invoke the kit-local coordinator directly:

```bash
plasma_python="$(python3 - <<'PY'
import json
print(json.load(open('/opt/plasma/install/python-runtime.json'))['python_path'])
PY
)"

sudo python3 scripts/ppu-bootstrap-deployment.py \
  --installer scripts/ppu-z2-installer.py \
  --product-root /opt/plasma \
  deploy \
  --release-artifact artifacts/plasma-ppu-<candidate>-linux-armv7l.tar.gz \
  --sidecar artifacts/plasma-ppu-<candidate>-linux-armv7l.tar.gz.sha256 \
  --plasma-python "$plasma_python" \
  --gateway-host <Z2-LAN-IP> \
  --ppu-id <PPU-ID> \
  --facility-id <FACILITY-ID> \
  --display-name <DISPLAY-NAME> \
  --qualification-fail-health-check
```

A successful qualification attempt is expected to return non-zero because candidate activation is intentionally failed. Acceptance requires all of the following afterward:

```text
/var/lib/plasma-bootstrap/deployment.json state = rolled_back
error_code = activation_failed_rolled_back
/opt/plasma/current = previous known-good release
/etc/plasma/ppu.yaml digest unchanged
Gateway /api/health/ready = ready
sudo bash scripts/plasmactl verify z2-ps = PASS
reboot retains the restored release
post-reboot verifier = PASS
```

An invalid archive, missing file, network unplug, process kill or manual symlink corruption is not equivalent evidence.

## Physical PYNQ-Z2 evidence — 2026-09-15/16

The following evidence was collected on a physical PYNQ-Z2 over a controlled private commissioning link. The session crossed midnight local time; the sequence below is one continuous qualification session.

### Artifact baseline

First-install Bootstrap and Runtime artifacts came from the same accepted commit:

```text
commit: 0a78bd4af352a4497d261d6a780d0fab50c06471
PPU bootstrap regression run: 34971024357
bootstrap artifact ZIP digest:
sha256:c0ea6d27d6dbc8f02b209722de91c30d40b0aaeb9e45a3543876c2c9b9910788

Z2 PS release candidate run: 34971386768
artifact: plasma-z2-ps-kit-0.1.1-0a78bd4af352
artifact ZIP digest:
sha256:27c79a15f12652b22c2e739522553761c48c29b3ea8b28a8f65cf37e86aefd28
```

Detached sidecars were checked with `shasum -a 256 -c`; both reported `OK`.

### Clean factory baseline — PASS

Method:

```bash
uname -a
uname -m
python3 --version
test -e /opt/plasma/current && echo runtime_present || echo runtime_absent
test -e /opt/plasma/bootstrap && echo bootstrap_present || echo bootstrap_absent
```

Observed:

```text
armv7l
PYNQ system Python 3.10.4
runtime_absent
bootstrap_absent
```

Bootstrap was installed with the canonical factory installer. `plasma-bootstrap.service` became active; Bootstrap `/v1/health` returned healthy; `/v1/status` reported `bootstrap_ready`, `runtime_absent`, and `fpga_update=false`. The pairing credential was rotated after an earlier operator-side exposure; no credential value is retained here.

### Console first install — PASS

The corrected macOS Control Station package from PR #602 / commit `310a082a783f37f79575ea83f342e412de8cd391` exposed the Bootstrap routes correctly. The new PPU registry entry `z2-hil` remained `pending`, paired successfully, and admitted the exact `0a78bd4...` kit.

After Console deployment:

```bash
readlink -f /opt/plasma/current
systemctl is-active plasma-server.service
systemctl is-active plasma-web.service
systemctl is-active plasma-runtime-activation.service
curl -fsS http://192.168.2.99:18080/api/health/ready
```

Observed:

```text
/opt/plasma/releases/0.1.1-0a78bd4af352
Server active
Gateway active
runtime-activation helper active
Gateway alive
execution ready
```

`/opt/plasma/install/last-install.json` reported `result=PASS`, Git SHA `0a78bd4af352a4497d261d6a780d0fab50c06471`, release archive SHA-256 `39d2bbc382649d106763029f0e00389ab4cf6a553c81606bcc83f5094affcf03`, and Plasma Python `3.12.13 armv7l final`. The deployment journal reported `state=runtime_active`.

Formal verification used the same-commit kit:

```bash
sudo bash scripts/plasmactl verify z2-ps
```

Observed:

```text
PASS: real Z2 ARMv7 PS runtime + local PS diagnostic loopback + P3 runtime-activation wiring
```

### First-install reboot persistence — PASS

Method:

```bash
sudo reboot
# after SSH returns
readlink -f /opt/plasma/current
systemctl is-active plasma-bootstrap.service
systemctl is-active plasma-server.service
systemctl is-active plasma-web.service
systemctl is-active plasma-runtime-activation.service
curl -fsS http://192.168.2.99:18080/api/health/ready
sudo bash scripts/plasmactl verify z2-ps
```

The same release remained selected, all services recovered, Gateway reached `alive/ready`, and the formal verifier passed without manual repair.

One timing observation was retained: immediately after reboot, systemd units could already report `active` while TCP `:18080` still returned `Connection refused`; Gateway became ready later without repair. Appliance readiness must therefore use `/api/health/ready` with a bounded deadline rather than treating `systemctl active` as sufficient. That improvement is intentionally deferred to a separate PR.

A second observation was retained: running `verify z2-ps` as unprivileged `xilinx` reported protected `/etc/plasma/ppu.yaml` as missing, while root verification passed and the file was present as `plasma:plasma 0640` under `root:plasma 0770`. Permission-denied versus missing diagnostics are intentionally deferred to a separate PR.

### Commissioning and maintenance transition — PASS

Console `Validate & Enable` moved the PPU from `pending` to `commissioned` with `Online`, `Healthy`, `execution=ready` and Runtime `In Sync`. `Reported Sites=0` was expected because this is PS-only qualification.

Before Runtime maintenance, `Disable` moved lifecycle to `disabled` while Runtime remained active.

### Normal upgrade — PASS

The upgrade candidate came from:

```text
commit: 310a082a783f37f79575ea83f342e412de8cd391
workflow run: 34990644094
artifact: plasma-z2-ps-kit-0.1.1-310a082a783f
artifact ZIP digest:
sha256:253208484f20f24b7c44988c65dc2806b6ca9d7ef333a941f0d7a33a4c13477c
```

Before upgrade:

```text
current=/opt/plasma/releases/0.1.1-0a78bd4af352
/etc/plasma/ppu.yaml sha256=ab6ebc8ba106907f08a3a3b51c2cdf1f43bd9c53cd938797b30c1f9d71637807
```

After Console deployment while lifecycle was `disabled`:

```text
current=/opt/plasma/releases/0.1.1-310a082a783f
/etc/plasma/ppu.yaml sha256=ab6ebc8ba106907f08a3a3b51c2cdf1f43bd9c53cd938797b30c1f9d71637807
journal state=runtime_active
journal previous_release=/opt/plasma/releases/0.1.1-0a78bd4af352
journal release_id=0.1.1-310a082a783f
journal artifact_sha256=676f2d79de0a6335707f47b47098057a5a9d3e23b24c4fb6acf5f7a28681f224
```

The identical pre/post `ppu.yaml` digest proves canonical configuration preservation for this transaction. The same-commit `310a...` verifier passed.

### Upgrade reboot persistence — PASS

After another normal reboot:

```text
current=/opt/plasma/releases/0.1.1-310a082a783f
/etc/plasma/ppu.yaml sha256=ab6ebc8ba106907f08a3a3b51c2cdf1f43bd9c53cd938797b30c1f9d71637807
Bootstrap active
Server active
Gateway active
runtime-activation helper active
Gateway alive
execution ready
ppu_id=z2-hil
formal z2-ps verifier PASS
```

No manual repair was required.

### Evidence status

```text
Clean factory baseline                         PASS
Bootstrap active while Runtime absent          PASS
Console first install                          PASS
Real ARMv7 Runtime + Gateway + PS loopback      PASS
First-install reboot persistence                PASS
Commissioning                                   PASS
Disabled maintenance transition                 PASS
Normal upgrade                                  PASS
Canonical ppu.yaml preservation                 PASS
Upgrade reboot persistence                      PASS
Controlled activation-failure rollback          PENDING PHYSICAL HIL
Reboot after rollback                           PENDING PHYSICAL HIL
```

Until the final two physical gates pass, the correct claim is **Real Z2 PS deployment/upgrade qualified to the completed gates**, not complete Z2 appliance deployment qualification.

## Qualification claims deliberately not made

This work does **not** qualify:

- publisher signature/authenticity;
- Bootstrap transport confidentiality outside the private commissioning link;
- FPGA bitstream update or PS-to-PL execution;
- Site electrical behavior or target power;
- real IC programming;
- physical multi-Site concurrency.

Those require separate design and evidence.
