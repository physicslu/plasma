"""LOM-P2A-2 Host-only tests of the PPU controller engine beyond the P2A-0 cases.

PS-GPIO button entry (request binding, contention, long press / debounce,
simulated sysfs GPIO), Engineering Mode authorization, concurrent takeover,
fsync/rename crash injection and the real PPU safety probe. No GPIO, SD card,
Z2, FPGA or DUT is touched.
"""
from __future__ import annotations

import fcntl
import json
import os
import socket
import threading
from pathlib import Path

import pytest

from . import lom_p2a2_real_engine_shim as shim

controller = shim.controller
proto = controller.proto
ROOT = Path(__file__).resolve().parents[3]
DEVICE = "ppu-device-7ed4b30913a9bf6101da5a7a"


class _Probe:
    def __init__(self) -> None:
        self.active: list[str] = []
        self.sealed: list[int] = []
        self.unknown: list[str] = []
        self.recovery_required = False

    def active_operations(self): return list(self.active)
    def seals(self): return list(self.sealed)
    def unknown_outcomes(self): return list(self.unknown)
    def active_set_recovery_required(self): return self.recovery_required
    def extra_blockers(self): return []
    def diagnose_site(self, site): return {}
    def recover_site(self, site, *, operator): return {}


def _engine(tmp_path: Path, *, button: bool = True, probe=None):
    store = controller.ControllerStore(tmp_path / "state")
    return controller.EnrollmentEngine(store, probe or _Probe(), device_id=DEVICE, boot_id="boot-1",
                                       button_enabled=button)


def _button_claim(engine, private: bytes, public: str, now: float, *, label="cs"):
    challenge = engine.challenge(now)
    key = proto.button_key(private, peer_public=challenge["ppu_public"], device_id=challenge["device_id"],
                           request_id=challenge["enrollment_id"], controller_public=public,
                           ppu_public=challenge["ppu_public"])
    cn = os.urandom(16).hex()
    response = engine.claim(proto.claim_request(key, challenge, controller_nonce=cn, label=label), now)
    return response, proto.unwrap_credential(key, nonce=response["wrap_nonce"], controller_nonce=cn,
                                             generation=response["generation"],
                                             wrapped=response["wrapped_credential"])


# --- protocol -----------------------------------------------------------------

def test_x25519_matches_rfc7748_vectors():
    h = bytes.fromhex
    assert proto.x25519(h("a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4"),
                        h("e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c")).hex() == \
        "c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552"
    alice = h("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
    bob = h("5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb")
    nine = (9).to_bytes(32, "little")
    assert proto.x25519(alice, nine).hex() == "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a"
    assert proto.x25519(alice, proto.x25519(bob, nine)).hex() == \
        "4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742"


def test_manager_protocol_module_is_byte_identical_to_the_ppu_module():
    assert (ROOT / "software/python/plasma_manager/local_enrollment.py").read_bytes() == \
        (ROOT / "scripts/ppu_local_enrollment.py").read_bytes()


# --- PS-GPIO button entry ---------------------------------------------------------

def test_button_binds_exactly_the_single_requesting_station(tmp_path):
    engine = _engine(tmp_path)
    private, public = proto.x25519_keypair()
    view = engine.button_request({"controller_public": public, "label": "cs-a"}, 1.0)
    assert view["state"] == "AWAITING_BUTTON"
    assert engine.challenge.__self__ is engine
    with pytest.raises(controller.ControllerError) as not_armed:
        engine.challenge(1.5)                       # a LAN request alone arms nothing
    assert not_armed.value.code == "ENROLLMENT_NOT_ARMED"
    assert engine.button_pressed(2.0) == "ENROLLMENT_ARMED:ps-gpio-button"
    response, credential = _button_claim(engine, private, public, 3.0)
    assert (response["generation"], response["mode"], response["source"]) == (1, "NORMAL", "ps-gpio-button")
    assert engine.authorize(credential, "site.job.submit") == "NORMAL"
    assert credential not in json.dumps(response)


def test_button_window_cannot_be_claimed_by_another_station(tmp_path):
    engine = _engine(tmp_path)
    _private, public = proto.x25519_keypair()
    engine.button_request({"controller_public": public}, 1.0)
    engine.button_pressed(2.0)
    attacker_private, attacker_public = proto.x25519_keypair()
    for attempt in range(proto.MAX_CLAIM_FAILURES):
        with pytest.raises(controller.ControllerError) as exc:
            _button_claim(engine, attacker_private, attacker_public, 3.0 + attempt)
        expected = ("ENROLLMENT_LOCKED_OUT" if attempt == proto.MAX_CLAIM_FAILURES - 1
                    else "ENROLLMENT_PROOF_INVALID")
        assert exc.value.code == expected
    assert engine.controller_state() == "UNENROLLED"


def test_competing_request_makes_the_window_contended_and_nobody_wins(tmp_path):
    engine = _engine(tmp_path)
    _p1, owner_public = proto.x25519_keypair()
    _p2, rival_public = proto.x25519_keypair()
    engine.button_request({"controller_public": owner_public}, 1.0)
    assert engine.button_request({"controller_public": owner_public}, 1.5)["state"] == "AWAITING_BUTTON"
    with pytest.raises(controller.ControllerError) as rival:
        engine.button_request({"controller_public": rival_public}, 2.0)
    assert rival.value.code == "ENROLLMENT_CONTENDED"
    with pytest.raises(controller.ControllerError) as owner_again:
        engine.button_request({"controller_public": owner_public}, 3.0)
    assert owner_again.value.code == "ENROLLMENT_CONTENDED"       # no winner is picked
    assert engine.button_pressed(4.0) == "BUTTON_PRESS_REFUSED_CONTENDED"
    assert engine.enrollment_state(4.0) == "NONE"
    # The contention ends with the request window; a fresh single request works.
    later = 1.0 + proto.BUTTON_REQUEST_WINDOW_S + 1
    assert engine.button_request({"controller_public": owner_public}, later)["state"] == "AWAITING_BUTTON"


def test_press_without_request_disabled_or_while_armed_never_arms(tmp_path):
    engine = _engine(tmp_path)
    assert engine.button_pressed(1.0) == "BUTTON_PRESS_IGNORED_NO_REQUEST"
    assert engine.enrollment_state(1.0) == "NONE"
    ticket = engine.engineering_arm(2.0, authorized=True)
    assert ticket
    _p, public = proto.x25519_keypair()
    with pytest.raises(controller.ControllerError) as busy:
        engine.button_request({"controller_public": public}, 3.0)
    assert busy.value.code == "ENROLLMENT_BUSY"
    assert engine.button_pressed(3.5) == "BUTTON_PRESS_IGNORED_BUSY"
    disabled = _engine(tmp_path / "other", button=False)
    with pytest.raises(controller.ControllerError) as off:
        disabled.button_request({"controller_public": public}, 1.0)
    assert off.value.code == "ENROLLMENT_BUTTON_DISABLED"
    assert disabled.button_pressed(1.0) == "BUTTON_PRESS_IGNORED_DISABLED"


@pytest.mark.parametrize("body", [
    {"controller_public": "A" * 64}, {"controller_public": "a" * 63}, {},
    {"controller_public": "a" * 64, "label": "x" * 65}, {"controller_public": "a" * 64, "extra": 1},
])
def test_malformed_button_requests_are_rejected(tmp_path, body):
    with pytest.raises(controller.ControllerError) as exc:
        _engine(tmp_path).button_request(body, 1.0)
    assert exc.value.code == "ENROLLMENT_PROOF_INVALID"


# --- long press / debounce state machine -----------------------------------------

def _feed(detector, samples):
    return [t for t, level in samples if detector.feed(level, t)]


def test_long_press_fires_once_after_hold_and_ignores_bounce():
    d = controller.LongPressDetector(debounce_s=0.05, hold_s=3.0)
    samples = [(0.0, False), (0.1, False)]
    # Contact bounce: 20 ms pulses never become a stable press.
    samples += [(0.20, True), (0.22, False), (0.24, True), (0.26, False), (0.30, False)]
    samples += [(1.00, True)] + [(1.00 + 0.01 * i, True) for i in range(1, 400)]
    fired = _feed(d, samples)
    assert len(fired) == 1 and 3.99 <= fired[0] + 0.0 <= 4.01


def test_short_press_and_held_button_do_not_refire():
    d = controller.LongPressDetector(debounce_s=0.05, hold_s=3.0)
    assert _feed(d, [(0.0, False), (0.1, False), (0.2, True), (3.1, True), (3.2, False), (3.3, False)]) == []
    fired = _feed(d, [(4.0, True), (7.1, True), (9.0, True), (20.0, True)])
    assert fired == [7.1]                      # once per press, never while held
    assert _feed(d, [(20.1, False), (20.2, False), (21.0, True), (24.1, True)]) == [24.1]


def test_line_active_at_start_must_be_released_first():
    d = controller.LongPressDetector(debounce_s=0.05, hold_s=3.0)
    assert _feed(d, [(0.0, True), (1.0, True), (5.0, True), (10.0, True)]) == []
    assert _feed(d, [(10.1, False), (10.2, False), (11.0, True), (14.1, True)]) == [14.1]


# --- simulated sysfs GPIO and board profile ---------------------------------------

def _fake_sysfs(root: Path, *, chips=(("gpiochip0", "zynq_gpio", 906, 118),)) -> Path:
    for name, label, base, ngpio in chips:
        chip = root / name
        chip.mkdir(parents=True)
        (chip / "label").write_text(label + "\n")
        (chip / "base").write_text(f"{base}\n")
        (chip / "ngpio").write_text(f"{ngpio}\n")
    (root / "export").write_text("")
    return root


def _profile(**overrides):
    values = dict(enabled=True, chip_label="zynq_gpio", line=12, active_low=True)
    values.update(overrides)
    return controller.ButtonProfile(**values)


def test_sysfs_gpio_resolves_label_forces_input_and_maps_active_low(tmp_path):
    sysfs = _fake_sysfs(tmp_path / "gpio")
    line_dir = sysfs / "gpio918"
    line_dir.mkdir()
    (line_dir / "direction").write_text("out")
    (line_dir / "value").write_text("1\n")
    line = controller.SysfsGpioInput(_profile(), sysfs)
    assert line.number == 906 + 12
    assert (line_dir / "direction").read_text() == "in"       # never left as an output
    assert line.active() is False                              # pulled up = released
    (line_dir / "value").write_text("0\n")
    assert line.active() is True                               # to GND = pressed


@pytest.mark.parametrize("chips, message", [
    ((("gpiochip0", "other", 0, 54),), "not present"),
    ((("gpiochip0", "zynq_gpio", 0, 118), ("gpiochip1", "zynq_gpio", 200, 118)), "ambiguous"),
    ((("gpiochip0", "zynq_gpio", 0, 8),), "not present"),
])
def test_sysfs_gpio_fails_closed_on_missing_or_ambiguous_chip(tmp_path, chips, message):
    sysfs = _fake_sysfs(tmp_path / "gpio", chips=chips)
    with pytest.raises(RuntimeError, match=message):
        controller.SysfsGpioInput(_profile(), sysfs)


def test_button_watcher_arms_through_the_engine_on_a_simulated_long_press(tmp_path):
    engine = _engine(tmp_path)
    private, public = proto.x25519_keypair()
    engine.button_request({"controller_public": public}, 0.0)

    class Line:
        level = False
        def active(self):
            return self.level

    clock = [0.0]
    line = Line()
    watcher = controller.ButtonWatcher(engine, line, _profile(), clock=lambda: clock[0])
    outcomes = []
    for step in range(0, 400):
        clock[0] = step * 0.01
        line.level = step >= 50
        outcomes.append(watcher.poll_once())
    assert [o for o in outcomes if o] == ["ENROLLMENT_ARMED:ps-gpio-button"]
    response, _credential = _button_claim(engine, private, public, clock[0] + 1)
    assert response["source"] == "ps-gpio-button"


def test_shipped_z2_profile_is_valid_disabled_and_pin_free_engine():
    raw_path = ROOT / "scripts/ppu-board-profiles/pynq-z2-enrollment-button.json"
    profile = controller.ButtonProfile.load(raw_path, reader=lambda p: json.loads(p.read_text()))
    assert profile.enabled is False and profile.disabled_reason
    assert (profile.chip_label, profile.line, profile.active_low) == ("zynq_gpio", 12, True)
    assert (profile.debounce_ms, profile.hold_ms) == (50, 3000)
    engine_source = (ROOT / "scripts/ppu_controller.py").read_text()
    assert "MIO12" not in engine_source and '"zynq_gpio"' not in engine_source


@pytest.mark.parametrize("change", [
    {"debounce_ms": 5}, {"hold_ms": 500}, {"poll_ms": 100}, {"enabled": "yes"},
    {"gpio": {"chip_label": "zynq_gpio", "line": 12}}, {"schema": "x"}, {"unknown": 1},
])
def test_invalid_button_profiles_are_rejected(change):
    raw = json.loads((ROOT / "scripts/ppu-board-profiles/pynq-z2-enrollment-button.json").read_text())
    raw.update(change)
    with pytest.raises(ValueError):
        controller.ButtonProfile.load(Path("x"), reader=lambda _p: raw)


# --- Engineering Mode -------------------------------------------------------------

@pytest.mark.parametrize("policy, ok", [
    (None, False),
    ({"schema": "plasma.ppu.engineering-mode.v1", "enrollment_cli": True, "expires_at_epoch_s": 2e9}, True),
    ({"schema": "plasma.ppu.engineering-mode.v1", "enrollment_cli": True, "expires_at_epoch_s": 1.0}, False),
    ({"schema": "plasma.ppu.engineering-mode.v1", "enrollment_cli": True}, False),
    ({"schema": "plasma.ppu.engineering-mode.v1", "enrollment_cli": False, "expires_at_epoch_s": 2e9}, False),
    ({"schema": "other", "enrollment_cli": True, "expires_at_epoch_s": 2e9}, False),
])
def test_engineering_mode_requires_a_trusted_explicit_unexpired_policy(policy, ok):
    def reader(_path):
        if policy is None:
            raise FileNotFoundError
        return policy
    assert controller.engineering_mode_authorized(Path("p"), now_epoch=1.9e9, trusted_reader=reader)[0] is ok


def test_engineering_policy_must_be_root_owned_and_not_writable_by_others(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"schema": "plasma.ppu.engineering-mode.v1", "enrollment_cli": True,
                                "expires_at_epoch_s": 2e9}))
    ok, reason = controller.engineering_mode_authorized(path)
    if os.geteuid() != 0:
        assert ok is False and "root-owned" in reason      # host user cannot forge it


def test_enroll_cli_refuses_without_root(tmp_path, capsys):
    if os.geteuid() == 0:
        pytest.skip("host test runs unprivileged")
    cli = shim._load("plasma_ppu_enroll_cli", "ppu-enroll.py")
    assert cli.main(["--state-root", str(tmp_path), "arm"]) == 77
    assert "ENGINEERING_MODE_NOT_AUTHORIZED" in capsys.readouterr().err
    assert not (tmp_path / "controller").exists()


# --- concurrency and crash injection ------------------------------------------------

def test_concurrent_claims_of_one_window_commit_exactly_once(tmp_path):
    engine = _engine(tmp_path)
    ticket = engine.engineering_arm(0.0, authorized=True)
    key = proto.ticket_key(ticket)
    challenges = [engine.challenge(1.0) for _ in range(6)]
    results, barrier = [], threading.Barrier(6)

    def claim(ch, i):
        barrier.wait()
        try:
            results.append(engine.claim(proto.claim_request(
                key, ch, controller_nonce=f"{i:032x}", label=f"s{i}"), 2.0)["generation"])
        except controller.ControllerError as exc:
            results.append(exc.code)

    threads = [threading.Thread(target=claim, args=(ch, i)) for i, ch in enumerate(challenges)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(1) == 1
    assert set(results) - {1} <= {"ENROLLMENT_TICKET_CONSUMED"}
    assert engine.controller()["generation"] == 1


def test_takeover_waits_for_an_in_flight_admission_then_defers(tmp_path):
    probe = _Probe()
    engine = _engine(tmp_path, probe=probe)
    ticket = engine.engineering_arm(0.0, authorized=True)
    key = proto.ticket_key(ticket)
    engine.fence.acquire_shared()                  # a Gateway write is being admitted
    engine.fence_wait_s = 0.2
    with pytest.raises(controller.ControllerError) as deferred:
        engine.claim(proto.claim_request(key, engine.challenge(1.0), controller_nonce="1" * 32,
                                         label="b"), 1.0)
    assert deferred.value.code == "TAKEOVER_DEFERRED_ACTIVE_OPERATION"
    assert deferred.value.detail == ["write-admission-in-progress"]
    assert engine.controller() is None and engine.enrollment_state(1.0) == "ARMED"
    engine.fence.release_shared()
    response = engine.claim(proto.claim_request(key, engine.challenge(2.0), controller_nonce="1" * 32,
                                                label="b"), 2.0)
    assert response["generation"] == 1


def test_admission_blocks_while_a_takeover_commits(tmp_path):
    engine = _engine(tmp_path)
    started, release = threading.Event(), threading.Event()
    with engine.fence.exclusive():
        def admit():
            started.set()
            try:
                engine.fence.acquire_shared(timeout_s=0.2)
            except controller.ControllerError as exc:
                outcome.append(exc.code)
            else:
                outcome.append("admitted")
                engine.fence.release_shared()
            release.set()
        outcome: list[str] = []
        thread = threading.Thread(target=admit)
        thread.start()
        started.wait()
        release.wait(2)
    thread.join()
    assert outcome == ["CONTROLLER_TRANSITION_IN_PROGRESS"]


def test_power_loss_during_record_rename_keeps_the_old_controller(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    ticket_a = engine.engineering_arm(0.0, authorized=True)
    shim_ppu = shim  # noqa: F841
    key_a = proto.ticket_key(ticket_a)
    first = engine.claim(proto.claim_request(key_a, engine.challenge(1.0), controller_nonce="a" * 32,
                                             label="a"), 1.0)
    before = engine.store.path("controller").read_bytes()
    ticket_b = _engine(tmp_path).engineering_arm(2.0, authorized=True)
    key_b = proto.ticket_key(ticket_b)
    challenge = engine.challenge(3.0)
    real_replace = os.replace

    def failing_replace(src, dst):
        if str(dst).endswith("controller.json"):
            raise OSError("power lost during rename")
        return real_replace(src, dst)

    monkeypatch.setattr(controller.os, "replace", failing_replace)
    with pytest.raises(OSError):
        engine.claim(proto.claim_request(key_b, challenge, controller_nonce="b" * 32, label="b"), 3.0)
    monkeypatch.setattr(controller.os, "replace", real_replace)
    assert engine.store.path("controller").read_bytes() == before        # old record intact
    assert not [p for p in engine.store.root.iterdir() if p.name.endswith(".new")]
    assert engine.controller()["generation"] == first["generation"] == 1
    retry = engine.claim(proto.claim_request(key_b, engine.challenge(4.0), controller_nonce="b" * 32,
                                             label="b"), 4.0)
    assert retry["generation"] == 2


def test_corrupt_or_group_readable_records_fail_closed(tmp_path):
    engine = _engine(tmp_path)
    ticket = engine.engineering_arm(0.0, authorized=True)
    response = engine.claim(proto.claim_request(proto.ticket_key(ticket), engine.challenge(1.0),
                                                controller_nonce="c" * 32, label="c"), 1.0)
    assert response["generation"] == 1
    engine.store.path("controller").chmod(0o640)
    with pytest.raises(controller.ControllerError) as broad:
        engine.authorize("x" * 64, "status.read")
    assert broad.value.code == "CONTROLLER_STATE_INVALID"
    assert engine.controller_state() == "FAULT"


# --- real PPU safety probe -----------------------------------------------------------

def _lease_server(path: Path, reply: bytes):
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(4)

    def serve():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            with conn:
                conn.recv(4096)
                conn.sendall(reply)

    threading.Thread(target=serve, daemon=True).start()
    return server


def _probe(tmp_path: Path, **kwargs):
    defaults = dict(seal_dir=tmp_path / "seals", runtime_control_socket=tmp_path / "control.sock",
                    reload_fence=tmp_path / "mmio.lock", bootstrap_active=lambda: [],
                    bootstrap_unknown=lambda: [], bootstrap_recovery_required=lambda: False)
    defaults.update(kwargs)
    return controller.PPUSafetyProbe(**defaults)


def test_safety_probe_reads_seals_lease_and_reload_fence_without_side_effects(tmp_path):
    probe = _probe(tmp_path)
    assert probe.active_operations() == [] and probe.seals() == [] and probe.extra_blockers() == []
    (tmp_path / "seals").mkdir()
    marker = tmp_path / "seals" / "site2.sealed"
    marker.write_text('{"site": 2}')
    (tmp_path / "seals" / "site0.sealed").write_text("{}")         # invalid Site id: ignored
    assert probe.seals() == [2] and marker.read_text() == '{"site": 2}'
    server = _lease_server(tmp_path / "control.sock", b'{"ok":true,"result":{"busy":true}}\n')
    try:
        assert probe.active_operations() == ["site-job:runtime-execution-lease"]
    finally:
        server.close()
    os.unlink(tmp_path / "control.sock")
    fence = tmp_path / "mmio.lock"
    fd = os.open(fence, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)                   # an FPGA reload holds the fence
        child = os.fork()
        if child == 0:                                   # observe from another process
            os._exit(0 if probe.active_operations() == ["fpga:reload-fence"] else 1)
        _pid, status = os.waitpid(child, 0)
        assert os.WEXITSTATUS(status) == 0
    finally:
        os.close(fd)


def test_unreadable_runtime_lease_is_a_recovery_blocker_not_idle(tmp_path):
    server = _lease_server(tmp_path / "control.sock", b"garbage\n")
    try:
        probe = _probe(tmp_path)
        assert probe.active_operations() == []
        assert probe.extra_blockers() == ["SITE_RUNTIME_LEASE_UNKNOWN"]
        engine = _engine(tmp_path, probe=probe)
        ticket = engine.engineering_arm(0.0, authorized=True)
        response = engine.claim(proto.claim_request(proto.ticket_key(ticket), engine.challenge(1.0),
                                                    controller_nonce="d" * 32, label="d"), 1.0)
        assert response["mode"] == "RECOVERY_ONLY"
        assert "SITE_RUNTIME_LEASE_UNKNOWN" in response["recovery_blockers"]
    finally:
        server.close()


def test_factory_install_ships_the_engine_and_the_sd_boot_consume_unit(tmp_path):
    installer = shim._load("plasma_lom_p2a2_installer", "ppu-bootstrap-installer.py")
    paths = installer.InstallPaths(tmp_path / "opt/plasma/bootstrap", tmp_path / "var/lib/plasma-bootstrap",
                                   tmp_path / "etc/systemd/system/plasma-bootstrap.service")
    receipt = installer.install_bootstrap(source_root=ROOT / "scripts", host="127.0.0.1", port=18081,
                                          python_executable="/usr/bin/python3", paths=paths)
    assert receipt["result"] == "PASS" and receipt["control_token_provisioned"] is False
    for name in ("ppu_controller.py", "ppu_local_enrollment.py", "ppu-enroll.py"):
        assert (paths.install_root / name).is_file()
    unit = (paths.systemd_unit.parent / "plasma-enroll-boot.service").read_text()
    assert "Before=plasma-bootstrap.service" in unit and "Type=oneshot" in unit
    assert "boot-consume --boot-partition /boot" in unit
    assert not (paths.state_root / "controller").exists()       # nothing enrolled by the factory


def test_claim_cannot_commit_a_window_destroyed_while_it_waited_for_the_fence(tmp_path):
    engine = _engine(tmp_path)
    ticket = engine.engineering_arm(0.0, authorized=True)
    request = proto.claim_request(proto.ticket_key(ticket), engine.challenge(1.0),
                                  controller_nonce="e" * 32, label="late")
    real_exclusive = engine.fence.exclusive

    def exclusive_after_lockout(timeout_s):
        engine.store.delete("pending")        # e.g. the 5th wrong proof of another client
        return real_exclusive(timeout_s)

    engine.fence.exclusive = exclusive_after_lockout
    with pytest.raises(controller.ControllerError) as exc:
        engine.claim(request, 2.0)
    assert exc.value.code == "ENROLLMENT_NOT_ARMED"
    assert engine.controller() is None
