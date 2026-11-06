"""Bundle-bound programming route resolution. Pure Host-only admission logic.

The descriptor is data in one verified Active Asset Set. Resolving it never
loads Provider code, configures PL, or grants hardware access.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import ppu_asset_set
import ppu_provider_options

SCHEMA = "plasma.ppu.provider-capabilities.v1"
DESCRIPTOR = "data/plasma-provider.json"
PLATFORM_OPTIONS = "data/plasma-provider-options.json"
OPERATIONS = frozenset({"erase", "program", "verify", "read", "flash_cycle"})
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
PACKAGE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class ProviderDenied(ValueError):
    pass


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise ProviderDenied(code)


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        _need(key not in result, "PROVIDER_DESCRIPTOR_DUPLICATE_KEY")
        result[key] = value
    return result


def _schema_pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        _need(key not in result, "OPTIONS_SCHEMA_INVALID")
        result[key] = value
    return result


@dataclass(frozen=True)
class ProviderRoute:
    asset_set_sha256: str
    provider_package: str
    profile_package: str
    descriptor_sha256: str
    target: str
    operation: str
    site_id: int
    transport: str
    driver_abi: str | None
    fpga_package: str | None
    max_image_bytes: int
    options_schema_sha256: str
    options_sha256: str
    options_json: bytes


def resolve(
    product_root: Path, *, asset_set_sha256: str, target: str,
    provider: str, profile: str, operation: str, site_id: int, image_size: int,
    hardware: Mapping[str, Any], options: Mapping[str, Any],
) -> ProviderRoute:
    """Resolve one route from verified bytes and observed capabilities.

    ``hardware`` is supplied by a trusted device-side observer, never copied
    from the Job or Bundle. A PS-only route requires explicit observed PS Site
    support; an FPGA route requires the observed loaded image/ABI/Site.
    ``options`` must be supplied explicitly, even when empty. It is checked
    against the selected Provider's hash-verified, versioned schema.
    """
    _need(type(asset_set_sha256) is str and SHA64.fullmatch(asset_set_sha256) is not None,
          "ASSET_SET_IDENTITY_INVALID")
    _need(type(target) is str and bool(target) and len(target) <= 256,
          "TARGET_INVALID")
    _need(type(provider) is str and PACKAGE_ID.fullmatch(provider) is not None,
          "PROVIDER_REF_INVALID")
    _need(type(profile) is str and PACKAGE_ID.fullmatch(profile) is not None,
          "PROFILE_REF_INVALID")
    _need(type(operation) is str and operation in OPERATIONS
          and type(site_id) is int and site_id >= 1
          and type(image_size) is int and image_size >= 0,
          "JOB_CONTRACT_INVALID")
    _need(isinstance(hardware, Mapping), "HARDWARE_UNVERIFIED")
    try:
        active = ppu_asset_set.read_active(product_root)
        _need(active["state"] == "ACTIVE"
              and active["asset_set_sha256"] == asset_set_sha256,
              "ACTIVE_SET_MISMATCH")
    except ppu_asset_set.AssetSetError as exc:
        raise ProviderDenied(f"ACTIVE_SET_UNTRUSTED:{exc}") from exc
    root = product_root / "assets" / "staged" / asset_set_sha256
    try:
        manifest = json.loads((root / "manifest.json").read_bytes(), object_pairs_hook=_pairs)
    except (OSError, ValueError, UnicodeError) as exc:
        raise ProviderDenied("BUNDLE_MANIFEST_UNREADABLE") from exc
    _need(manifest.get("schema") == "plasma.ppu.bundle.v3", "BUNDLE_SCHEMA_INVALID")
    packages = {p["id"]: p for p in manifest["packages"]}
    selected_profile = packages.get(profile)
    _need(selected_profile is not None, "PROFILE_MISSING_OR_AMBIGUOUS")
    _need(selected_profile["kind"] == "programming-profile", "PROFILE_PACKAGE_INVALID")
    for entry in selected_profile["files"]:
        if entry["path"] != f"payload/packages/{profile}/{DESCRIPTOR}":
            continue
        _need(entry["executable"] is False and entry["size"] <= 8192,
              "PROVIDER_DESCRIPTOR_INVALID")
        try:
            raw = (root / entry["path"]).read_bytes()
        except OSError as exc:
            raise ProviderDenied("PROVIDER_DESCRIPTOR_UNREADABLE") from exc
        _need(hashlib.sha256(raw).hexdigest() == entry["sha256"],
              "PROVIDER_DESCRIPTOR_CHANGED")
        try:
            desc = json.loads(raw, object_pairs_hook=_pairs)
        except (ValueError, UnicodeError) as exc:
            raise ProviderDenied("PROVIDER_DESCRIPTOR_INVALID") from exc
        _need(type(desc) is dict and set(desc) == {
            "schema", "target", "provider_package", "operations", "sites",
            "transport", "driver_abi", "fpga_package", "max_image_bytes"},
              "PROVIDER_DESCRIPTOR_INVALID")
        _need(desc["schema"] == SCHEMA and type(desc["target"]) is str
              and type(desc["provider_package"]) is str
              and type(desc["operations"]) is list
              and bool(desc["operations"])
              and all(type(op) is str for op in desc["operations"])
              and len(desc["operations"]) == len(set(desc["operations"]))
              and set(desc["operations"]) <= OPERATIONS
              and type(desc["sites"]) is list and bool(desc["sites"])
              and all(type(s) is int for s in desc["sites"])
              and desc["sites"] == sorted(set(desc["sites"]))
              and all(type(s) is int and s >= 1 for s in desc["sites"])
              and type(desc["transport"]) is str
              and desc["transport"] in ("ps-only", "fpga")
              and (desc["driver_abi"] is None or type(desc["driver_abi"]) is str)
              and (desc["fpga_package"] is None or type(desc["fpga_package"]) is str)
              and type(desc["max_image_bytes"]) is int
              and 0 < desc["max_image_bytes"] <= 512 * 1024 * 1024,
              "PROVIDER_DESCRIPTOR_INVALID")
        break
    else:
        raise ProviderDenied("PROVIDER_DESCRIPTOR_MISSING")
    _need(desc["target"] == target, "TARGET_MISMATCH")
    digest = entry["sha256"]
    _need(desc["provider_package"] == provider, "PROVIDER_SELECTION_MISMATCH")
    selected_provider = packages.get(desc["provider_package"])
    _need(selected_provider is not None and selected_provider["id"] in selected_profile["requires"]
          and selected_provider["kind"] in ("python", "native-c", "platform-provider"),
          "PROVIDER_PACKAGE_INVALID")
    provider_paths = {entry["path"] for entry in selected_provider["files"]}
    provider_prefix = f"payload/packages/{selected_provider['id']}/"
    _need((selected_provider["kind"] == "python" and provider_prefix + "python/main.py" in provider_paths)
          or (selected_provider["kind"] == "native-c" and any(
              entry["path"].startswith(provider_prefix + "bin/")
              and entry["executable"] is True for entry in selected_provider["files"]))
          or (selected_provider["kind"] == "platform-provider"
              and provider_paths == {provider_prefix + PLATFORM_OPTIONS}
              and all(entry["executable"] is False for entry in selected_provider["files"])),
          "PROVIDER_ENTRYPOINT_MISSING")
    _need(operation in desc["operations"], "OPERATION_UNSUPPORTED")
    observed_sites = hardware.get("sites")
    _need(type(observed_sites) in (list, tuple)
          and all(type(observed_site) is int and observed_site >= 1
                  for observed_site in observed_sites)
          and len(observed_sites) == len(set(observed_sites)),
          "HARDWARE_SITES_INVALID")
    _need(site_id in desc["sites"] and site_id in observed_sites,
          "SITE_NOT_SUPPORTED")
    _need(image_size <= desc["max_image_bytes"], "IMAGE_OUT_OF_BOUNDS")
    _need(hardware.get("platform") == manifest["target"]["platform"]
          and hardware.get("board") == manifest["target"]["board"],
          "PLATFORM_MISMATCH")
    if desc["transport"] == "ps-only":
        _need(desc["driver_abi"] is None and desc["fpga_package"] is None
              and hardware.get("ps_transport_ready") is True,
              "PS_TRANSPORT_UNVERIFIED")
    else:
        fpga = packages.get(desc["fpga_package"])
        _need((desc["fpga_package"] is None or (
                  fpga is not None and fpga["kind"] == "fpga-image"
                  and fpga["id"] in selected_profile["requires"]))
              and type(desc["driver_abi"]) is str and bool(desc["driver_abi"]),
              "FPGA_DRIVER_CONTRACT_INVALID")
        _need(hardware.get("fpga_part") == manifest["target"]["fpga_part"]
              and (fpga is None or hardware.get("loaded_fpga_package") == fpga["id"])
              and hardware.get("driver_abi") == desc["driver_abi"]
              and hardware.get("fpga_identity_proven") is True
              and (desc["fpga_package"] is not None or (
                  type(hardware.get("worker_identity")) is dict
                  and hardware["worker_identity"].get("status") == "IMAGE"
                  and bool(hardware["worker_identity"].get("image_id")))),
              "FPGA_DRIVER_UNVERIFIED")
    options_path = provider_prefix + (PLATFORM_OPTIONS if selected_provider["kind"]
                                      == "platform-provider" else ppu_provider_options.FILE)
    schema_entries = [entry for entry in selected_provider["files"]
                      if entry["path"] == options_path]
    _need(len(schema_entries) == 1, "OPTIONS_SCHEMA_MISSING")
    schema_entry = schema_entries[0]
    _need(schema_entry["executable"] is False
          and 0 < schema_entry["size"] <= ppu_provider_options.MAX_SCHEMA_BYTES,
          "OPTIONS_SCHEMA_INVALID")
    try:
        schema_raw = (root / options_path).read_bytes()
    except OSError as exc:
        raise ProviderDenied("OPTIONS_SCHEMA_UNREADABLE") from exc
    schema_sha = hashlib.sha256(schema_raw).hexdigest()
    _need(len(schema_raw) == schema_entry["size"]
          and schema_sha == schema_entry["sha256"], "OPTIONS_SCHEMA_CHANGED")
    try:
        schema = json.loads(schema_raw, object_pairs_hook=_schema_pairs)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProviderDenied("OPTIONS_SCHEMA_INVALID") from exc
    try:
        options_json = ppu_provider_options.validate(schema, options)
    except ppu_provider_options.OptionsDenied as exc:
        raise ProviderDenied(str(exc)) from exc
    return ProviderRoute(asset_set_sha256, selected_provider["id"], selected_profile["id"], digest,
                         target, operation, site_id, desc["transport"],
                         desc["driver_abi"], desc["fpga_package"],
                         desc["max_image_bytes"], schema_sha,
                         hashlib.sha256(options_json).hexdigest(), options_json)
