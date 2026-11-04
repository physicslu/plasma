"""Bundle-to-Provider Host-only route tests; never start hardware or Provider code."""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from contextlib import nullcontext

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT, TARGET
from .test_ppu_b3_z2_install_gate1 import b3_request, make_coordinator
from .test_ppu_bundle_v3_smoke_execution_gate1 import build_smoke

sys.path.insert(0, str(ROOT / "scripts"))
import ppu_provider_contract as providers  # noqa: E402


def staged_provider(tmp_path, *, provider_id="reference-provider", transport="fpga",
                    target="arbitrary-target", descriptor_change=None):
    source, _ = build_smoke(tmp_path / "source")
    with zipfile.ZipFile(source) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    descriptor = {
        "schema": providers.SCHEMA, "target": target,
        "provider_package": provider_id,
        "operations": ["erase", "program", "verify", "read", "flash_cycle"],
        "sites": [1, 2], "transport": transport,
        "driver_abi": "example-swd-abi" if transport == "fpga" else None,
        "fpga_package": "example-fpga" if transport == "fpga" else None,
        "max_image_bytes": 4096, "max_runtime_s": 30,
    }
    if descriptor_change:
        descriptor.update(descriptor_change)
    provider_path = f"payload/packages/{provider_id}/python/main.py"
    profile_path = "payload/packages/profile/data/plasma-provider.json"
    payloads = {
        provider_path: b"raise RuntimeError('Provider execution is not part of route resolution')\n",
        profile_path: json.dumps(descriptor, sort_keys=True).encode(),
    }
    packages = [
        {"id": provider_id, "kind": "python", "version": "1.0", "requires": [],
         "files": []},
        {"id": "profile", "kind": "programming-profile", "version": "1.0",
         "requires": [provider_id] + (["example-fpga"] if transport == "fpga" else []),
         "files": []},
    ]
    if transport == "fpga":
        prefix = "payload/packages/example-fpga/fpga/"
        payloads[prefix + "image.bin"] = b"host-only FPGA bytes never loaded"
        payloads[prefix + "image.hwh"] = b"host-only HWH bytes never loaded"
        payloads[prefix + "image.json"] = b"{}"
        packages.append({"id": "example-fpga", "kind": "fpga-image", "version": "1.0",
                         "requires": [], "files": []})
    for package in packages:
        prefix = f"payload/packages/{package['id']}/"
        for path, raw in payloads.items():
            if path.startswith(prefix):
                package["files"].append({"path": path, "sha256": hashlib.sha256(raw).hexdigest(),
                                         "size": len(raw), "executable": False})
    manifest["packages"] = packages
    archive = tmp_path / "provider.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
        for path, raw in payloads.items():
            output.writestr(path, raw)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    co = make_coordinator(tmp_path)
    co.execute_bundle_v3_install(b3_request(archive, digest))
    co.activate_staged_asset_set(digest, quiescence_lease=nullcontext)
    return co.paths.product_root, digest, descriptor


def observed(*, transport="fpga"):
    return {"platform": TARGET["platform"], "board": TARGET["board"],
            "fpga_part": TARGET["fpga_part"], "sites": [1, 2],
            "ps_transport_ready": True, "loaded_fpga_package": "example-fpga",
            "driver_abi": "example-swd-abi", "fpga_identity_proven": transport == "fpga"}


def test_two_provider_routes_use_one_bundle_job_contract_without_catalog(tmp_path):
    for provider_id, transport in (("reference-provider", "fpga"),
                                   ("independent-provider", "ps-only")):
        root, digest, _ = staged_provider(tmp_path / provider_id,
                                          provider_id=provider_id, transport=transport)
        route = providers.resolve(root, asset_set_sha256=digest, target="arbitrary-target",
                                  operation="flash_cycle", site_id=2, image_size=1024,
                                  hardware=observed(transport=transport))
        assert route.provider_package == provider_id
        assert route.operation == "flash_cycle" and route.site_id == 2
        assert route.transport == transport


@pytest.mark.parametrize("change,code", [
    ({"operations": ["program"]}, "OPERATION_UNSUPPORTED"),
    ({"provider_package": "missing"}, "PROVIDER_PACKAGE_INVALID"),
    ({"max_image_bytes": 4}, "IMAGE_OUT_OF_BOUNDS"),
])
def test_incomplete_provider_contract_fails_closed(tmp_path, change, code):
    root, digest, _ = staged_provider(tmp_path, descriptor_change=change)
    with pytest.raises(providers.ProviderDenied, match=code):
        providers.resolve(root, asset_set_sha256=digest, target="arbitrary-target",
                          operation="flash_cycle", site_id=2, image_size=1024,
                          hardware=observed())


def test_actual_hardware_and_active_bytes_must_still_match(tmp_path):
    root, digest, _ = staged_provider(tmp_path)
    with pytest.raises(providers.ProviderDenied, match="FPGA_DRIVER_UNVERIFIED"):
        providers.resolve(root, asset_set_sha256=digest, target="arbitrary-target",
                          operation="program", site_id=2, image_size=1024,
                          hardware={**observed(), "driver_abi": "other"})
    descriptor = root / "assets" / "staged" / digest / "payload/packages/profile/data/plasma-provider.json"
    descriptor.chmod(0o600)
    descriptor.write_text("{}")
    with pytest.raises(providers.ProviderDenied, match="ACTIVE_SET_UNTRUSTED"):
        providers.resolve(root, asset_set_sha256=digest, target="arbitrary-target",
                          operation="program", site_id=2, image_size=1024,
                          hardware=observed())
