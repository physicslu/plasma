from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP_PATH = REPO_ROOT / "scripts" / "swpc-site-topology-bootstrap.py"
PLASMACTL_PATH = REPO_ROOT / "scripts" / "plasmactl"


def _load_bootstrap_module():
    spec = importlib.util.spec_from_file_location("swpc_site_topology_bootstrap", BOOTSTRAP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = _load_bootstrap_module()


def _write_config(path: Path, *, sites: list[dict] | None = None, maximum: int = 8) -> bytes:
    payload = {
        "ppu": {
            "id": "swpc-z2like-01",
            "facility_id": "lab",
            "model": "PYNQ-Z2-like",
            "display_name": "SWPC Z2-like surrogate",
        },
        "server": {
            "host": "127.0.0.1",
            "port": 9900,
            "max_supported_sites": maximum,
            "max_concurrent_jobs": 1,
            "max_queue_depth_per_site": 16,
        },
        "sites": [] if sites is None else sites,
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    path.chmod(0o640)
    return path.read_bytes()


def test_bootstrap_creates_exactly_eight_disabled_mock_sites_and_preserves_other_state(tmp_path: Path) -> None:
    config = tmp_path / "ppu.yaml"
    _write_config(config)
    before = yaml.safe_load(config.read_text(encoding="utf-8"))
    before_stat = config.stat()

    bootstrap.bootstrap_sites(config.resolve())

    after = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert after["ppu"] == before["ppu"]
    assert after["server"] == before["server"]
    assert after["sites"] == [
        {"id": site_id, "enabled": False, "interface": "mock"}
        for site_id in range(1, 9)
    ]
    after_stat = config.stat()
    assert stat.S_IMODE(after_stat.st_mode) == stat.S_IMODE(before_stat.st_mode) == 0o640
    assert after_stat.st_uid == before_stat.st_uid
    assert after_stat.st_gid == before_stat.st_gid


def test_bootstrap_refuses_non_empty_topology_without_modifying_file(tmp_path: Path) -> None:
    config = tmp_path / "ppu.yaml"
    before = _write_config(config, sites=[{"id": 1, "enabled": False, "interface": "mock"}])

    with pytest.raises(bootstrap.BootstrapError, match="already non-empty"):
        bootstrap.bootstrap_sites(config.resolve())

    assert config.read_bytes() == before


def test_bootstrap_requires_explicit_eight_site_capacity(tmp_path: Path) -> None:
    config = tmp_path / "ppu.yaml"
    before = _write_config(config, maximum=4)

    with pytest.raises(bootstrap.BootstrapError, match="max_supported_sites == 8"):
        bootstrap.bootstrap_sites(config.resolve())

    assert config.read_bytes() == before


def test_bootstrap_replace_failure_leaves_canonical_file_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "ppu.yaml"
    before = _write_config(config)

    def fail_replace(_source: str, _destination: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(bootstrap.os, "replace", fail_replace)
    with pytest.raises(bootstrap.BootstrapError, match="atomic topology bootstrap failed"):
        bootstrap.bootstrap_sites(config.resolve())

    assert config.read_bytes() == before
    assert not list(tmp_path.glob(".ppu.yaml.bootstrap.*.tmp"))


def test_bootstrap_refuses_symlink_config(tmp_path: Path) -> None:
    real_config = tmp_path / "real.yaml"
    _write_config(real_config)
    link = tmp_path / "ppu.yaml"
    link.symlink_to(real_config)

    with pytest.raises(bootstrap.BootstrapError, match="non-symlink"):
        bootstrap.bootstrap_sites(link.absolute())


def test_plasmactl_routes_bootstrap_only_to_explicit_swpc_backend(tmp_path: Path) -> None:
    fake_backend = tmp_path / "bootstrap-backend.sh"
    fake_backend.write_text("#!/usr/bin/env bash\nprintf 'BOOTSTRAP_ROUTE_OK\\n'\n", encoding="utf-8")
    fake_backend.chmod(0o755)
    env = os.environ.copy()
    env["PLASMA_SWPC_Z2LIKE_BOOTSTRAP_BACKEND"] = str(fake_backend)

    completed = subprocess.run(
        ["bash", str(PLASMACTL_PATH), "bootstrap-sites", "swpc-z2like"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "BOOTSTRAP_ROUTE_OK\n"


def test_plasmactl_rejects_bootstrap_for_other_profiles() -> None:
    completed = subprocess.run(
        ["bash", str(PLASMACTL_PATH), "bootstrap-sites", "integration"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "supports swpc-z2like only" in completed.stderr
