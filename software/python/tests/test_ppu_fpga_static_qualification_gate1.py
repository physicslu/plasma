"""B2 static FPGA qualification inside the ONE Bundle v3 B2/B3 flow (Host-only).

All FPGA bytes here are SYNTHETIC (see ppu_fpga_qualification_fixture). These
tests prove admission logic only; they are not a Vivado build, FPGA load,
Identity readback, Z2 HIL or DUT result.
"""
from __future__ import annotations

import base64
import hashlib
import json
import threading
from pathlib import Path

import pytest

from .ppu_bundle_authority_fixture import provision_fixture_grant
from .ppu_fpga_qualification_fixture import (
    synthetic_image, write_contracts, provision_default_contract,
)
from .test_ppu_bundle_v3_packages_contract import (
    ROOT, SOURCE, TARGET, bundle_v3, contract, load,
)
from .test_ppu_package_receive_admission_pr1 import TOKEN, client, loopback  # noqa: F401

qualification = load("ppu_fpga_static_qualification_test", "ppu_fpga_qualification.py")
bootstrap = load("ppu_fpga_static_qualification_service", "ppu-bootstrap-service.py")

SHIPPED = ROOT / "scripts" / "ppu-fpga-image-contracts.json"

# Byte-exact copy of PR #1247 draft fixture
# pl/tests/fixtures/swd-independent-ab79b04e/plasma-image-manifest.json
# (draft; NOT merged, deployed or HIL-qualified). Used only to prove the shipped
# contract pins that Manifest and that the Root parser accepts it.
PR1247_MANIFEST = b'''{
  "schema": "plasma.fpga.image.v1",
  "image_id": "z2-independent-swd-v5-ab79b04e",
  "board_id": "pynq-z2",
  "fpga_part": "xc7z020clg400-1",
  "soc_compatible": "xlnx,zynq-7000",
  "firmware_name": "plasma-swd-independent-ab79b04e.bin",
  "firmware_sha256": "d3b65a818c03ef1f73a3f0026357d6ed6a9fd903f2f041bc09b89d6b6ba3b773",
  "recovery_name": "base.bin",
  "recovery_sha256": "c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c",
  "abi_version": 327681,
  "abi_offset": 0,
  "identity_words": [
    [0, 327681, 4294967295],
    [4096, 327682, 4294967295]
  ],
  "site_bitmap": 3,
  "site_bitmap_offset": null,
  "axi_base": 1136660480,
  "axi_bytes": 8192,
  "owner_base": 1136656384,
  "owner_bytes": 65536,
  "uio_name": "uio1",
  "expected_uio": {
    "uio": "uio1",
    "driver": "uio_pdrv_genirq",
    "maps": [[1136656384, 65536]],
    "runtime": "suspended",
    "irq_counts": [0, 0]
  }
}
'''


def fpga_bundle(tmp_path, files=None, *, mutate=None):
    files = synthetic_image()[0] if files is None else files
    return bundle_v3(tmp_path, parts=[("swd-image", "fpga-image", [], files)],
                     mutate=mutate)


def qualify(tmp_path, archive, digest, contracts_path, *, target=TARGET):
    verified = contract.verify_host_only_artifact(
        archive, expected_sha256=digest, source_commit=None, target_profile=target,
    )
    return qualification.qualify_bundle_fpga(
        archive, verified, contracts_path=contracts_path, trusted_target=target,
    )


def deny(code, tmp_path, archive, digest, contracts_path, **kw):
    with pytest.raises(qualification.FpgaQualificationDenied, match=code):
        qualify(tmp_path, archive, digest, contracts_path, **kw)


def contract_file(tmp_path, *entries):
    return write_contracts(tmp_path / "factory" / "contracts.json", *entries)


# --- shipped trusted contract (ABI v5 / ab79b04e) -------------------------

def test_shipped_contract_is_abi5_ab79b04e_two_site(tmp_path):
    copy = tmp_path / "shipped.json"
    copy.write_bytes(SHIPPED.read_bytes())
    copy.chmod(0o644)
    contracts, _ = qualification.read_trusted_contracts(copy)
    assert list(contracts) == ["z2-independent-swd-v5-ab79b04e"]
    entry = contracts["z2-independent-swd-v5-ab79b04e"]
    assert entry["build"] == "ab79b04e"
    assert entry["source_commit"].startswith("ab79b04e")
    assert entry["target"] == TARGET
    assert entry["site_identities"] == [
        {"site_id": 1, "offset": 0x0000, "identity": 0x00050001},
        {"site_id": 2, "offset": 0x1000, "identity": 0x00050002},
    ]
    assert entry["abi_version"] == 0x00050001 and entry["site_bitmap"] == 0b11
    # The contract is a static expectation; it never claims readback/HIL.
    assert "static" in entry["evidence"] and "hil" not in entry["evidence"].lower()


def test_shipped_contract_pins_pr1247_manifest_parsed_by_root_parser():
    entry = json.loads(SHIPPED.read_text())["contracts"][0]
    assert hashlib.sha256(PR1247_MANIFEST).hexdigest() == entry["manifest_sha256"]
    root = qualification.load_root_manifest_parser()
    assert Path(root.__file__).resolve() == (ROOT / "pl/hil/fpga_image_root.py").resolve()
    parsed = root.parse_image_manifest_bytes(PR1247_MANIFEST)
    assert parsed.image_id == entry["image_id"]
    assert parsed.firmware_name == entry["firmware_name"]
    assert parsed.firmware_sha256 == entry["bin_sha256"]
    assert parsed.identity_words == ((0, 0x00050001, 0xFFFFFFFF),
                                     (0x1000, 0x00050002, 0xFFFFFFFF))
    assert (parsed.axi_base, parsed.axi_bytes, parsed.owner_base, parsed.owner_bytes) == (
        entry["axi_base"], entry["axi_bytes"], entry["owner_base"], entry["owner_bytes"])


def test_shipped_contract_rejects_synthetic_image(tmp_path):
    archive, digest = fpga_bundle(tmp_path)
    copy = tmp_path / "shipped.json"
    copy.write_bytes(SHIPPED.read_bytes())
    copy.chmod(0o644)
    deny("FPGA_IMAGE_CONTRACT_UNKNOWN", tmp_path, archive, digest, copy)


# --- module-level positive and negative ------------------------------------

def test_valid_triple_is_static_qualified_without_load_or_readback(tmp_path):
    files, entry = synthetic_image()
    archive, digest = fpga_bundle(tmp_path, files)
    result = qualify(tmp_path, archive, digest, contract_file(tmp_path, entry))
    assert result["result"] == "STATIC_QUALIFIED"
    assert result["archive_sha256"] == digest
    assert result["fpga_loaded"] is False
    assert result["identity_readback"] == "NOT_RUN"
    assert result["execution_permitted"] is False
    (image,) = result["images"]
    assert image["contract_id"] == entry["contract_id"]
    assert image["site_identities"] == entry["site_identities"]
    assert image["bin_sha256"] == entry["bin_sha256"]


def test_bundle_without_fpga_needs_no_contract(tmp_path):
    archive, digest = bundle_v3(tmp_path, parts=[
        ("tool", "python", [], {"python/tool.py": b"# not executed\n"})])
    assert qualify(tmp_path, archive, digest, tmp_path / "absent.json") is None


@pytest.mark.parametrize("problem,code", [
    ("missing", "FPGA_CONTRACTS_NOT_PROVISIONED"),
    ("group-writable", "FPGA_CONTRACTS_UNTRUSTED"),
    ("symlink", "FPGA_CONTRACTS_UNTRUSTED"),
    ("bad-schema", "FPGA_CONTRACTS_INVALID"),
    ("zero-site", "FPGA_CONTRACT_SITES_INVALID"),
    ("bitmap", "FPGA_CONTRACT_SITES_INVALID"),
])
def test_untrusted_or_invalid_contract_fails_closed(tmp_path, problem, code):
    files, entry = synthetic_image()
    archive, digest = fpga_bundle(tmp_path, files)
    path = tmp_path / "factory" / "contracts.json"
    if problem == "missing":
        pass
    elif problem == "group-writable":
        contract_file(tmp_path, entry).chmod(0o664)
    elif problem == "symlink":
        real = write_contracts(tmp_path / "elsewhere.json", entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(real)
    elif problem == "bad-schema":
        contract_file(tmp_path, entry)
        data = json.loads(path.read_text())
        data["schema"] = "plasma.ppu.fpga-image-contracts.v0"
        path.write_text(json.dumps(data))
    elif problem == "zero-site":
        contract_file(tmp_path, dict(entry, site_identities=[
            {"site_id": 0, "offset": 0, "identity": 0x00050001}]))
    elif problem == "bitmap":
        contract_file(tmp_path, dict(entry, site_bitmap=1))
    deny(code, tmp_path, archive, digest, path)


def _with_manifest(tmp_path, overrides, *, contract_overrides=None, bin_bytes=None):
    """Bundle whose Manifest differs; contract pins THAT Manifest's SHA so the
    semantic (ABI / Identity / Site / BIN) check is the one that must fail."""
    good_files, good = synthetic_image()
    files, changed = synthetic_image(manifest_overrides=overrides)
    if bin_bytes is not None:
        name = next(k for k in files if k.endswith(".bin"))
        files[name] = bin_bytes
    entry = dict(good, manifest_sha256=changed["manifest_sha256"],
                 **(contract_overrides or {}))
    archive, digest = fpga_bundle(tmp_path, files)
    return archive, digest, contract_file(tmp_path, entry)


@pytest.mark.parametrize("overrides,code", [
    ({"abi_version": 0x00060001, "identity_words": [[0, 0x00060001, 0xFFFFFFFF],
                                                    [0x1000, 0x00050002, 0xFFFFFFFF]]},
     "FPGA_IMAGE_ABI_MISMATCH"),
    ({"identity_words": [[0, 0x00050001, 0xFFFFFFFF], [0x1000, 0x00050003, 0xFFFFFFFF]]},
     "FPGA_IMAGE_IDENTITY_MISMATCH"),
    ({"site_bitmap": 1}, "FPGA_IMAGE_SITE_CAPABILITY_MISMATCH"),
    ({"firmware_sha256": "0" * 64}, "FPGA_IMAGE_BIN_SHA_MISMATCH"),
])
def test_manifest_semantics_must_match_trusted_contract(tmp_path, overrides, code):
    archive, digest, path = _with_manifest(tmp_path, overrides)
    deny(code, tmp_path, archive, digest, path)


def test_wrong_image_identity_is_unknown_to_contract(tmp_path):
    files, _ = synthetic_image(manifest_overrides={"image_id": "attacker-chosen-ab79b04e"})
    _, entry = synthetic_image()
    archive, digest = fpga_bundle(tmp_path, files)
    deny("FPGA_IMAGE_CONTRACT_UNKNOWN", tmp_path, archive, digest,
         contract_file(tmp_path, entry))


def test_manifest_rejected_by_root_parser(tmp_path):
    files, entry = synthetic_image(manifest_overrides={"schema": "plasma.fpga.image.v0"})
    archive, digest = fpga_bundle(tmp_path, files)
    deny("FPGA_IMAGE_MANIFEST_DENIED:IMAGE_MANIFEST_SCHEMA_DENIED",
         tmp_path, archive, digest, contract_file(tmp_path, entry))


def test_bin_bytes_differ_from_manifest(tmp_path):
    files, entry = synthetic_image()
    name = next(k for k in files if k.endswith(".bin"))
    files[name] = b"TAMPERED SYNTHETIC BIN"
    archive, digest = fpga_bundle(tmp_path, files)
    deny("FPGA_IMAGE_BIN_SHA_MISMATCH", tmp_path, archive, digest,
         contract_file(tmp_path, entry))


def test_bin_name_differs_from_manifest(tmp_path):
    files, entry = synthetic_image()
    name = next(k for k in files if k.endswith(".bin"))
    files["fpga/renamed.bin"] = files.pop(name)
    archive, digest = fpga_bundle(tmp_path, files)
    deny("FPGA_IMAGE_BIN_NAME_MISMATCH", tmp_path, archive, digest,
         contract_file(tmp_path, entry))


def test_hwh_not_paired_with_trusted_contract(tmp_path):
    files, entry = synthetic_image(hwh_bytes=b"<!-- other synthetic handoff -->")
    _, good = synthetic_image()
    archive, digest = fpga_bundle(tmp_path, files)
    deny("FPGA_IMAGE_CONTRACT_HWH_MISMATCH", tmp_path, archive, digest,
         contract_file(tmp_path, dict(entry, hwh_sha256=good["hwh_sha256"])))


def test_manifest_bytes_not_pinned_by_contract(tmp_path):
    files, entry = synthetic_image(manifest_overrides={"soc_compatible": "other"})
    _, good = synthetic_image()
    archive, digest = fpga_bundle(tmp_path, files)
    deny("FPGA_IMAGE_CONTRACT_MANIFEST_MISMATCH", tmp_path, archive, digest,
         contract_file(tmp_path, dict(entry, manifest_sha256=good["manifest_sha256"])))


def test_contract_target_differs_from_device_target(tmp_path):
    files, entry = synthetic_image()
    archive, digest = fpga_bundle(tmp_path, files)
    other = dict(entry, target=dict(TARGET, platform="linux-aarch64"))
    deny("FPGA_IMAGE_CONTRACT_TARGET_MISMATCH", tmp_path, archive, digest,
         contract_file(tmp_path, other))


def test_device_target_board_differs_from_manifest(tmp_path):
    files, entry = synthetic_image()
    device = dict(TARGET, board="other-board")
    archive, digest = fpga_bundle(
        tmp_path, files, mutate=lambda m: m.__setitem__("target", dict(device)))
    deny("FPGA_IMAGE_TARGET_MISMATCH", tmp_path, archive, digest,
         contract_file(tmp_path, dict(entry, target=device)), target=device)


def test_static_qualification_never_touches_root_loader(tmp_path, monkeypatch):
    root = qualification.load_root_manifest_parser()
    def forbidden(*_a, **_k):
        raise AssertionError("B2 must not reach the Root FPGA Loader")
    for name in ("run", "stage_bundle_fpga_files_only", "read_identity",
                 "live_report", "write_state", "trusted_local"):
        monkeypatch.setattr(root, name, forbidden)
    monkeypatch.setattr(root.guard, "RootZ2TargetPort", forbidden)
    files, entry = synthetic_image()
    archive, digest = fpga_bundle(tmp_path, files)
    assert qualify(tmp_path, archive, digest,
                   contract_file(tmp_path, entry))["result"] == "STATIC_QUALIFIED"


# --- service B2 over real loopback HTTP ------------------------------------

def _post_deployment(api, upload_id):
    """Raw HTTP so the fail-closed error code in the 409 body stays visible."""
    status, raw = api._transport(
        "POST", "/v1/deployments",
        json.dumps({"kind": "bundle", "upload_id": upload_id}).encode(),
        {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
    )
    return status, json.loads(raw)


def _b2(api, raw):
    return _post_deployment(api, api.upload(raw))


def test_service_b2_pass_requires_master_and_fpga_static_qualification(loopback, tmp_path):
    api, paths, server = loopback
    archive, digest = fpga_bundle(tmp_path / "ok")
    status, body = _b2(api, archive.read_bytes())
    assert status == 200, body
    result = body["deployment"]["result"]
    assert result["result"] == "PASS"
    assert result["source_authorized"] is True
    assert result["fpga_static_qualification"] == "STATIC_QUALIFIED"
    assert result["fpga_loaded"] is False
    assert result["identity_readback"] == "NOT_RUN"
    assert result["install_qualified"] is False
    plan = result["plan"]
    assert plan["execution_permitted"] is False
    assert plan["fpga_qualification"]["archive_sha256"] == digest
    assert plan["authorization"]["archive_sha256"] == digest
    assert not paths.product_root.exists()
    # The SWPC client accepts this receipt as a valid B2 admission.
    assert client._valid_package_admission(body["deployment"], kind="bundle")


def test_client_rejects_b2_receipt_claiming_fpga_load_or_missing_qualification(
        loopback, tmp_path):
    api, paths, server = loopback
    archive, _ = fpga_bundle(tmp_path / "ok")
    _status, body = _b2(api, archive.read_bytes())
    receipt = body["deployment"]
    for mutate in (
        lambda r: r["result"].__setitem__("fpga_static_qualification", "NOT_APPLICABLE"),
        lambda r: r["result"].__setitem__("fpga_loaded", True),
        lambda r: r["result"].__setitem__("identity_readback", "PASS"),
        lambda r: r["result"].__setitem__("source_authorized", False),
        lambda r: r["result"]["plan"].__setitem__("execution_permitted", True),
    ):
        changed = json.loads(json.dumps(receipt))
        mutate(changed)
        assert not client._valid_package_admission(changed, kind="bundle")


def test_service_b2_fpga_unqualified_is_not_admitted(loopback, tmp_path):
    api, paths, server = loopback
    files, _ = synthetic_image(b"OTHER SYNTHETIC BIN WITH NO CONTRACT")
    archive, _digest = fpga_bundle(tmp_path / "bad", files)
    status, body = _b2(api, archive.read_bytes())
    assert status == 409 and "FPGA_IMAGE_CONTRACT_UNKNOWN" in json.dumps(body)
    record = bootstrap._deployment_api_record(paths)
    assert record is None or record.get("state") != "admitted"


def test_service_b2_without_master_grant_fails_before_fpga(loopback, tmp_path):
    api, paths, server = loopback
    archive, _ = fpga_bundle(tmp_path / "x")
    raw = archive.read_bytes()
    upload_id = api.upload(raw)
    paths.bundle_authority_policy.unlink()  # unprovisioned / revoked device
    status, body = _post_deployment(api, upload_id)
    assert status == 409 and "BUNDLE_AUTHORITY_NOT_PROVISIONED" in json.dumps(body)


# --- B3 must re-qualify against the CURRENT trusted state ------------------

def _b3_server(tmp_path):
    paths = bootstrap.ServicePaths(
        product_root=tmp_path / "product", state_root=tmp_path / "state",
        package_target_file=tmp_path / "trusted-target.json",
        bundle_install_policy=tmp_path / "trusted-policy.json",
        bundle_authority_policy=tmp_path / "private-master-grant.json",
        fpga_image_contracts=tmp_path / "factory" / "ppu-fpga-image-contracts.json",
    )
    paths.package_target_file.write_text(json.dumps(TARGET))
    paths.package_target_file.chmod(0o600)
    paths.bundle_install_policy.write_text(json.dumps({
        "schema": "plasma.ppu.b3-install-policy.v1", "mode": "development",
        "install_only": True, "actions": ["install", "verify"],
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


def test_b3_rejects_fpga_contract_or_master_grant_change_after_b2(tmp_path):
    srv, paths, calls = _b3_server(tmp_path)
    archive, digest = bundle_v3(tmp_path / "bundle", mutate=lambda m: m.__setitem__(
        "actions", ["install", "verify"]))
    raw = archive.read_bytes()
    upload_id = _commit(paths, raw)
    provision_fixture_grant(paths, raw)
    _, entry = synthetic_image()
    write_contracts(paths.fpga_image_contracts, entry)
    b2 = srv.start_deployment({"kind": "bundle", "upload_id": upload_id})
    assert b2["result"]["fpga_static_qualification"] == "STATIC_QUALIFIED"
    b3 = {"kind": "bundle", "upload_id": upload_id, "install_only": True}

    # Contract withdrawn after B2.
    original = paths.fpga_image_contracts.read_bytes()
    paths.fpga_image_contracts.unlink()
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_FPGA_QUALIFICATION_DENIED"):
        srv.start_deployment(b3)
    # Contract replaced by a different (still valid) trusted contract set.
    _, extra = synthetic_image(b"ANOTHER SYNTHETIC BIN")
    write_contracts(paths.fpga_image_contracts, entry, extra)
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_FPGA_QUALIFICATION_CHANGED"):
        srv.start_deployment(b3)
    paths.fpga_image_contracts.write_bytes(original)

    # Master grant changed (new generation) after B2.
    grants = json.loads(paths.bundle_authority_policy.read_text())
    paths.bundle_authority_policy.write_text(json.dumps(dict(grants, master_generation=2)))
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_ADMISSION_AUTHORITY_CHANGED"):
        srv.start_deployment(b3)
    # Master grant expired after B2.
    expired = json.loads(json.dumps(grants))
    expired["authorizations"][0]["expires_epoch_s"] = 1
    paths.bundle_authority_policy.write_text(json.dumps(expired))
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_MASTER_AUTHORITY_DENIED"):
        srv.start_deployment(b3)
    paths.bundle_authority_policy.write_text(json.dumps(grants))
    assert calls == []

    # Unchanged trusted state: B3 proceeds to the (stubbed) install-only runner.
    srv.start_deployment(b3)
    srv.deployment_thread.join(timeout=10)
    assert len(calls) == 1
    assert not (paths.product_root / "current").exists()
