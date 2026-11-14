from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tarfile
import types
import zipfile
from pathlib import Path

import pytest

from .ppu_control_plane_fixture import write_control_plane

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ppu-z2-installer.py"
spec = importlib.util.spec_from_file_location("ppu_z2_installer", SCRIPT)
assert spec is not None and spec.loader is not None
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _fake_release(
    root: Path,
    *,
    hardware_boundary: dict[str, bool] | None = None,
    symlink_member: bool = False,
    legacy_catalog_data: bool = False,
    control_plane: bool = True,
) -> Path:
    bundle = root / "bundle" / "plasma-release"
    runtime = bundle / "runtime"
    app = runtime / "ppu" / "ppu.pyz"
    app.parent.mkdir(parents=True)

    with zipfile.ZipFile(app, "w") as archive:
        archive.writestr("__main__.py", "print('ok')\n")

    # OPF S5 / PR-C1: a current PPU runtime carries no Catalog / IC Support.
    runtime_manifest: dict[str, object] = {
        "schema_version": 1,
        "role": "ppu",
        "hardware_boundary": hardware_boundary
        if hardware_boundary is not None
        else dict(installer.EXPECTED_HARDWARE_BOUNDARY),
    }
    if control_plane:
        runtime_manifest["control_plane"] = write_control_plane(runtime)
    if legacy_catalog_data:
        # Pre-PR-C1 release layout: shipped Catalog data is tolerated, never required.
        catalog = runtime / "data" / "device-catalog" / "production" / "icpn-v1-manifest.json"
        catalog.parent.mkdir(parents=True)
        catalog.write_text('{"schema_version":1}\n', encoding="utf-8")
        (runtime / "data" / "ic-support" / "profiles").mkdir(parents=True)
        runtime_manifest["data"] = {
            "device_catalog_manifest": "data/device-catalog/production/icpn-v1-manifest.json",
            "ic_support_root": "data/ic-support",
        }
    (runtime / "ppu-runtime.json").write_text(
        json.dumps(runtime_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    release_manifest = {
        "schema_version": 1,
        "product": "plasma",
        "product_version": "0.1.0",
        "git_sha": "a" * 40,
        "role": "ppu",
        "platform": "linux",
        "architecture": "armv7l",
        "target": "linux-armv7l",
        "build_timestamp": "2026-09-06T00:00:00Z",
        "archive_format": "tar.gz",
        "contracts": {"plasma_protocol": "3.3", "web_rest_api": "3"},
        "components": {"python": "0.3.2"},
        "layout": {"runtime": "runtime", "config_defaults": "config/defaults"},
    }
    (bundle / "release.json").write_text(
        json.dumps(release_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if symlink_member:
        (runtime / "bad-link").symlink_to("ppu/ppu.pyz")

    files = sorted(
        path for path in bundle.rglob("*") if path.is_file() and not path.is_symlink()
    )
    (bundle / "SHA256SUMS").write_text(
        "".join(
            f"{_sha256(path)}  {path.relative_to(bundle).as_posix()}\n" for path in files
        ),
        encoding="utf-8",
    )

    artifact = root / "plasma-ppu-0.1.0-linux-armv7l.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        archive.add(bundle, arcname="plasma-release", recursive=True)
    Path(str(artifact) + ".sha256").write_text(
        f"{_sha256(artifact)}  {artifact.name}\n",
        encoding="utf-8",
    )
    return artifact


def test_release_verifier_accepts_canonical_ps_only_bundle(tmp_path: Path) -> None:
    artifact = _fake_release(tmp_path)
    verified = installer.verify_release(
        artifact,
        extract_to=tmp_path / "verified",
    )
    assert verified.product_version == "0.1.0"
    assert verified.git_sha == "a" * 40
    assert verified.release_id == "0.1.0-aaaaaaaaaaaa"
    assert verified.runtime_manifest["hardware_boundary"] == installer.EXPECTED_HARDWARE_BOUNDARY


def test_release_verifier_requires_no_catalog_and_tolerates_legacy_catalog(tmp_path: Path) -> None:
    current = installer.verify_release(_fake_release(tmp_path / "current"),
                                       extract_to=tmp_path / "current-verified")
    assert "data" not in current.runtime_manifest
    assert not (tmp_path / "current-verified" / "plasma-release" / "runtime" / "data").exists()
    legacy = installer.verify_release(_fake_release(tmp_path / "legacy", legacy_catalog_data=True),
                                      extract_to=tmp_path / "legacy-verified")
    assert legacy.runtime_manifest["data"]["ic_support_root"] == "data/ic-support"


def test_release_verifier_rejects_tampered_archive_sidecar(tmp_path: Path) -> None:
    artifact = _fake_release(tmp_path)
    Path(str(artifact) + ".sha256").write_text(
        f"{'0' * 64}  {artifact.name}\n",
        encoding="utf-8",
    )
    with pytest.raises(installer.Z2InstallerError, match="does not match"):
        installer.verify_release(artifact, extract_to=tmp_path / "verified")


def test_release_verifier_rejects_non_regular_tar_member(tmp_path: Path) -> None:
    artifact = _fake_release(tmp_path, symlink_member=True)
    with pytest.raises(installer.Z2InstallerError, match="non-regular"):
        installer.verify_release(artifact, extract_to=tmp_path / "verified")


def test_release_verifier_rejects_open_hardware_boundary(tmp_path: Path) -> None:
    boundary = dict(installer.EXPECTED_HARDWARE_BOUNDARY)
    boundary["accesses_pl"] = True
    artifact = _fake_release(tmp_path, hardware_boundary=boundary)
    with pytest.raises(installer.Z2InstallerError, match="hardware boundary is not closed"):
        installer.verify_release(artifact, extract_to=tmp_path / "verified")


def test_isolated_python_must_be_plasma_owned_armv7_final_and_311_or_newer(tmp_path: Path) -> None:
    product_root = tmp_path / "opt" / "plasma"
    python_path = product_root / "python" / "3.11.9" / "bin" / "python3"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("placeholder\n", encoding="utf-8")
    python_path.chmod(0o755)

    runtime = installer.validate_plasma_python(
        python_path,
        product_root=product_root,
        probe=lambda path: {
            "version": [3, 11, 9],
            "releaselevel": "final",
            "machine": "armv7l",
            "executable": str(path),
        },
    )
    assert runtime.version == "3.11.9"
    assert runtime.architecture == "armv7l"
    assert runtime.releaselevel == "final"

    with pytest.raises(installer.Z2InstallerError, match="required 3.11"):
        installer.validate_plasma_python(
            python_path,
            product_root=product_root,
            probe=lambda path: {
                "version": [3, 10, 4],
                "releaselevel": "final",
                "machine": "armv7l",
                "executable": str(path),
            },
        )

    with pytest.raises(installer.Z2InstallerError, match="final release"):
        installer.validate_plasma_python(
            python_path,
            product_root=product_root,
            probe=lambda path: {
                "version": [3, 11, 0],
                "releaselevel": "candidate",
                "machine": "armv7l",
                "executable": str(path),
            },
        )

    outside = tmp_path / "usr" / "bin" / "python3"
    outside.parent.mkdir(parents=True)
    outside.write_text("placeholder\n", encoding="utf-8")
    outside.chmod(0o755)
    with pytest.raises(installer.Z2InstallerError, match="must live under"):
        installer.validate_plasma_python(
            outside,
            product_root=product_root,
            probe=lambda path: {
                "version": [3, 12, 0],
                "releaselevel": "final",
                "machine": "armv7l",
                "executable": str(path),
            },
        )


def test_systemd_units_bind_absolute_isolated_python_and_keep_ps_only_boundary(tmp_path: Path) -> None:
    paths = installer.InstallPaths(
        product_root=tmp_path / "opt" / "plasma",
        config_root=tmp_path / "etc" / "plasma",
        state_root=tmp_path / "var" / "lib" / "plasma",
        log_root=tmp_path / "var" / "log" / "plasma",
        systemd_root=tmp_path / "etc" / "systemd" / "system",
    )
    python_path = paths.product_root / "python" / "3.11.9" / "bin" / "python3"
    runtime = installer.PythonRuntime(python_path, "3.11.9", "armv7l")
    units = installer.render_systemd_units(
        paths=paths,
        python_runtime=runtime,
        gateway_host="192.168.2.99",
    )
    server = units["plasma-server.service"]
    gateway = units["plasma-web.service"]
    assert f"ExecStart={python_path}" in server
    assert f"ExecStart={python_path}" in gateway
    assert "/usr/bin/python3" not in server + gateway
    assert "--host 192.168.2.99 --port 18080" in gateway
    assert "--plasma-host 127.0.0.1 --plasma-port 9900" in gateway
    assert "NoNewPrivileges=true" in server
    assert "ProtectSystem=strict" in server

    config = installer.render_ppu_config(
        ppu_id="z2-dev-01",
        facility_id="lab",
        display_name="Plasma Z2 PS",
        state_root=paths.state_root,
        log_root=paths.log_root,
    )
    assert "sites: []" not in config
    assert "max_supported_sites: 8" in config
    # OPF S5 / PR-C1: no Catalog environment is configured for PPU services.
    for unit in (server, gateway):
        assert "PLASMA_IC_SUPPORT_ROOT" not in unit
        assert "PLASMA_DEVICE_CATALOG_MANIFEST" not in unit
        assert "device-catalog" not in unit and "ic-support" not in unit


def test_gateway_bind_is_explicit_and_not_wildcard() -> None:
    assert installer._validate_gateway_host("192.168.2.99") == "192.168.2.99"
    for value in ("0.0.0.0", "127.0.0.1", "not-an-address"):
        with pytest.raises(installer.Z2InstallerError):
            installer._validate_gateway_host(value)


def test_local_health_probe_is_explicitly_proxy_free() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "ProxyHandler({})" in source
    assert "build_opener" in source


def test_failed_activation_restores_previous_release_config_and_units(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = _fake_release(tmp_path)
    verified = installer.verify_release(artifact, extract_to=tmp_path / "verified")
    paths = installer.InstallPaths(
        product_root=tmp_path / "opt" / "plasma",
        config_root=tmp_path / "etc" / "plasma",
        state_root=tmp_path / "var" / "lib" / "plasma",
        log_root=tmp_path / "var" / "log" / "plasma",
        systemd_root=tmp_path / "etc" / "systemd" / "system",
    )
    previous = paths.releases_root / "0.0.9-previous"
    previous.mkdir(parents=True)
    paths.current.parent.mkdir(parents=True, exist_ok=True)
    paths.current.symlink_to(previous)

    old_config = "old-config\n"
    old_server = "old-server-unit\n"
    old_gateway = "old-gateway-unit\n"
    paths.config_root.mkdir(parents=True)
    paths.systemd_root.mkdir(parents=True)
    (paths.config_root / "ppu.yaml").write_text(old_config, encoding="utf-8")
    (paths.systemd_root / "plasma-server.service").write_text(old_server, encoding="utf-8")
    (paths.systemd_root / "plasma-web.service").write_text(old_gateway, encoding="utf-8")

    monkeypatch.setattr(installer, "_chown_tree", lambda *args: None)
    monkeypatch.setattr(installer.os, "chown", lambda *args: None)
    monkeypatch.setattr(
        installer.pwd,
        "getpwnam",
        lambda name: types.SimpleNamespace(pw_uid=1001, pw_gid=1001),
    )
    monkeypatch.setattr(
        installer.grp,
        "getgrnam",
        lambda name: types.SimpleNamespace(gr_gid=1001),
    )

    calls: list[tuple[str, ...]] = []

    def fake_systemctl(*args: str) -> None:
        calls.append(args)

    def failed_health(host: str) -> dict[str, object]:
        raise installer.Z2InstallerError("synthetic readiness failure")

    runtime = installer.PythonRuntime(
        paths.product_root / "python" / "3.11.9" / "bin" / "python3",
        "3.11.9",
        "armv7l",
    )
    with pytest.raises(installer.Z2InstallerError, match="previous configuration/release was restored"):
        installer.install_release(
            verified,
            python_runtime=runtime,
            gateway_host="192.168.2.99",
            paths=paths,
            ppu_id="z2-dev-01",
            facility_id="lab",
            display_name="Plasma Z2 PS",
            systemctl=fake_systemctl,
            health_check=failed_health,
            ensure_service_account=lambda: None,
        )

    assert paths.current.resolve() == previous.resolve()
    assert (paths.config_root / "ppu.yaml").read_text(encoding="utf-8") == old_config
    assert (paths.systemd_root / "plasma-server.service").read_text(encoding="utf-8") == old_server
    assert (paths.systemd_root / "plasma-web.service").read_text(encoding="utf-8") == old_gateway
    assert ("daemon-reload",) in calls
    assert ("restart", "plasma-server.service") in calls
    assert ("restart", "plasma-web.service") in calls


def test_first_install_failure_removes_candidate_managed_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = _fake_release(tmp_path)
    verified = installer.verify_release(artifact, extract_to=tmp_path / "verified")
    paths = installer.InstallPaths(
        product_root=tmp_path / "opt" / "plasma",
        config_root=tmp_path / "etc" / "plasma",
        state_root=tmp_path / "var" / "lib" / "plasma",
        log_root=tmp_path / "var" / "log" / "plasma",
        systemd_root=tmp_path / "etc" / "systemd" / "system",
    )
    monkeypatch.setattr(installer, "_chown_tree", lambda *args: None)
    monkeypatch.setattr(installer.os, "chown", lambda *args: None)
    monkeypatch.setattr(
        installer.pwd,
        "getpwnam",
        lambda name: types.SimpleNamespace(pw_uid=1001, pw_gid=1001),
    )
    monkeypatch.setattr(
        installer.grp,
        "getgrnam",
        lambda name: types.SimpleNamespace(gr_gid=1001),
    )
    calls: list[tuple[str, ...]] = []

    with pytest.raises(installer.Z2InstallerError, match="restored"):
        installer.install_release(
            verified,
            python_runtime=installer.PythonRuntime(
                paths.product_root / "python" / "3.11.9" / "bin" / "python3",
                "3.11.9",
                "armv7l",
            ),
            gateway_host="192.168.2.99",
            paths=paths,
            ppu_id="z2-dev-01",
            facility_id="lab",
            display_name="Plasma Z2 PS",
            systemctl=lambda *args: calls.append(args),
            health_check=lambda host: (_ for _ in ()).throw(
                installer.Z2InstallerError("synthetic readiness failure")
            ),
            ensure_service_account=lambda: None,
        )

    assert not paths.current.exists() and not paths.current.is_symlink()
    assert not (paths.config_root / "ppu.yaml").exists()
    assert not (paths.systemd_root / "plasma-server.service").exists()
    assert not (paths.systemd_root / "plasma-web.service").exists()
    assert ("disable", "--now", "plasma-web.service") in calls
    assert ("disable", "--now", "plasma-server.service") in calls


def test_bootstrap_source_does_not_import_project_or_python311_only_tomllib() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "tomllib" not in source
    assert "plasma_" not in "\n".join(
        line for line in source.splitlines() if line.startswith("import ") or line.startswith("from ")
    )
    assert "--plasma-python" in source
    assert "release >= 3.11" in source
    assert "releaselevel" in source


def test_rendered_config_lists_every_supported_site_disabled(tmp_path: Path) -> None:
    # The Python 3.10 installer-only CI job runs without the Plasma package;
    # the full suite (Python >= 3.11) validates with the real config loader.
    try:
        from plasma_core.config import load_config
    except ImportError as exc:  # Python 3.10 bootstrap job: no Plasma package
        pytest.skip(f"Plasma config loader unavailable: {exc}")

    config_path = tmp_path / "ppu.yaml"
    config_path.write_text(
        installer.render_ppu_config(
            ppu_id="z2-dev-01",
            facility_id="lab",
            display_name="Plasma Z2 PS",
            state_root=tmp_path / "state",
            log_root=tmp_path / "log",
        ),
        encoding="utf-8",
    )
    config = load_config(config_path)
    config.validate()
    assert [site.id for site in config.sites] == list(range(1, 9))
    assert all(site.enabled is False for site in config.sites)
    assert {site.interface for site in config.sites} == {"mock"}
    # No product default ICPN: the exact target is an explicit operator choice.
    assert {site.target for site in config.sites} == {None}
    assert "STM32" not in (tmp_path / "ppu.yaml").read_text()


def test_install_refreshes_only_already_installed_stage_c_units_with_plasma_python(tmp_path):
    paths = _install_paths(tmp_path)
    runtime = installer.PythonRuntime(path=Path("/opt/plasma/python/9.8.7/bin/python3"),
                                      version="9.8.7", architecture="armv7l",
                                      releaselevel="final")
    # Stage C not enabled: an install creates nothing.
    assert installer.render_stage_c_refresh(paths=paths, python_runtime=runtime) == []
    paths.systemd_root.mkdir(parents=True)
    paths.config_root.mkdir(parents=True)
    for name in ("plasma-site-worker.service", "plasma-package@.service"):
        (paths.systemd_root / name).write_text("ExecStart=/opt/plasma/python/3.12.13/bin/python3 x\n")
    (paths.config_root / "ppu-package-actions.json").write_text(
        '{"site_worker_control_socket": "/run/plasma-site-worker/control.sock"}')
    out = {path.name: text for path, text, _mode in
           installer.render_stage_c_refresh(paths=paths, python_runtime=runtime)}
    assert set(out) == {"plasma-site-worker.service", "plasma-package@.service",
                        "ppu-package-actions.json"}  # helper unit absent -> not created
    assert all("/opt/plasma/python/9.8.7/bin/python3" in text for text in out.values())
    assert all("3.12.13" not in text for text in out.values())
    assert '"site_worker_control_socket": "/run/plasma-site-worker/control.sock"' in out[
        "ppu-package-actions.json"]


def _install_paths(tmp_path: Path):
    return installer.InstallPaths(
        product_root=tmp_path / "opt" / "plasma",
        config_root=tmp_path / "etc" / "plasma",
        state_root=tmp_path / "var" / "lib" / "plasma",
        log_root=tmp_path / "var" / "log" / "plasma",
        systemd_root=tmp_path / "etc" / "systemd" / "system",
    )


def _run_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, paths) -> list[tuple[str, ...]]:
    artifact = _fake_release(tmp_path)
    verified = installer.verify_release(artifact, extract_to=tmp_path / "verified")
    monkeypatch.setattr(installer, "_chown_tree", lambda *args: None)
    monkeypatch.setattr(installer.os, "chown", lambda *args: None)
    monkeypatch.setattr(installer.pwd, "getpwnam", lambda name: types.SimpleNamespace(pw_uid=1001, pw_gid=1001))
    monkeypatch.setattr(installer.grp, "getgrnam", lambda name: types.SimpleNamespace(gr_gid=1001))
    calls: list[tuple[str, ...]] = []
    installer.install_release(
        verified,
        python_runtime=installer.PythonRuntime(
            paths.product_root / "python" / "3.12.13" / "bin" / "python3", "3.12.13", "armv7l"
        ),
        gateway_host="192.168.2.99",
        paths=paths,
        ppu_id="z2-dev-01",
        facility_id="lab",
        display_name="Plasma Z2 PS",
        systemctl=lambda *args: calls.append(args),
        health_check=lambda host: {"gateway": "alive", "execution": "ready"},
        ensure_service_account=lambda: None,
    )
    return calls


def test_upgrade_restarts_running_services_and_migrates_legacy_empty_sites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _install_paths(tmp_path)
    previous = paths.releases_root / "0.0.9-previous"
    previous.mkdir(parents=True)
    paths.current.symlink_to(previous)
    paths.config_root.mkdir(parents=True)
    legacy = installer.render_ppu_config(
        ppu_id="kept-id", facility_id="lab", display_name="Kept",
        state_root=paths.state_root, log_root=paths.log_root,
    ).replace(installer.render_default_sites(), "sites: []\n")
    assert "sites: []\n" in legacy
    (paths.config_root / "ppu.yaml").write_text(legacy, encoding="utf-8")

    calls = _run_install(tmp_path, monkeypatch, paths)

    enable = calls.index(("enable", "--now", "plasma-web.service"))
    assert calls[enable + 1:enable + 3] == [("restart", "plasma-server.service"), ("restart", "plasma-web.service")]
    migrated = (paths.config_root / "ppu.yaml").read_text(encoding="utf-8")
    assert "sites: []" not in migrated
    assert 'id: "kept-id"' in migrated  # identity preserved, not re-rendered
    evidence = json.loads((paths.install_root / "last-install.json").read_text(encoding="utf-8"))
    assert evidence["site_desired_state"]["empty_sites_migrated_to_defaults"] is True


def test_fresh_install_does_not_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _run_install(tmp_path, monkeypatch, _install_paths(tmp_path))
    assert ("enable", "--now", "plasma-server.service") in calls
    assert not [call for call in calls if call[0] == "restart"]


@pytest.mark.parametrize(
    "content",
    [
        "sites:\n  - {id: 2, enabled: true, interface: openocd, target: STM32F103C8T6}\n",
        "sites: []\nsites: []\n",
        "  sites: []\n",
        "sites: [] # operator\n",
    ],
)
def test_empty_sites_migration_only_touches_the_exact_legacy_line(content: str) -> None:
    assert installer.migrate_empty_sites(content.encode()) is None


def test_empty_sites_migration_replaces_exact_legacy_line() -> None:
    migrated = installer.migrate_empty_sites(b"ppu:\n  id: a\n\nsites: []\n")
    assert migrated is not None
    assert migrated.startswith("ppu:\n  id: a\n\nsites:\n  - {id: 1, enabled: false")
    assert migrated.count("enabled: false") == 8
