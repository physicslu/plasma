#!/usr/bin/env python3
"""Bounded original HTML source probe for an official MicrochipDirect MCU chart.

Capture a *public manufacturer chart source* as immutable original bytes.
This tool intentionally does NOT parse Flash/RAM/VDD, identify exact ICPNs,
infer column types, claim SKU enumeration, or write Production catalog data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request
import urllib.error

URL = "https://www.microchipdirect.com/chart.aspx?branchID=21&mid=3"
LIMIT = 12 * 1024 * 1024
REQUIRED = (b"ATSAMD21G15", b"ATSAMC21G18A")


def require(ok, why):
    if not ok:
        raise ValueError(why)


def authorized(url):
    u = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(u.query)
    return (u.scheme == "https" and u.hostname == "www.microchipdirect.com"
            and u.path.casefold() == "/chart.aspx"
            and params == {"branchID": ["21"], "mid": ["3"]}
            and u.port is None and not u.username and not u.password)


def validate_html(raw):
    require(isinstance(raw, bytes) and 0 < len(raw) <= LIMIT,
            "HTML original-response size outside approved cap")
    lowered = raw.lower()
    require(b"<html" in lowered and b"</html" in lowered,
            "manufacturer response not a complete HTML document")
    require(not (b"/404" in lowered[:1000] and len(raw) < 20000),
            "manufacturer chart returned an error page")
    require(all(marker.lower() in lowered for marker in REQUIRED),
            "official MCU chart expected device markers absent")
    return {
        "original_byte_sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "marker_devices_observed": [x.decode("ascii") for x in REQUIRED],
        "source_semantic_row_replay_complete": False,
        "exact_icpn_verified": 0,
        "phase1_specifications_verified": 0,
    }


def get_bytes():
    req = urllib.request.Request(URL, headers={
        "Accept": "text/html",
        "User-Agent": "PLASMA-Phase1-Source-Research/1.0",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        last = r.geturl()
        require(r.status == 200 and authorized(last),
                f"official chart redirect invalid: status={r.status} "
                f"host={urllib.parse.urlparse(last).hostname} "
                f"path={urllib.parse.urlparse(last).path}")
        return r.read(LIMIT + 1)


def capture(path, getter=get_bytes):
    root = Path(path)
    require(not root.exists(), "original source directory already exists")
    root.mkdir(parents=True)
    manifest = {
        "schema_version": 1, "policy": "ADR-0002 Phase 1",
        "source_url": URL, "source_type": "manufacturer_parametric_html_chart",
        "chart_scope": "MicrochipDirect branchID=21 mid=3; not all Microchip products",
        "original_response_retained": False,
        "capture_outcome": "SOURCE_NOT_AVAILABLE",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": None, "error": None,
        "production_write_authorized": False,
        "software_supported_claimed": False,
    }
    try:
        raw = getter()
        evidence = validate_html(raw)
        (root / "original-chart.html").write_bytes(raw)
        manifest["source"] = evidence
        manifest["original_response_retained"] = True
        manifest["capture_outcome"] = "CAPTURED_NOT_SEMANTICALLY_VERIFIED"
    except (OSError, ValueError, urllib.error.URLError) as exc:
        manifest["error"] = f"{type(exc).__name__}: {exc}"
    (root / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    require(manifest["original_response_retained"],
            "SOURCE_NOT_AVAILABLE: " + str(manifest["error"]))
    return replay(root)


def replay(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    require(manifest.get("schema_version") == 1
            and manifest.get("policy") == "ADR-0002 Phase 1"
            and manifest.get("source_url") == URL
            and manifest.get("source_type") == "manufacturer_parametric_html_chart"
            and manifest.get("capture_outcome") == "CAPTURED_NOT_SEMANTICALLY_VERIFIED"
            and manifest.get("original_response_retained") is True
            and manifest.get("production_write_authorized") is False
            and manifest.get("software_supported_claimed") is False,
            "source not captured or manifest inconsistent")
    actual = validate_html((root / "original-chart.html").read_bytes())
    require(actual == manifest["source"], "original HTML source integrity mismatch")
    return {
        **actual, "capture_outcome": manifest["capture_outcome"],
        "source_url": URL, "chart_scope": manifest["chart_scope"],
        "no_exact_icpn_admission": True,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture", type=Path)
    mode.add_argument("--replay", type=Path)
    args = p.parse_args()
    root = args.capture or args.replay
    require("production" not in [x.casefold() for x in root.resolve().parts],
            "Production output path prohibited")
    result = capture(args.capture) if args.capture else replay(args.replay)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
