from __future__ import annotations

import importlib.util
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ppu-bootstrap.py"
SPEC = importlib.util.spec_from_file_location("ppu_bootstrap", SCRIPT)
assert SPEC and SPEC.loader
bootstrap = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bootstrap
SPEC.loader.exec_module(bootstrap)


def _paths(tmp_path: Path):
    product = tmp_path / "opt" / "plasma"
    state = tmp_path / "var" / "lib" / "plasma-bootstrap"
    machine = tmp_path / "etc" / "machine-id"
    machine.parent.mkdir(parents=True)
    machine.write_text("0123456789abcdef0123456789abcdef\n", encoding="utf-8")
    return bootstrap.BootstrapPaths(product, state, machine)


def _active_release(paths, *, version="1.2.3", sha="a" * 40):
    release_id = f"{version}-{sha[:12]}"
    release = paths.product_root / "releases" / release_id
    release.mkdir(parents=True)
    (release / "release.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "product": "plasma",
                "product_version": version,
                "git_sha": sha,
                "role": "ppu",
                "platform": "linux",
                "architecture": "armv7l",
                "target": "linux-armv7l",
            }
        ),
        encoding="utf-8",
    )
    paths.product_root.mkdir(parents=True, exist_ok=True)
    paths.current.symlink_to(release)
    return release_id


def test_status_is_useful_without_runtime_or_commissioned_identity(tmp_path: Path):
    paths = _paths(tmp_path)
    document = bootstrap.status_document(paths)

    assert document["bootstrap"]["state"] == "bootstrap_ready"
    assert document["runtime"] == {
        "state": "runtime_absent",
        "release_id": None,
        "product_version": None,
        "git_sha": None,
        "target": None,
        "reason": None,
    }
    assert document["identity"]["device_id"].startswith("ppu-device-")
    assert document["identity"]["ppu_id"] is None
    assert document["capabilities"] == {
        "runtime_deployment": False,
        "identity_update": False,
        "fpga_update": False,
    }
    assert document["fpga"] == {
        "pl_version": None,
        "pl_compatibility": "not_managed",
        "pl_qualification": "not_qualified",
    }


def test_machine_id_is_not_exposed_verbatim(tmp_path: Path):
    paths = _paths(tmp_path)
    document = bootstrap.status_document(paths)
    assert "0123456789abcdef" not in document["identity"]["device_id"]


def test_commissioned_identity_must_match_the_machine(tmp_path: Path):
    paths = _paths(tmp_path)
    identity = bootstrap.load_identity(paths)
    paths.state_root.mkdir(parents=True)
    paths.identity_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "device_id": identity.device_id,
                "ppu_id": "ppu-01",
                "facility_id": "lab",
                "hardware_revision": "z2-rev1",
            }
        ),
        encoding="utf-8",
    )

    loaded = bootstrap.load_identity(paths)
    assert loaded.ppu_id == "ppu-01"
    assert loaded.facility_id == "lab"
    assert loaded.hardware_revision == "z2-rev1"

    payload = json.loads(paths.identity_file.read_text(encoding="utf-8"))
    payload["device_id"] = "ppu-device-wrong"
    paths.identity_file.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(bootstrap.BootstrapError, match="does not match"):
        bootstrap.load_identity(paths)


def test_active_runtime_identity_is_observed_from_immutable_release(tmp_path: Path):
    paths = _paths(tmp_path)
    release_id = _active_release(paths)
    runtime = bootstrap.inspect_runtime(paths)
    assert runtime.state == "runtime_active"
    assert runtime.release_id == release_id
    assert runtime.product_version == "1.2.3"
    assert runtime.git_sha == "a" * 40
    assert runtime.target == "linux-armv7l"


def test_unsafe_current_path_fails_closed_to_recovery_required(tmp_path: Path):
    paths = _paths(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "release.json").write_text("{}", encoding="utf-8")
    paths.product_root.mkdir(parents=True)
    paths.current.symlink_to(outside)

    runtime = bootstrap.inspect_runtime(paths)
    assert runtime.state == "recovery_required"
    assert runtime.reason


def test_release_directory_must_match_release_identity(tmp_path: Path):
    paths = _paths(tmp_path)
    release = paths.product_root / "releases" / "wrong-directory"
    release.mkdir(parents=True)
    (release / "release.json").write_text(
        json.dumps(
            {
                "product_version": "1.0.0",
                "git_sha": "b" * 40,
                "role": "ppu",
                "target": "linux-armv7l",
            }
        ),
        encoding="utf-8",
    )
    paths.product_root.mkdir(parents=True, exist_ok=True)
    paths.current.symlink_to(release)
    runtime = bootstrap.inspect_runtime(paths)
    assert runtime.state == "recovery_required"
    assert "directory" in (runtime.reason or "")


def test_systemd_unit_keeps_bootstrap_separate_from_plasma_runtime():
    unit = bootstrap.render_systemd_unit(
        python_executable="/usr/bin/python3",
        script_path="/opt/plasma/bootstrap/ppu-bootstrap.py",
        host="192.168.2.99",
        port=18081,
    )
    assert "Plasma PPU Bootstrap / Recovery Service" in unit
    assert "ExecStart=/usr/bin/python3 /opt/plasma/bootstrap/ppu-bootstrap.py serve" in unit
    assert "plasma-server.service" not in unit
    assert "plasma-web.service" not in unit
    assert "User=root" in unit


def test_http_is_read_only_and_fail_closed(tmp_path: Path):
    paths = _paths(tmp_path)
    server = bootstrap._BootstrapHTTPServer(("127.0.0.1", 0), paths)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/v1/health", timeout=2) as response:
            health = json.loads(response.read().decode("utf-8"))
        assert health["ok"] is True
        assert health["service"] == "plasma-ppu-bootstrap"

        with urllib.request.urlopen(f"http://{host}:{port}/v1/status", timeout=2) as response:
            status = json.loads(response.read().decode("utf-8"))
        assert status["runtime"]["state"] == "runtime_absent"
        assert status["capabilities"]["runtime_deployment"] is False

        request = urllib.request.Request(
            f"http://{host}:{port}/v1/deployments",
            data=b"{}",
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(request, timeout=2)
        assert excinfo.value.code == 405
        body = json.loads(excinfo.value.read().decode("utf-8"))
        assert body["error"] == "mutation_not_enabled"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
