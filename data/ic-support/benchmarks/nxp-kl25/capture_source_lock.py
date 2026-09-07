#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "source-acquisition-contract.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture exact NXP KL25 manufacturer PDF identities into a source lock")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE / "source-lock.json")
    args = parser.parse_args()

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    locked_sources = []
    for source in contract["sources"]:
        path = args.source_dir / source["local_filename"]
        if not path.is_file():
            raise SystemExit(f"missing required source: {path}")
        locked_sources.append({
            "source_id": source["source_id"],
            "authority": source["authority"],
            "document_role": source["document_role"],
            "document_number": source["document_number"],
            "revision": source["revision"],
            "requested_url": source["official_url"],
            "final_url": source["official_url"],
            "local_filename": source["local_filename"],
            "integrity": {
                "algorithm": "sha256",
                "digest": sha256_file(path),
                "byte_length": path.stat().st_size
            }
        })

    output = {
        "schema_version": "0.1.0",
        "source_lock_id": "nxp-kl25-source-lock-v0",
        "benchmark_id": contract["benchmark_id"],
        "targets": [contract["target"]],
        "sources": locked_sources,
        "trust_boundary": {
            "source_lock_complete": True,
            "evidence_pack_admission": False,
            "canonical_dataset_admission": False,
            "production_admission": False
        }
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    for source in locked_sources:
        print(f"{source['source_id']} {source['integrity']['digest']} {source['integrity']['byte_length']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
