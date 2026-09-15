#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_CSV = HERE / "stm32u5-base-device-discovery.csv"
USER_AGENT = "Mozilla/5.0 (compatible; PlasmaDeviceCatalogResearch/1.0; +https://github.com/physicslu/plasma)"


def fetch(url: str, attempts: int = 3) -> str:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                return raw.decode(charset, errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt != attempts:
                time.sleep(attempt * 2)
    raise RuntimeError(f"failed to fetch {url}: {last}")


def exact_tokens(base: str, page: str) -> list[str]:
    # Exact commercial order codes are accepted only when the literal token is
    # present on the manufacturer product page. We do not generate suffixes.
    text = html.unescape(page).upper()
    pattern = re.compile(rf"(?<![A-Z0-9]){re.escape(base)}[A-Z0-9]{{2,10}}(?![A-Z0-9])")
    tokens = sorted(set(pattern.findall(text)))
    return [token for token in tokens if token != base]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    with BASE_CSV.open(encoding="utf-8", newline="") as handle:
        bases = list(csv.DictReader(handle))
    if len(bases) != 74:
        raise SystemExit(f"expected 74 base devices, got {len(bases)}")

    rows: list[dict[str, str]] = []
    per_base: dict[str, int] = {}
    for index, row in enumerate(bases, 1):
        base = row["base_device"].strip().upper()
        subfamily = row["subfamily"].strip().upper()
        url = row["manufacturer_url"].strip()
        page = fetch(url)
        tokens = exact_tokens(base, page)
        if not tokens:
            raise SystemExit(f"{base}: no exact manufacturer Part Number token observed")
        per_base[base] = len(tokens)
        for token in tokens:
            rows.append(
                {
                    "exact_icpn": token,
                    "base_device": base,
                    "subfamily": subfamily,
                    "manufacturer_url": url,
                    "observation_scope": "literal_token_on_st_product_page",
                }
            )
        print(f"[{index:02d}/74] {base}: {len(tokens)} exact tokens")
        time.sleep(0.15)

    identities = sorted({row["exact_icpn"] for row in rows})
    if len(identities) != len(rows):
        raise SystemExit("duplicate exact ICPN observed across base devices")
    canonical = "\n".join(identities) + "\n"
    digest = hashlib.sha256(canonical.encode()).hexdigest()

    out_csv = Path(args.output_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["exact_icpn", "base_device", "subfamily", "manufacturer_url", "observation_scope"],
        )
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda value: value["exact_icpn"]))

    summary = {
        "schema_version": 1,
        "transaction": "stm32u5-exact-orderable-identity-probe",
        "authority": "manufacturer_web_observation",
        "observed_base_devices": len(bases),
        "base_devices_with_exact_identity": len(per_base),
        "exact_icpn_count": len(identities),
        "exact_icpn_set_sha256": digest,
        "per_base_counts": dict(sorted(per_base.items())),
        "synthesized_exact_icpns": 0,
    }
    Path(args.output_json).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
