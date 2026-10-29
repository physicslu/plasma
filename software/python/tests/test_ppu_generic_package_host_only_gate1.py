"""#1209 revised Gate 1: one transaction engine, sandbox-only C/Python/FPGA."""
from __future__ import annotations

import base64
import fcntl
import hashlib
import importlib.util
import json
import io
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


contract = load("ppu_generic_package_contract_gate1", "ppu_unified_deployment.py")
engine = load("ppu_generic_package_engine_gate1", "ppu-bootstrap-deployment.py")
SOURCE = "a" * 40
TARGET = {"platform": "linux-armv7", "board": "pynq-z2", "fpga_part": "xc7z020clg400-1"}
SAMPLES = (
    ("wordport", "python", {
        "payload/python/wordport.py": b"# wordport engine\n",
        "payload/python/wordport.json": b"{\"mode\":\"host-only\"}",
    }),
    ("openocd-integration", "python", {"payload/python/openocd.py": b"# openocd integration\n"}),
    ("abtest", "python", {"payload/python/abtest.py": b"# A/B runner\n"}),
    ("native-bridge", "native-c", {
        "payload/bin/bridge": b"\x7fELFtest-fixture",
        "payload/lib/bridge.so": b"\x7fELFlibrary-fixture",
        "payload/include/bridge.h": b"/* interface fixture */\n",
    }),
    ("z2-identity", "fpga-image", {
        "payload/fpga/z2-identity.bit": b"host-only-image-fixture",
        "payload/fpga/z2-identity.hwh": b"host-only-handoff-fixture",
        "payload/fpga/z2-identity.json": b"{\"schema\":\"host-only-fixture\"}",
    }),
)


def package(tmp: Path, name: str, kind: str, files: dict[str, bytes], *,
            alterations: dict | None = None, names_override=None) -> tuple[Path, str]:
    entries = [{"path": filename, "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data), "executable": filename.startswith("payload/bin/")}
               for filename, data in files.items()]
    manifest = {
        "schema": contract.PACKAGE_SCHEMA, "name": name, "kind": kind,
        "version": "2026.10.29", "source_commit": SOURCE,
        "target": TARGET, "files": entries,
    }
    if kind == "fpga-image":
        manifest["fpga_pair"] = {
            "image": "payload/fpga/z2-identity.bit", "handoff": "payload/fpga/z2-identity.hwh"
        }
    if alterations:
        manifest.update(alterations)
    archive = tmp / f"{name}.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", json.dumps(manifest))
        for filename, data in files.items():
            output.writestr(filename if names_override is None else names_override, data)
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def coordinator(tmp: Path):
    paths = engine.DeploymentPaths(
        bootstrap_state_root=tmp / "isolated-bootstrap-state",
        product_root=tmp / "production-untouched", config_root=tmp / "config-untouched",
        runtime_state_root=tmp / "runtime-untouched", log_root=tmp / "log-untouched",
        systemd_root=tmp / "systemd-untouched",
    )
    return engine.DeploymentCoordinator(paths=paths, installer=SimpleNamespace(),
                                       clock=lambda: 123.0)


def request(archive: Path, digest: str):
    return engine.HostOnlyPackageRequest(archive, SOURCE, digest, TARGET)


@pytest.mark.parametrize("name,kind,files", SAMPLES)
def test_generic_host_only_transaction_stages_verifies_and_activates(
    tmp_path: Path, name: str, kind: str, files: dict[str, bytes],
) -> None:
    archive, digest = package(tmp_path, name, kind, files)
    co = coordinator(tmp_path)
    receipt = co.execute_package_host_only(request(archive, digest))
    assert receipt["result"] == "PASS"
    assert receipt["package"]["kind"] == kind
    assert receipt["transaction"]["state"] == "package_active"
    assert receipt["host_only"] is True and receipt["install_qualified"] is False
    journal = json.loads(co.paths.journal.read_text())
    assert journal["transaction_id"] == receipt["transaction"]["transaction_id"]
    assert journal["package_kind"] == kind and journal["module"] == name
    assert co.paths.journal.stat().st_mode & 0o077 == 0
    assert co.paths.lock.stat().st_mode & 0o077 == 0
    active = co.paths.bootstrap_state_root / "host-only-packages" / "active" / f"{name}.json"
    record = json.loads(active.read_text())
    stage = co.paths.bootstrap_state_root / "host-only-packages" / "releases" / name / record["release_id"]
    for relative, data in files.items():
        assert (stage / relative).read_bytes() == data
    assert not co.paths.product_root.exists()
    assert not co.paths.systemd_root.exists()


def test_generic_future_module_without_static_allowlist(tmp_path: Path) -> None:
    archive, digest = package(tmp_path, "future-parser", "native-c", {"payload/bin/parse": b"data"})
    assert coordinator(tmp_path).execute_package_host_only(request(archive, digest))["result"] == "PASS"


@pytest.mark.parametrize("kind,files", [
    ("python", {"payload/python/main.py": b"pass\n", "payload/bin/hidden": b"binary"}),
    ("python", {"payload/python/main.py": b"pass\n", "payload/fpga/hidden.bit": b"image"}),
    ("native-c", {"payload/bin/main": b"binary", "payload/python/hidden.py": b"pass\n"}),
    ("fpga-image", {
        "payload/fpga/z2-identity.bit": b"image",
        "payload/fpga/z2-identity.hwh": b"handoff",
        "payload/python/hidden.py": b"pass\n",
    }),
])
def test_package_kind_cannot_install_other_kinds_payload(
    tmp_path: Path, kind: str, files: dict[str, bytes],
) -> None:
    archive, digest = package(tmp_path, "generic", kind, files)
    with pytest.raises(engine.DeploymentError, match="PACKAGE_KIND_FILE_DENIED"):
        coordinator(tmp_path).execute_package_host_only(request(archive, digest))


def test_first_three_pilot_packages_use_real_1207_source_bytes(tmp_path: Path) -> None:
    client = load("ppu_generic_package_existing_client", "ppu_deploy.py")
    for name in client.MODULES:
        prior_manifest, legacy_bytes, swpc_files = client.build_bundle(name, SOURCE)
        assert set(prior_manifest["z2_files"]) == set(client.Z2_FILES)
        assert swpc_files
        with zipfile.ZipFile(io.BytesIO(legacy_bytes)) as archive:
            actual_sources = {
                "payload/" + relative: archive.read(relative)
                for relative in prior_manifest["z2_files"]
            }
        for relative, data in actual_sources.items():
            assert hashlib.sha256(data).hexdigest() == prior_manifest["z2_files"][relative[8:]]
        generic, digest = package(tmp_path, name, "python", actual_sources)
        result = coordinator(tmp_path / name).execute_package_host_only(request(generic, digest))
        assert result["result"] == "PASS" and result["package"]["name"] == name


@pytest.mark.parametrize("alteration,reason", [
    ({"target": {**TARGET, "board": "unknown-board"}}, "PACKAGE_MANIFEST_CONTENT_DENIED"),
    ({"source_commit": "b" * 40}, "PACKAGE_MANIFEST_CONTENT_DENIED"),
    ({"name": "../escape"}, "PACKAGE_MANIFEST_CONTENT_DENIED"),
    ({"files": [{"path": "payload/a.py", "sha256": "0"*64, "size": 3,
                  "executable": False}]}, "PACKAGE_MEMBER_MISSING"),
])
def test_host_only_rejects_incompatible_or_forged_manifest(tmp_path: Path, alteration, reason) -> None:
    archive, digest = package(tmp_path, "wordport", "python", {"payload/python/wordport.py": b"x"},
                              alterations=alteration)
    co = coordinator(tmp_path)
    with pytest.raises(engine.DeploymentError, match=reason):
        co.execute_package_host_only(request(archive, digest))
    assert json.loads(co.paths.journal.read_text())["state"] == "verify_failed"
    assert not (co.paths.bootstrap_state_root / "host-only-packages").exists()


def test_hash_mismatch_and_symlink_archive_rejected(tmp_path: Path) -> None:
    archive, digest = package(tmp_path, "wordport", "python", {"payload/python/one.py": b"x"})
    co = coordinator(tmp_path)
    with pytest.raises(engine.DeploymentError, match="PACKAGE_ARCHIVE_SHA256_MISMATCH"):
        co.execute_package_host_only(request(archive, "0" * 64))
    link = tmp_path / "link.zip"
    link.symlink_to(archive)
    with pytest.raises(engine.DeploymentError, match="PACKAGE_ARCHIVE_UNTRUSTED"):
        co.execute_package_host_only(request(link, digest))


def test_held_real_coordinator_lock_rejects_generic_package(tmp_path: Path) -> None:
    archive, digest = package(tmp_path, "wordport", "python", {"payload/python/one.py": b"x"})
    co = coordinator(tmp_path)
    co.paths.bootstrap_state_root.mkdir()
    with co.paths.lock.open("a+b") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(engine.DeploymentError, match="another PPU deployment"):
            co.execute_package_host_only(request(archive, digest))
    assert not co.paths.journal.exists()


@pytest.mark.parametrize("fault,expected", [
    ("after_stage", "rolled_back"),
    ("after_activate", "rolled_back"),
    ("rollback_unknown", "recovery_required"),
])
def test_host_only_rollback_and_unknown_recovery(tmp_path: Path, fault: str, expected: str) -> None:
    co = coordinator(tmp_path)
    archive1, digest1 = package(tmp_path, "wordport", "python", {"payload/python/one.py": b"old"})
    co.execute_package_host_only(request(archive1, digest1))
    active = co.paths.bootstrap_state_root / "host-only-packages" / "active" / "wordport.json"
    previous = active.read_bytes()
    archive2, digest2 = package(tmp_path, "wordport", "python", {"payload/python/one.py": b"new"})
    with pytest.raises(engine.DeploymentError, match="host-only package transaction failed"):
        co.execute_package_host_only(request(archive2, digest2), inject_failure=fault)
    assert json.loads(co.paths.journal.read_text())["state"] == expected
    if expected == "rolled_back":
        assert active.read_bytes() == previous
    else:
        with pytest.raises(engine.DeploymentError, match="recovery"):
            co.execute_package_host_only(request(archive1, digest1))


def test_untrusted_production_path_and_network_api_remain_disabled(tmp_path: Path) -> None:
    archive, digest = package(tmp_path, "wordport", "python", {"payload/python/one.py": b"x"})
    prod = engine.DeploymentCoordinator(paths=engine.DeploymentPaths(), installer=SimpleNamespace())
    with pytest.raises(engine.DeploymentError, match="HOST_ONLY_PRODUCTION_STATE_ROOT_DENIED"):
        prod.execute_package_host_only(request(archive, digest))
    service = load("ppu_generic_package_blocked_api", "ppu-bootstrap-service.py")
    with pytest.raises(service.BootstrapServiceError, match="ENGINEERING_INSTALL_NOT_QUALIFIED"):
        service._deployment_request({"kind": "engineering-module", "module": "wordport"})
    with pytest.raises(service.BootstrapServiceError, match="FPGA_IMAGE_INSTALL_NOT_QUALIFIED"):
        service._deployment_request({"kind": "fpga-image"})


def test_fpga_missing_handoff_never_activates(tmp_path: Path) -> None:
    archive, digest = package(tmp_path, "z2-identity", "fpga-image",
                              {"payload/fpga/z2-identity.bit": b"fixture"})
    with pytest.raises(engine.DeploymentError, match="PACKAGE_FPGA_PAIR_DENIED"):
        coordinator(tmp_path).execute_package_host_only(request(archive, digest))


def test_package_symlinked_simulated_release_tree_fails_closed(tmp_path: Path) -> None:
    archive, digest = package(tmp_path, "wordport", "python", {"payload/python/one.py": b"x"})
    co = coordinator(tmp_path)
    store = co.paths.bootstrap_state_root / "host-only-packages"
    store.mkdir(parents=True)
    (store / "releases").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(engine.DeploymentError, match="HOST_ONLY_SANDBOX_SYMLINK_DENIED"):
        co.execute_package_host_only(request(archive, digest))
    assert json.loads(co.paths.journal.read_text())["state"] == "verify_failed"


def test_reused_staged_release_rejects_symlinked_payload_parent(tmp_path: Path) -> None:
    archive, digest = package(tmp_path, "wordport", "python", {"payload/python/one.py": b"safe"})
    co = coordinator(tmp_path)
    receipt = co.execute_package_host_only(request(archive, digest))
    release = (co.paths.bootstrap_state_root / "host-only-packages" / "releases"
               / "wordport" / receipt["transaction"]["release_id"])
    code_dir = release / "payload" / "python"
    outside = tmp_path / "outside-python-files"
    code_dir.rename(outside)
    code_dir.symlink_to(outside, target_is_directory=True)
    with pytest.raises(engine.DeploymentError, match="HOST_ONLY_STAGED_SYMLINK_DENIED"):
        co.execute_package_host_only(request(archive, digest))
    assert json.loads(co.paths.journal.read_text())["state"] == "rolled_back"


def test_reused_staged_release_rejects_undeclared_file(tmp_path: Path) -> None:
    archive, digest = package(tmp_path, "wordport", "python", {"payload/python/one.py": b"safe"})
    co = coordinator(tmp_path)
    receipt = co.execute_package_host_only(request(archive, digest))
    release = (co.paths.bootstrap_state_root / "host-only-packages" / "releases"
               / "wordport" / receipt["transaction"]["release_id"])
    (release / "payload/python/hidden.py").write_bytes(b"extra")
    with pytest.raises(engine.DeploymentError, match="HOST_ONLY_STAGED_UNDECLARED_FILE"):
        co.execute_package_host_only(request(archive, digest))
    assert json.loads(co.paths.journal.read_text())["state"] == "rolled_back"


def test_unreviewed_zip_member_and_traversal_are_denied(tmp_path: Path) -> None:
    archive, digest = package(tmp_path, "module", "native-c", {"../escape": b"x"})
    with pytest.raises(engine.DeploymentError, match="PACKAGE_FILE_SET_DENIED"):
        coordinator(tmp_path).execute_package_host_only(request(archive, digest))


def test_duplicate_manifest_key_and_symlink_payload_fail_closed(tmp_path: Path) -> None:
    manifest = (
        '{"schema":"plasma.ppu.package.v1","name":"wordport",'
        '"name":"forged","kind":"python","version":"v1",'
        '"source_commit":"' + SOURCE + '",'
        '"target":' + json.dumps(TARGET) + ',"files":[]}'
    )
    archive = tmp_path / "duplicate-key.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", manifest)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(engine.DeploymentError, match="PACKAGE_DUPLICATE_JSON_KEY"):
        coordinator(tmp_path).execute_package_host_only(request(archive, digest))

    link = zipfile.ZipInfo("payload/python/wordport.py")
    link.create_system = 3
    link.external_attr = (0o120777 << 16)
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", "{}")
        output.writestr(link, b"target")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(engine.DeploymentError, match="PACKAGE_FILE_SET_DENIED"):
        coordinator(tmp_path).execute_package_host_only(request(archive, digest))


def test_no_extra_adapter_or_second_transaction_persistence() -> None:
    source = (ROOT / "scripts" / "ppu-bootstrap-deployment.py").read_text()
    assert source.count("def _deployment_lock(") == 1
    assert source.count("class Journal:") == 1
    assert source.count("class DeploymentCoordinator:") == 1
    assert "def execute_package_host_only(" in source
    assert "subprocess.run(" not in source


def test_real_bootstrap_chunk_upload_to_same_coordinator_host_only_sandbox(tmp_path: Path) -> None:
    """Existing upload bytes -> ZIP verifier -> one Coordinator; never live API admission."""
    service = load("ppu_channel_real_upload_service_gate1", "ppu-bootstrap-service.py")
    for name, kind, files in SAMPLES:
        isolated = tmp_path / name
        isolated.mkdir()
        archive, digest = package(isolated, name, kind, files)
        payload = archive.read_bytes()
        paths = service.ServicePaths(
            product_root=isolated / "product-untouched",
            state_root=isolated / "bootstrap-state",
        )
        opened = service.create_upload(paths, size=len(payload), sha256=digest)
        upload_id = opened["upload_id"]
        midpoint = max(1, len(payload) // 2)
        offset = 0
        for chunk in (payload[:midpoint], payload[midpoint:]):
            if not chunk:
                continue
            receipt = service.append_chunk(
                paths, upload_id, offset=offset,
                data_base64=base64.b64encode(chunk).decode("ascii"),
                sha256=hashlib.sha256(chunk).hexdigest(),
            )
            offset += len(chunk)
            assert receipt["received_bytes"] == offset
        committed = service.commit_upload(paths, upload_id)
        assert committed["state"] == "committed"
        # Bootstrap currently names every uploaded archive .tar.gz, regardless
        # of actual ZIP bytes. The runtime kit installer must NOT receive it.
        stored = service._upload_paths(paths, upload_id).committed
        assert stored.read_bytes() == payload
        assert zipfile.is_zipfile(stored)
        co = coordinator(isolated)
        result = co.execute_package_host_only(request(stored, digest))
        assert result["result"] == "PASS"
        assert result["package"]["kind"] == kind
        assert result["install_qualified"] is False
        assert not paths.product_root.exists()
        assert not co.paths.product_root.exists()
        # The live request parser still fails closed for engineering and FPGA.
        blocked_kind = "fpga-image" if kind == "fpga-image" else "engineering-module"
        with pytest.raises(service.BootstrapServiceError, match="INSTALL_NOT_QUALIFIED"):
            service._deployment_request({"kind": blocked_kind, "upload_id": upload_id})


def test_chunk_upload_rejects_tamper_before_host_only_install(tmp_path: Path) -> None:
    service = load("ppu_channel_upload_tamper_gate1", "ppu-bootstrap-service.py")
    archive, digest = package(tmp_path, "wordport", "python", {"payload/python/main.py": b"pass\\n"})
    payload = archive.read_bytes()
    paths = service.ServicePaths(state_root=tmp_path / "bootstrap-state")
    opened = service.create_upload(paths, size=len(payload), sha256=digest)
    upload_id = opened["upload_id"]
    with pytest.raises(service.BootstrapServiceError, match="SHA-256 mismatch"):
        service.append_chunk(paths, upload_id, offset=0,
                             data_base64=base64.b64encode(payload).decode("ascii"),
                             sha256="0" * 64)
    with pytest.raises(service.BootstrapServiceError, match="incomplete"):
        service.commit_upload(paths, upload_id)
    assert not service._upload_paths(paths, upload_id).committed.exists()


def test_generic_zip_cannot_reach_legacy_runtime_installer(tmp_path: Path) -> None:
    """Runtime dispatch must fail before invoking the PS tar.gz kit installer."""
    service = load("ppu_channel_runtime_zip_guard_gate1", "ppu-bootstrap-service.py")
    archive, digest = package(tmp_path, "wordport", "python", {"payload/python/main.py": b"pass\\n"})
    payload = archive.read_bytes()
    kit = tmp_path / "kit-present-but-must-not-execute.py"
    kit.write_text("raise AssertionError('legacy installer invoked')\\n")
    paths = service.ServicePaths(state_root=tmp_path / "state", kit_tool=kit)
    upload_id = service.create_upload(paths, size=len(payload), sha256=digest)["upload_id"]
    service.append_chunk(paths, upload_id, offset=0,
                         data_base64=base64.b64encode(payload).decode("ascii"),
                         sha256=digest)
    service.commit_upload(paths, upload_id)
    with pytest.raises(service.BootstrapServiceError, match="GENERIC_PACKAGE_RUNTIME_INSTALLER_DENIED"):
        service.run_deployment_subprocess(paths, upload_id, {
            "api_transaction_id": "a" * 32,
        })
    assert not paths.product_root.exists()


def test_host_only_package_journal_correlates_bootstrap_api_transaction(tmp_path: Path) -> None:
    archive, digest = package(tmp_path, "wordport", "python", {"payload/python/main.py": b"pass\\n"})
    co = coordinator(tmp_path)
    tx = "b" * 32
    req = engine.HostOnlyPackageRequest(archive, SOURCE, digest, TARGET, api_transaction_id=tx)
    receipt = co.execute_package_host_only(req)
    assert receipt["result"] == "PASS"
    journal = json.loads(co.paths.journal.read_text())
    assert journal["api_transaction_id"] == tx
    assert journal["transaction_id"] == receipt["transaction"]["transaction_id"]
    assert journal["kind"] == "host-only-package"
    assert not co.paths.product_root.exists()


@pytest.mark.parametrize("invalid", ["", "not-a-transaction", "0" * 31, "Z" * 32, 123])
def test_invalid_host_only_api_transaction_fails_before_journal(tmp_path: Path, invalid) -> None:
    archive, digest = package(tmp_path, "wordport", "python", {"payload/python/main.py": b"pass\\n"})
    co = coordinator(tmp_path)
    req = engine.HostOnlyPackageRequest(archive, SOURCE, digest, TARGET, api_transaction_id=invalid)
    with pytest.raises(engine.DeploymentError, match="HOST_ONLY_API_TRANSACTION_ID_INVALID"):
        co.execute_package_host_only(req)
    assert not co.paths.journal.exists()


def test_corrupt_archive_never_reaches_runtime_installer(tmp_path: Path) -> None:
    service = load("ppu_channel_invalid_archive_gate1", "ppu-bootstrap-service.py")
    payload = b"not-a-tar-and-not-a-zip" * 3
    digest = hashlib.sha256(payload).hexdigest()
    kit = tmp_path / "kit-present-but-must-not-execute.py"
    kit.write_text("raise AssertionError('legacy installer invoked')\\n")
    paths = service.ServicePaths(state_root=tmp_path / "state", kit_tool=kit)
    upload_id = service.create_upload(paths, size=len(payload), sha256=digest)["upload_id"]
    service.append_chunk(paths, upload_id, offset=0,
                         data_base64=base64.b64encode(payload).decode("ascii"), sha256=digest)
    service.commit_upload(paths, upload_id)
    with pytest.raises(service.BootstrapServiceError, match="RUNTIME_ARCHIVE_FORMAT_INVALID"):
        service.run_deployment_subprocess(paths, upload_id, {"api_transaction_id": "a" * 32})
    assert not paths.product_root.exists()


@pytest.mark.parametrize("bad_path", [None, 123, [], {}, True])
def test_generic_manifest_non_string_path_fails_closed(tmp_path: Path, bad_path) -> None:
    archive, _ = package(tmp_path, "wordport", "python",
                         {"payload/python/main.py": b"pass\\n"})
    with zipfile.ZipFile(archive, "r") as source:
        manifest = json.loads(source.read("manifest.json"))
        payload = source.read("payload/python/main.py")
    manifest["files"][0]["path"] = bad_path
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", json.dumps(manifest))
        output.writestr("payload/python/main.py", payload)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(contract.UnifiedDeploymentError, match="PACKAGE_FILE_METADATA_DENIED"):
        contract.verify_host_only_package(archive, expected_sha256=digest,
                                          source_commit=SOURCE, target_profile=TARGET)


@pytest.mark.parametrize("field,bad_value", [("image", None), ("image", []),
                                              ("image", 123), ("handoff", {}),
                                              ("handoff", True)])
def test_generic_fpga_pair_rejects_non_string_members(
    tmp_path: Path, field: str, bad_value,
) -> None:
    files = {"payload/fpga/z2-identity.bit": b"image",
             "payload/fpga/z2-identity.hwh": b"handoff"}
    archive, digest = package(tmp_path, "z2-identity", "fpga-image", files,
                              alterations={"fpga_pair": {
                                  "image": "payload/fpga/z2-identity.bit",
                                  "handoff": "payload/fpga/z2-identity.hwh",
                              }})
    with zipfile.ZipFile(archive) as source:
        manifest = json.loads(source.read("manifest.json"))
    manifest["fpga_pair"][field] = bad_value
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", json.dumps(manifest))
        for name, data in files.items():
            output.writestr(name, data)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(contract.UnifiedDeploymentError, match="PACKAGE_FPGA_PAIR_DENIED"):
        contract.verify_host_only_package(archive, expected_sha256=digest,
                                          source_commit=SOURCE, target_profile=TARGET)
