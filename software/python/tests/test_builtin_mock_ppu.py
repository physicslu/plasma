"""Host-only: the built-in Mock PPU (Gate 1 D1-D7, M1-M3).

M1: the product launcher (plasma_server.mock_ppu) and the Bootstrap CLI paths
it needs. M2: Mock/Physical classification from the enrolled device's MACed
status, the mixed-Batch refusal, class-scoped Route resolution and the Fleet
label. M3: the Linux user-systemd unit and the --no-mock-ppu opt-out. The
live three-process stack is exercised by scripts/mock-cd.py; nothing here is
physical HIL.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from plasma_manager import bootstrap
from plasma_manager.bootstrap import (
    PPU_CLASS_MOCK, PPU_CLASS_PHYSICAL, PPU_CLASS_UNKNOWN, BootstrapCredentialError,
    BootstrapCredentialStore, ppu_class_from_status,
)
from plasma_manager.programming import ProgrammingError
from plasma_manager.programming_batch import batch_ppu_class
from plasma_opf import bundle_v3
from plasma_server import mock_ppu, mock_resources

from .test_programming_batch_targets import one, rig, with_start

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
PRODUCTION_ROUTES = ROOT / "data" / "opf" / "programming-routes"
BACKEND = ROOT / "utilities/plasmactl/backends/plasmactl-local-control-station"
TOKEN = "a" * 32
DEVICE = "ppu-device-mock-0001"


def _load_service():
    name = "plasma_test_bootstrap_service_mock"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / "ppu-bootstrap-service.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------- M1

def test_committed_mock_route_is_the_launcher_route_document() -> None:
    committed = json.loads((PRODUCTION_ROUTES / "mock-site-simulated.json").read_text())
    assert committed == mock_ppu.route_document()
    route = bundle_v3.load_route(PRODUCTION_ROUTES / "mock-site-simulated.json")
    assert route.target == mock_resources.MOCK_PLATFORM
    assert route.icpn == mock_ppu.ROUTE_ICPN


def test_provision_is_idempotent_with_a_stable_identity(tmp_path: Path) -> None:
    spec = mock_ppu.MockPPUSpec(root=tmp_path / "mock", control_plane=SCRIPTS)
    paths = mock_ppu.provision(spec)
    machine_id = paths["machine_id"].read_text()
    assert (spec.alias, spec.sites, spec.host) == ("mock-ppu-01", 8, "127.0.80.1")
    again = mock_ppu.provision(spec)
    assert again["machine_id"].read_text() == machine_id
    for key in ("package_target", "install_policy"):
        assert again[key].stat().st_mode & 0o777 == 0o600
    assert json.loads(again["package_target"].read_text()) == mock_resources.MOCK_PLATFORM
    assert paths["root"].stat().st_mode & 0o777 == 0o700
    config = json.loads(json.dumps(mock_ppu.runtime_config(spec)))
    assert [site["interface"] for site in config["sites"]] == ["mock"] * 8


def test_launcher_commands_are_the_product_processes(tmp_path: Path) -> None:
    spec = mock_ppu.MockPPUSpec(root=tmp_path / "m", control_plane=tmp_path / "plane")
    runtime = mock_ppu.runtime_command(spec)
    assert runtime[1:3] == ["-m", "plasma_server.runtime_server"]
    assert "--mock-asset-set-control-plane" in runtime
    boot = mock_ppu.bootstrap_command(spec)
    assert boot[1] == str(tmp_path / "plane" / "ppu-bootstrap-service.py")
    assert boot[boot.index("serve"):][:5] == ["serve", "--host", "127.0.80.1", "--port", "18081"]
    assert boot[-2:] == ["--mock-enrollment-ticket-file", str(spec.paths()["ticket"])]
    gateway = mock_ppu.gateway_command(spec)
    assert gateway[1:3] == ["-m", "plasma_web.gateway_phase3"]
    assert "--controller-admission-socket" in gateway
    # Nothing points back at a repository checkout.
    assert not any("scripts/mock-cd" in part for part in runtime + boot + gateway)


def test_unix_socket_path_limit_is_enforced(tmp_path: Path) -> None:
    spec = mock_ppu.MockPPUSpec(root=tmp_path / ("x" * 120), control_plane=SCRIPTS)
    with pytest.raises(mock_ppu.MockPPUError, match="too long"):
        spec.paths()
    # A long device root is fine once the sockets live in a short runtime dir.
    short = mock_ppu.MockPPUSpec(root=tmp_path / ("x" * 120), control_plane=SCRIPTS,
                                 socket_dir=Path("/run/user/1000/plasma-mock-ppu"))
    assert short.paths()["admission_socket"] == Path("/run/user/1000/plasma-mock-ppu/adm.sock")
    assert short.paths()["machine_id"].parent == tmp_path / ("x" * 120)


def test_bootstrap_cli_defaults_stay_the_z2_layout() -> None:
    service = _load_service()
    args = service._parser().parse_args(["serve", "--host", "127.0.0.1"])
    defaults = service.ServicePaths()
    for field in ("admission_socket", "runtime_control_socket", "seal_dir", "reload_fence",
                  "bundle_install_policy", "deployment_engine_script", "z2_installer_script",
                  "button_profile", "site_recovery_script"):
        assert getattr(args, field) == getattr(defaults, field)
    assert args.gateway_port == defaults.gateway_port
    assert args.mock_enrollment_ticket_file is None


def _fake_server(tmp_path: Path, platform: str, state: str = "UNENROLLED"):
    service = _load_service()
    target = tmp_path / "target.json"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump({"platform": platform, "board": "b", "fpga_part": "none"}, handle)
    armed = []
    engine = SimpleNamespace(controller_state=lambda: state,
                             engineering_arm=lambda now, authorized: armed.append(authorized) or "t" * 64)
    server = SimpleNamespace(
        bootstrap_paths=service.ServicePaths(package_target_file=target),
        engine=engine, controller_module=SimpleNamespace(boot_clock=lambda: 1.0))
    return service, server, armed


def test_mock_ticket_is_refused_on_a_non_mock_platform(tmp_path: Path) -> None:
    service, server, armed = _fake_server(tmp_path, "z2")
    with pytest.raises(service.BootstrapServiceError, match="MOCK_ENROLLMENT_REQUIRES_MOCK_PLATFORM"):
        service.arm_mock_enrollment_ticket(server, tmp_path / "ticket")
    assert armed == [] and not (tmp_path / "ticket").exists()


def test_mock_ticket_is_armed_once_while_unenrolled(tmp_path: Path) -> None:
    service, server, armed = _fake_server(tmp_path, "mock")
    ticket = tmp_path / "ticket"
    assert service.arm_mock_enrollment_ticket(server, ticket) is True
    assert ticket.read_text() == "t" * 64 and ticket.stat().st_mode & 0o777 == 0o600
    # A pending ticket is never replaced, and an enrolled Mock arms nothing.
    assert service.arm_mock_enrollment_ticket(server, ticket) is False
    ticket.unlink()
    (tmp_path / "e").mkdir()
    _service, enrolled, armed_enrolled = _fake_server(tmp_path / "e", "mock", state="NORMAL")
    assert service.arm_mock_enrollment_ticket(enrolled, ticket) is False
    assert armed == [True] and armed_enrolled == [] and not ticket.exists()


def test_register_refuses_an_alias_owned_by_another_endpoint(monkeypatch, tmp_path: Path) -> None:
    spec = mock_ppu.MockPPUSpec(root=tmp_path / "m", control_plane=SCRIPTS)
    calls = []

    def request(method, url, body=None, *, timeout=10.0):
        calls.append((method, url))
        return 200, {"ppus": [{"alias": "mock-ppu-01", "endpoint": "http://192.0.2.5:18080",
                               "lifecycle": "commissioned"}]}

    monkeypatch.setattr(mock_ppu, "_request", request)
    with pytest.raises(mock_ppu.MockPPUError, match="belongs to another endpoint"):
        mock_ppu.register_with_manager(spec, "http://127.0.0.1:18280")
    assert [method for method, _url in calls] == ["GET"]


# ------------------------------------------------------------------- M2

@pytest.mark.parametrize("payload, expected", [
    ({"target": {"platform": "mock", "board": "mock-site", "fpga_part": "none"}}, PPU_CLASS_MOCK),
    ({"target": {"platform": "pynq-z2", "board": "z2", "fpga_part": "xc7z020"}}, PPU_CLASS_PHYSICAL),
    ({"target": None}, PPU_CLASS_UNKNOWN),
    ({}, PPU_CLASS_UNKNOWN),                      # an older Bootstrap: never assumed Mock
    ({"target": {"platform": ""}}, PPU_CLASS_UNKNOWN),
])
def test_class_comes_only_from_the_trusted_target(payload, expected) -> None:
    assert ppu_class_from_status(payload) == expected


def test_class_is_bound_to_the_enrolled_device(tmp_path: Path) -> None:
    path = tmp_path / "bootstrap-credentials.json"
    store = BootstrapCredentialStore(path)
    store.set("mock-ppu-01", DEVICE, TOKEN)
    assert store.ppu_class("mock-ppu-01") == PPU_CLASS_UNKNOWN
    store.record_class("mock-ppu-01", PPU_CLASS_MOCK)
    assert store.public_state("mock-ppu-01")["ppu_class"] == PPU_CLASS_MOCK
    # A contradicting proof for the same enrollment is refused, never relabelled.
    with pytest.raises(BootstrapCredentialError, match="re-enrollment"):
        store.record_class("mock-ppu-01", PPU_CLASS_PHYSICAL)
    # unknown never overwrites a proof; an alias without credential has no class.
    store.record_class("mock-ppu-01", PPU_CLASS_UNKNOWN)
    store.record_class("ghost", PPU_CLASS_MOCK)
    assert BootstrapCredentialStore(path).ppu_class("mock-ppu-01") == PPU_CLASS_MOCK
    assert BootstrapCredentialStore(path).ppu_class("ghost") == PPU_CLASS_UNKNOWN
    # A new enrollment must prove its class again; removal forgets it.
    store.set("mock-ppu-01", DEVICE, TOKEN, generation=2)
    assert store.ppu_class("mock-ppu-01") == PPU_CLASS_UNKNOWN
    store.record_class("mock-ppu-01", PPU_CLASS_MOCK)
    store.remove("mock-ppu-01")
    assert "ppu_classes" not in json.loads(path.read_text())


def test_classification_file_stays_loadable_by_the_previous_manager(tmp_path: Path) -> None:
    """Rollback safety: classes live beside, not inside, the v2 credential records."""
    path = tmp_path / "bootstrap-credentials.json"
    store = BootstrapCredentialStore(path)
    store.set("z2", DEVICE, TOKEN, generation=7, controller_id="controller-1")
    store.record_class("z2", PPU_CLASS_PHYSICAL)
    raw = json.loads(path.read_text())
    assert raw["schema_version"] == bootstrap.BOOTSTRAP_CREDENTIAL_SCHEMA
    assert set(raw["credentials"]["z2"]) == {"device_id", "token", "updated_at", "generation",
                                             "controller_id"}
    assert raw["ppu_classes"] == {"z2": PPU_CLASS_PHYSICAL}
    # The previous loader reads exactly these records and ignores the sibling key.
    assert BootstrapCredentialStore._load(path)["z2"].generation == 7


def test_forged_classification_entries_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "bootstrap-credentials.json"
    BootstrapCredentialStore(path).set("z2", DEVICE, TOKEN)
    raw = json.loads(path.read_text())
    raw["ppu_classes"] = {"z2": "MOCK"}
    path.write_text(json.dumps(raw))
    path.chmod(0o600)
    with pytest.raises(BootstrapCredentialError, match="classification is invalid"):
        BootstrapCredentialStore(path)


@pytest.mark.parametrize("classes, expected", [
    ({"a": "mock", "b": "mock"}, "mock"),
    ({"a": "physical", "b": "physical"}, "physical"),
    ({"a": "unknown"}, "unknown"),
    ({"a": "physical", "b": "unknown"}, "unknown"),
])
def test_batch_class_of_homogeneous_targets(classes, expected) -> None:
    assert batch_ppu_class(classes) == expected


@pytest.mark.parametrize("classes", [
    {"mock-ppu-01": "mock", "z2": "physical"},
    {"mock-ppu-01": "mock", "legacy": "unknown"},   # unproven is never Mock
])
def test_mixed_mock_batch_is_refused(classes) -> None:
    with pytest.raises(ProgrammingError) as caught:
        batch_ppu_class(classes)
    assert caught.value.status == 409 and caught.value.code == "mixed_mock_physical_batch"


def _classes(workflow, mapping):
    workflow.coordinator.credentials = SimpleNamespace(
        ppu_class=lambda alias: mapping.get(alias, PPU_CLASS_UNKNOWN))


def test_mixed_batch_is_refused_before_the_start_is_consumed(tmp_path: Path) -> None:
    batches, workflow, gateways, _c = rig(tmp_path, aliases=("mock-ppu-01", "z2"))
    _classes(workflow, {"mock-ppu-01": PPU_CLASS_MOCK, "z2": PPU_CLASS_PHYSICAL})
    request = with_start(workflow, [one("mock-ppu-01", 2), one("z2", 2)])
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(request)
    assert caught.value.code == "mixed_mock_physical_batch"
    assert batches._batches == {}
    # No PPU was read, reserved or submitted to.
    assert all(not g.posts and not g.reservation_calls for g in gateways.values())
    # The same start_id stays usable for a corrected, homogeneous Batch.
    _classes(workflow, {"mock-ppu-01": PPU_CLASS_PHYSICAL, "z2": PPU_CLASS_PHYSICAL})
    accepted = batches.start_batch(request)["batch"]
    assert accepted["ppu_class"] == PPU_CLASS_PHYSICAL


def test_physical_batch_never_resolves_the_mock_route(tmp_path: Path) -> None:
    batches, workflow, _g, _c = rig(tmp_path, aliases=("z2",))
    workflow.routes_root = PRODUCTION_ROUTES       # the Physical + Mock Routes side by side
    _classes(workflow, {"z2": PPU_CLASS_PHYSICAL})
    physical = workflow.routes_for(mock=False)
    mock = workflow.routes_for(mock=True)
    assert [r.target["platform"] for r in mock] == ["mock"]
    assert "mock" not in {r.target["platform"] for r in physical}
    # Same ICPN in both, yet each class resolves exactly one Route.
    assert {r.icpn for r in mock} & {r.icpn for r in physical} == {mock_ppu.ROUTE_ICPN}
    assert workflow.list_routes("z2")["routes"] == [r.summary() for r in physical]
    _classes(workflow, {"z2": PPU_CLASS_MOCK})
    assert workflow.list_routes("z2")["routes"] == [r.summary() for r in mock]


def test_historical_batch_without_class_reads_unknown(tmp_path: Path) -> None:
    batches, workflow, _g, _c = rig(tmp_path, aliases=("z2",))
    accepted = batches.start_batch(with_start(workflow, [one("z2", 2)]))["batch"]
    record = batches._batches[accepted["batch_id"]]
    record.pop("ppu_class")                        # a journal written before M2
    view = batches.status_batch(accepted["batch_id"])["batch"]
    assert view["ppu_class"] == PPU_CLASS_UNKNOWN
    assert batches.cycle_records(accepted["batch_id"])["ppu_class"] == PPU_CLASS_UNKNOWN


def test_fleet_labels_ppus_by_enrollment_proof_not_alias(tmp_path: Path) -> None:
    from plasma_manager.bootstrap_server import BootstrapPlasmaManagerHandler

    handler = object.__new__(BootstrapPlasmaManagerHandler)
    proofs = {"mock-ppu-01": PPU_CLASS_MOCK, "z2": PPU_CLASS_PHYSICAL}
    handler._bootstrap = lambda: SimpleNamespace(credentials=SimpleNamespace(
        ppu_class=lambda alias: proofs.get(alias, PPU_CLASS_UNKNOWN)))
    snapshot = {"ok": True, "summary": {"configured_ppus": 3}, "ppus": [
        {"alias": "mock-ppu-01"}, {"alias": "z2"}, {"alias": "mock-lookalike"}]}
    fleet = handler._classified_fleet(snapshot)
    assert [p["ppu_class"] for p in fleet["ppus"]] == ["mock", "physical", "unknown"]
    assert fleet["summary"] | {} == {"configured_ppus": 3, "mock_ppus": 1, "physical_ppus": 1}
    assert "ppu_class" not in snapshot["ppus"][0]            # the poller snapshot is untouched


# ------------------------------------------------------------------- M3

UNIT_HARNESS = r"""
set -Eeuo pipefail
source "$1" help >/dev/null
root="$2"
unit_dir="$root/units"; mkdir -p "$unit_dir"
manager_unit="$unit_dir/plasma-local-manager.service"
console_unit="$unit_dir/plasma-control-station.service"
mock_ppu_unit="$unit_dir/plasma-mock-ppu.service"
state_dir="$root/state"; mock_ppu_root="$state_dir/mock-ppu"
current_link="$root/current"
mock_ppu="${MOCK:-1}"
require_command() { :; }
node() { :; }
systemctl() { printf 'SYSTEMCTL %s\n' "$*" >> "$root/events"; return "${SYSTEMCTL_RC:-0}"; }
write_units
apply_mock_ppu_enablement
"""


def _units(tmp_path: Path, mock: str, *, preexisting: bool = False):
    if preexisting:
        (tmp_path / "units").mkdir(parents=True, exist_ok=True)
        (tmp_path / "units/plasma-mock-ppu.service").write_text(
            "# Managed by Plasma local-control-station profile\nold\n")
    result = subprocess.run(
        ["bash", "-c", UNIT_HARNESS, "units", str(BACKEND), str(tmp_path)],
        capture_output=True, text=True, timeout=30, check=False,
        env={"MOCK": mock, "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    assert result.returncode == 0, result.stdout + result.stderr
    events = (tmp_path / "events").read_text() if (tmp_path / "events").exists() else ""
    return tmp_path / "units/plasma-mock-ppu.service", events


def test_default_install_writes_and_enables_the_mock_ppu_unit(tmp_path: Path) -> None:
    unit, events = _units(tmp_path, "1")
    text = unit.read_text()
    assert text.startswith("# Managed by Plasma local-control-station profile\n")
    assert (f"ExecStart={tmp_path}/current/venv/bin/python -m plasma_server.mock_ppu serve "
            f"--root {tmp_path}/state/mock-ppu --socket-dir %t/plasma-mock-ppu "
            f"--control-plane {tmp_path}/current/ppu-control-plane "
            "--alias mock-ppu-01 --sites 8 --manager-url http://127.0.0.1:18280") in text
    assert "After=plasma-local-manager.service" in text and "Restart=on-failure" in text
    assert "KillMode=mixed" in text
    assert "RuntimeDirectory=plasma-mock-ppu\nRuntimeDirectoryMode=0700" in text
    assert "SYSTEMCTL --user enable plasma-mock-ppu.service" in events


def test_no_mock_ppu_removes_the_owned_unit_and_disables_it(tmp_path: Path) -> None:
    unit, events = _units(tmp_path, "0", preexisting=True)
    assert not unit.exists()
    assert "SYSTEMCTL --user disable --now plasma-mock-ppu.service" in events
    assert "enable plasma-mock-ppu.service" not in events.replace("disable", "")


def test_backend_options_and_reserved_alias() -> None:
    script = BACKEND.read_text()
    assert "--no-mock-ppu)\n        mock_ppu=0; shift ;;" in script
    assert "PLASMA_LOCAL_CONTROL_STATION_MOCK_PPU=%q" in script
    assert 'mock_ppu="${PLASMA_LOCAL_CONTROL_STATION_MOCK_PPU:-1}"' in script
    result = subprocess.run(
        ["bash", "-c", 'source "$1" help >/dev/null; ppu_alias=mock-ppu-01; '
         'ppu_endpoint=http://127.0.0.1:18080; base_python=python3; validate_settings',
         "x", str(BACKEND)], capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode != 0 and "reserved for the built-in Mock PPU" in result.stderr


def test_release_ships_the_canonical_ppu_control_plane(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", "-c", 'source "$1" help >/dev/null; base_python="$3"; repo_root="$4"; '
         'build_release_control_plane "$2"',
         "x", str(BACKEND), str(tmp_path / "plane"), sys.executable, str(ROOT)],
        capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stderr
    installer = _load_installer()
    shipped = {str(p.relative_to(tmp_path / "plane")) for p in (tmp_path / "plane").rglob("*")
               if p.is_file()}
    assert shipped == set(installer.control_plane_files()) | {"control-plane-manifest.json"}
    assert (tmp_path / "plane/ppu-bootstrap-service.py").is_file()


def _load_installer():
    spec = importlib.util.spec_from_file_location("plasma_test_installer_mock",
                                                  SCRIPTS / "ppu-bootstrap-installer.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_one_launcher_owns_a_device_root(tmp_path: Path) -> None:
    spec = mock_ppu.MockPPUSpec(root=tmp_path / "m", control_plane=SCRIPTS)
    first, second = mock_ppu.Stack(spec), mock_ppu.Stack(spec)
    first._acquire_root()
    socket_path = spec.paths()["admission_socket"]
    with pytest.raises(mock_ppu.MockPPUError, match="another launcher"):
        second.start()
    assert second.processes == [] and not socket_path.exists()
    first.stop()
    second._acquire_root()          # released on stop: a restart may take it
    second.stop()


def test_rejected_ticket_is_discarded_and_ends_the_launcher(monkeypatch, tmp_path: Path) -> None:
    spec = mock_ppu.MockPPUSpec(root=tmp_path / "m", control_plane=SCRIPTS)
    spec.root.mkdir()
    spec.paths()["ticket"].write_text("t" * 64)

    def request(method, url, body=None, *, timeout=10.0):
        if url.endswith("/api/registry"):
            return 200, {"ppus": [{"alias": spec.alias, "endpoint": spec.gateway_url,
                                   "lifecycle": "commissioned"}]}
        if url.endswith("/bootstrap"):
            return 200, {"pairing": {"paired": False}}
        return 409, {"ok": False, "state": "ENROLLMENT_EXPIRED"}

    monkeypatch.setattr(mock_ppu, "_request", request)
    with pytest.raises(mock_ppu.EnrollmentTicketRejected):
        mock_ppu.register_with_manager(spec, "http://127.0.0.1:18280")
    assert not spec.paths()["ticket"].exists()


def test_busy_enrollment_window_does_not_crash_the_bootstrap(tmp_path: Path) -> None:
    service, server, _armed = _fake_server(tmp_path, "mock")
    controller = SimpleNamespace(ControllerError=RuntimeError, boot_clock=lambda: 1.0)

    def busy(now, authorized):
        raise RuntimeError("ENROLLMENT_BUSY")

    server.controller_module = controller
    server.engine.engineering_arm = busy
    assert service.arm_mock_enrollment_ticket(server, tmp_path / "ticket") is False
    assert not (tmp_path / "ticket").exists()


def test_status_reports_the_class_its_own_authentication_proved(tmp_path: Path) -> None:
    """No stale `unknown` from a status read that itself bound the class."""
    store = BootstrapCredentialStore(tmp_path / "bootstrap-credentials.json")
    store.set("mock-ppu-01", DEVICE, TOKEN)
    coordinator = object.__new__(bootstrap.ManagerBootstrapCoordinator)
    coordinator.credentials = store
    payload = {"bootstrap": {"state": "bootstrap_ready"},
               "target": {"platform": "mock", "board": "mock-site", "fpga_part": "none"}}

    def authenticated(alias):
        store.record_class(alias, ppu_class_from_status(payload))
        return alias, None, None, payload, DEVICE, TOKEN

    coordinator._live = lambda alias: (alias, None, None, payload, DEVICE)
    coordinator._authenticated = authenticated
    assert coordinator.status("mock-ppu-01")["pairing"]["ppu_class"] == PPU_CLASS_MOCK
