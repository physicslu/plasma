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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_CSV = HERE / "stm32u5-base-device-discovery.csv"
USER_AGENT = "Mozilla/5.0 (compatible; PlasmaDeviceCatalogResearch/1.0; +https://github.com/physicslu/plasma)"


def fetch(url: str, attempts: int = 4, timeout: int = 30) -> str:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Connection": "close",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                return raw.decode(charset, errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt != attempts:
                time.sleep(attempt * 2)
    raise RuntimeError(f"failed to fetch {url}: {last}")


def exact_tokens(base: str, page: str) -> list[str]:
    # Accept only literal tokens already present on the ST product page.
    # No ordering suffix is generated or completed by Plasma.
    text = html.unescape(page).upper()
    pattern = re.compile(rf"(?<![A-Z0-9]){re.escape(base)}[A-Z0-9]{{2,10}}(?![A-Z0-9])")
    return sorted(set(pattern.findall(text)))


def probe(row: dict[str, str], *, attempts: int = 4, timeout: int = 30) -> tuple[str, str, str, list[str]]:
    base = row["base_device"].strip().upper()
    subfamily = row["subfamily"].strip().upper()
    url = row["manufacturer_url"].strip()
    tokens = exact_tokens(base, fetch(url, attempts=attempts, timeout=timeout))
    if not tokens:
        raise RuntimeError(f"{base}: no exact manufacturer Part Number token observed")
    return base, subfamily, url, tokens


def append_result(
    result: tuple[str, str, str, list[str]],
    rows: list[dict[str, str]],
    per_base: dict[str, int],
    completed: int,
) -> int:
    base, subfamily, url, tokens = result
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
    completed += 1
    print(f"[{completed:02d}/74] {base}: {len(tokens)} exact tokens", flush=True)
    return completed


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
    failed_rows: list[dict[str, str]] = []
    completed = 0

    # Keep concurrency deliberately low. ST product pages are an evidence source,
    # not a load target, and transient throttling must not become false evidence.
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(probe, row): row for row in bases}
        for future in as_completed(futures):
            row = futures[future]
            try:
                result = future.result()
            except RuntimeError as exc:
                print(f"parallel probe deferred for serial retry: {row['base_device']}: {exc}", flush=True)
                failed_rows.append(row)
                continue
            completed = append_result(result, rows, per_base, completed)

    # Fail-closed fallback: retry every transient failure serially with a longer
    # timeout. No Base Device may be skipped and no missing row is treated as an
    # unsupported-device claim.
    for row in failed_rows:
        base = row["base_device"].strip().upper()
        print(f"serial fallback probe: {base}", flush=True)
        result = probe(row, attempts=6, timeout=60)
        completed = append_result(result, rows, per_base, completed)
        time.sleep(1)

    if completed != 74 or len(per_base) != 74:
        raise SystemExit(f"incomplete manufacturer observation: completed={completed}, unique_bases={len(per_base)}")

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
