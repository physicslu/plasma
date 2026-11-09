"""Host-only Bundle v3 FPGA admission and owner authorization tests."""
from __future__ import annotations

import base64
import hashlib
import json
import threading
from pathlib import Path

import pytest

from .ppu_owner_authorization_fixture import admit_body, install_body, machine_id_file
from .ppu_fpga_qualification_fixture import synthetic_image
from .test_ppu_bundle_v3_packages_contract import ROOT, TARGET, bundle_v3, contract, load
from .test_ppu_package_receive_admission_pr1 import TOKEN, client, loopback  # noqa: F401
from .bootstrap_request_auth_fixture import signed_call

qualification = load("ppu_fpga_static_qualification_test", "ppu_fpga_qualification.py")
bootstrap = load("ppu_fpga_static_qualification_service", "ppu-bootstrap-service.py")


def fpga_bundle(tmp_path, files=None, *, mutate=None):
    files = synthetic_image()[0] if files is None else files
    return bundle_v3(tmp_path, parts=[("swd-image", "fpga-image", [], files)], mutate=mutate)


def qualify(tmp_path, archive, digest, *, target=TARGET):
    verified = contract.verify_host_only_artifact(
        archive, expected_sha256=digest, target_profile=target)
    return qualification.qualify_bundle_fpga(archive, verified, trusted_target=target)


def deny(code, tmp_path, archive, digest, **kw):
    with pytest.raises(qualification.FpgaQualificationDenied, match=code):
        qualify(tmp_path, archive, digest, **kw)


def _with_manifest(tmp_path, overrides, *, bin_bytes=None):
    files, _ = synthetic_image(manifest_overrides=overrides)
    if bin_bytes is not None:
        name = next(k for k in files if k.endswith(".bin"))
        files[name] = bin_bytes
    archive, digest = fpga_bundle(tmp_path, files)
    return archive, digest


def test_new_image_id_requires_no_factory_registry(tmp_path):
    new_bin = b"NEW SYNTHETIC HOST-ONLY FPGA BIN - NOT A BITSTREAM"
    files, _ = synthetic_image(new_bin, manifest_overrides={
        "image_id": "new-authorized-image-2026"})
    archive, digest = fpga_bundle(tmp_path, files)
    result = qualify(tmp_path, archive, digest)
    assert result["archive_sha256"] == digest
    assert result["images"][0]["image_id"] == "new-authorized-image-2026"
    assert result["images"][0]["bin_sha256"] == hashlib.sha256(new_bin).hexdigest()
    assert result["identity_readback"] == "NOT_RUN"
    assert result["fpga_loaded"] is False
    assert result["execution_permitted"] is False
    assert not (tmp_path / "factory-registry.json").exists()


def test_reference_manifest_still_parses(tmp_path):
    path = ROOT / "pl/hil/releases/swd-independent-d0add58c/plasma-image-manifest.json"
    root = qualification.load_root_manifest_parser()
    parsed = root.parse_image_manifest_bytes(path.read_bytes())
    assert parsed.abi_version == qualification.DRIVER_ABI
    assert parsed.site_bitmap == 3
    assert parsed.expected_uio["backend"] == "devmem"


def test_valid_triple_is_static_qualified_without_load_or_readback(tmp_path):
    files, _ = synthetic_image()
    archive, digest = fpga_bundle(tmp_path, files)
    result = qualify(tmp_path, archive, digest)
    assert result["result"] == "STATIC_QUALIFIED"
    assert result["archive_sha256"] == digest
    assert result["identity_readback"] == "NOT_RUN"


def test_bundle_without_fpga_needs_no_registry(tmp_path):
    archive, digest = bundle_v3(tmp_path, parts=[
        ("tool", "python", [], {"python/tool.py": b"# not executed\n"})])
    assert qualify(tmp_path, archive, digest) is None


def test_multiple_fpga_packages_fail_before_install(tmp_path):
    files, _ = synthetic_image()
    archive, digest = bundle_v3(tmp_path, parts=[
        ("image-one", "fpga-image", [], files),
        ("image-two", "fpga-image", [], files)])
    deny("FPGA_IMAGE_PACKAGE_NOT_UNIQUE", tmp_path, archive, digest)


@pytest.mark.parametrize("overrides,code", [
    ({"abi_version": 0x00060001, "identity_words": [[0, 0x00060001, 0xFFFFFFFF],
                                                    [0x1000, 0x00050002, 0xFFFFFFFF]]},
     "FPGA_IMAGE_DRIVER_ABI_UNSUPPORTED"),
    ({"identity_words": [[0, 0x00050001, 0xFFFFFFFF], [0, 0x00050002, 0xFFFFFFFF]]},
     "FPGA_IMAGE_MANIFEST_DENIED:IMAGE_RELEASE_ABI_DENIED"),
    ({"site_bitmap": 0}, "FPGA_IMAGE_MANIFEST_DENIED:IMAGE_RELEASE_APERTURE_DENIED"),
    ({"firmware_sha256": "0" * 64}, "FPGA_IMAGE_BIN_SHA_MISMATCH"),
    ({"recovery_sha256": "d" * 64}, "FPGA_IMAGE_MANIFEST_DENIED:IMAGE_RECOVERY_NOT_DEVICE_GOLDEN"),
])
def test_invalid_image_fails_closed(tmp_path, overrides, code):
    archive, digest = _with_manifest(tmp_path, overrides)
    deny(code, tmp_path, archive, digest)


def test_manifest_rejected_by_root_parser(tmp_path):
    archive, digest = _with_manifest(tmp_path, {"schema": "plasma.fpga.image.v0"})
    deny("FPGA_IMAGE_MANIFEST_DENIED:IMAGE_MANIFEST_SCHEMA_DENIED", tmp_path, archive, digest)


def test_bin_bytes_differ_from_manifest(tmp_path):
    files, _ = synthetic_image()
    name = next(k for k in files if k.endswith(".bin"))
    files[name] = b"TAMPERED SYNTHETIC BIN"
    archive, digest = fpga_bundle(tmp_path, files)
    deny("FPGA_IMAGE_BIN_SHA_MISMATCH", tmp_path, archive, digest)


def test_bin_name_differs_from_manifest(tmp_path):
    files, _ = synthetic_image()
    name = next(k for k in files if k.endswith(".bin"))
    files["fpga/renamed.bin"] = files.pop(name)
    archive, digest = fpga_bundle(tmp_path, files)
    deny("FPGA_IMAGE_BIN_NAME_MISMATCH", tmp_path, archive, digest)


@pytest.mark.parametrize("hwh,code", [
    (b"<hwh/>", "IMAGE_HWH_RANGE_INVALID"),
    (b"<ROOT><SYSTEMINFO BOARD='pynq-z2' DEVICE='7z020' PACKAGE='clg400' SPEEDGRADE='-1'/>"
     b"<MEMRANGE MASTERBUSINTERFACE='M_AXI_GP0' BASEVALUE='0x43c01000' "
     b"HIGHVALUE='0x43c01fff'/></ROOT>", "IMAGE_HWH_IDENTITY_RANGE_MISMATCH"),
])
def test_hwh_must_cover_declared_identity_addresses(tmp_path, hwh, code):
    files, _ = synthetic_image(hwh_bytes=hwh)
    archive, digest = fpga_bundle(tmp_path, files)
    deny("FPGA_IMAGE_MANIFEST_DENIED:" + code, tmp_path, archive, digest)


def test_hwh_target_must_match_manifest(tmp_path):
    files, _ = synthetic_image()
    name = next(k for k in files if k.endswith(".hwh"))
    files[name] = files[name].replace(b"DEVICE='7z020'", b"DEVICE='7z030'")
    archive, digest = fpga_bundle(tmp_path, files)
    deny("FPGA_IMAGE_MANIFEST_DENIED:IMAGE_HWH_TARGET_MISMATCH",
         tmp_path, archive, digest)


def test_device_target_board_differs_from_manifest(tmp_path):
    files, _ = synthetic_image()
    target = dict(TARGET, board="other-board")
    archive, digest = fpga_bundle(tmp_path, files, mutate=lambda m: m.__setitem__("target", target))
    deny("FPGA_IMAGE_TARGET_MISMATCH", tmp_path, archive, digest, target=target)


def test_static_qualification_never_touches_root_loader(tmp_path, monkeypatch):
    root = qualification.load_root_manifest_parser()
    def forbidden(*_a, **_k):
        raise AssertionError("B2 must not reach the Root FPGA Loader")
    for name in ("run", "stage_bundle_fpga_files_only", "read_identity",
                 "live_report", "write_state", "trusted_local"):
        monkeypatch.setattr(root, name, forbidden)
    monkeypatch.setattr(root.guard, "RootZ2TargetPort", forbidden)
    archive, digest = fpga_bundle(tmp_path)
    assert qualify(tmp_path, archive, digest)["result"] == "STATIC_QUALIFIED"


# --- service B2 over real loopback HTTP ------------------------------------

def _post_deployment(api, paths, upload_id):
    """Raw HTTP so the fail-closed error code in the 409 body stays visible."""
    status, raw = signed_call(
        api._transport, "POST", "/v1/deployments",
        json.dumps(admit_body(paths, "bundle", upload_id)).encode(), credential=TOKEN,
    )
    return status, json.loads(raw)


def _b2(api, paths, raw):
    return _post_deployment(api, paths, api.upload(raw))


def test_service_b2_pass_requires_owner_and_fpga_static_qualification(loopback, tmp_path):
    api, paths, server = loopback
    archive, digest = fpga_bundle(tmp_path / "ok")
    status, body = _b2(api, paths, archive.read_bytes())
    assert status == 200, body
    result = body["deployment"]["result"]
    assert result["result"] == "PASS"
    assert result["owner_authorized"] is True
    assert result["fpga_static_qualification"] == "STATIC_QUALIFIED"
    assert result["fpga_loaded"] is False
    assert result["identity_readback"] == "NOT_RUN"
    assert result["install_qualified"] is False
    plan = result["plan"]
    assert plan["execution_permitted"] is False
    assert plan["fpga_qualification"]["archive_sha256"] == digest
    assert plan["owner_authorization"]["subject_sha256"] == digest
    assert plan["owner_authorization"]["action"] == "bundle.admit"
    assert not paths.product_root.exists()
    # The SWPC client accepts this receipt as a valid B2 admission.
    assert client._valid_package_admission(body["deployment"], kind="bundle")


def test_client_rejects_b2_receipt_claiming_fpga_load_or_missing_qualification(
        loopback, tmp_path):
    api, paths, server = loopback
    archive, _ = fpga_bundle(tmp_path / "ok")
    _status, body = _b2(api, paths, archive.read_bytes())
    receipt = body["deployment"]
    for mutate in (
        lambda r: r["result"].__setitem__("fpga_static_qualification", "NOT_APPLICABLE"),
        lambda r: r["result"].__setitem__("fpga_loaded", True),
        lambda r: r["result"].__setitem__("identity_readback", "PASS"),
        lambda r: r["result"].__setitem__("owner_authorized", False),
        lambda r: r["result"]["plan"]["owner_authorization"].__setitem__("action", "bundle.install"),
        lambda r: r["result"]["plan"]["owner_authorization"].__setitem__("subject_sha256", "f" * 64),
        lambda r: r["result"]["plan"].__delitem__("owner_authorization"),
        lambda r: r["result"]["plan"].__setitem__("execution_permitted", True),
    ):
        changed = json.loads(json.dumps(receipt))
        mutate(changed)
        assert not client._valid_package_admission(changed, kind="bundle")


def test_service_b2_invalid_fpga_is_not_admitted(loopback, tmp_path):
    api, paths, server = loopback
    files, _ = synthetic_image(manifest_overrides={"firmware_sha256": "0" * 64})
    archive, _digest = fpga_bundle(tmp_path / "bad", files)
    status, body = _b2(api, paths, archive.read_bytes())
    assert status == 409 and "FPGA_IMAGE_BIN_SHA_MISMATCH" in json.dumps(body)
    record = bootstrap._deployment_api_record(paths)
    assert record is None or record.get("state") != "admitted"


def test_service_b2_without_owner_authorization_fails_before_fpga(loopback, tmp_path):
    api, paths, server = loopback
    archive, _ = fpga_bundle(tmp_path / "x")
    raw = archive.read_bytes()
    upload_id = api.upload(raw)
    status, raw_body = signed_call(
        api._transport, "POST", "/v1/deployments",
        json.dumps({"kind": "bundle", "upload_id": upload_id}).encode(), credential=TOKEN,
    )
    assert status == 409 and "PACKAGE_REQUEST_FIELDS_DENIED" in raw_body.decode()
    assert not paths.deployment_record.exists()


# --- B3 must re-qualify against the CURRENT trusted state ------------------

def _b3_server(tmp_path):
    paths = bootstrap.ServicePaths(
        product_root=tmp_path / "product", state_root=tmp_path / "state",
        package_target_file=tmp_path / "trusted-target.json",
        bundle_install_policy=tmp_path / "trusted-policy.json",
        machine_id_path=machine_id_file(tmp_path),
    )
    paths.package_target_file.write_text(json.dumps(TARGET))
    paths.package_target_file.chmod(0o600)
    paths.bundle_install_policy.write_text(json.dumps({
        "schema": "plasma.ppu.b3-install-policy.v2", "mode": "development",
        "modes": ["activate", "stage_only"], "actions": ["install", "verify"],
    }))
    paths.bundle_install_policy.chmod(0o600)
    srv = object.__new__(bootstrap.BootstrapHTTPServer)
    srv.bootstrap_paths = paths
    srv.mutation_lock = threading.RLock()
    srv.deployment_thread = None
    calls = []
    srv.bundle_install_runner = lambda *args: calls.append(args) or {}
    return srv, paths, calls


def _commit(paths, raw):
    digest = hashlib.sha256(raw).hexdigest()
    upload_id = bootstrap.create_upload(paths, size=len(raw), sha256=digest)["upload_id"]
    bootstrap.append_chunk(paths, upload_id, offset=0,
                           data_base64=base64.b64encode(raw).decode("ascii"),
                           sha256=digest)
    bootstrap.commit_upload(paths, upload_id)
    return upload_id


def test_b3_rejects_owner_authorization_change_after_b2(tmp_path):
    srv, paths, calls = _b3_server(tmp_path)
    archive, digest = bundle_v3(tmp_path / "bundle", mutate=lambda m: m.__setitem__(
        "actions", ["install", "verify"]))
    raw = archive.read_bytes()
    upload_id = _commit(paths, raw)
    b2 = srv.start_deployment(admit_body(paths, "bundle", upload_id))
    assert b2["result"]["fpga_static_qualification"] == "STATIC_QUALIFIED"
    b3 = install_body(paths, b2, fpga_load=False)

    # Pairing credential rotated after the owner signed the B3 request:
    # every outstanding authorization is invalid.
    original_token = paths.token_file.read_text()
    paths.token_file.write_text("rotated-paired-credential-" + "z" * 24 + "\n")
    with pytest.raises(bootstrap.BootstrapServiceError, match="OWNER_AUTHORIZATION_INVALID"):
        srv.start_deployment(b3)
    paths.token_file.write_text(original_token)
    # FPGA load is a distinct owner action: an install-only authorization
    # cannot be widened into an FPGA load.
    widened = dict(b3, mode="activate", fpga_load=True)
    with pytest.raises(bootstrap.BootstrapServiceError, match="OWNER_AUTHORIZATION_ACTION_MISMATCH"):
        srv.start_deployment(widened)
    assert calls == []

    # Unchanged trusted state: B3 proceeds to the (stubbed) install-only runner.
    srv.start_deployment(b3)
    srv.deployment_thread.join(timeout=10)
    assert len(calls) == 1
    assert not (paths.product_root / "current").exists()


@pytest.mark.parametrize("build", ("ab79b04e", "bd976140"))
def test_retired_release_files_remain_absent(build):
    assert not (ROOT / f"pl/hil/releases/swd-independent-{build}").exists()
