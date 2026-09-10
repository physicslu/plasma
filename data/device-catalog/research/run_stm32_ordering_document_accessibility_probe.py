#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from st_dual_surface_browser_acquisition import STDualSurfaceBrowserAcquirer
from st_product_page_acquisition import AcquisitionError
from stm32_ordering_document_accessibility_probe import DEFAULT_MANIFEST, probe_is_clean, read_manifest, run_probe

DEFAULT_OUTPUT = Path("/tmp/stm32-ordering-document-accessibility-summary.json")
MAX_PDF_BYTES = 32 * 1024 * 1024
PDF_TRANSPORT = "playwright_browser_context_request"


def _playwright_version() -> str:
    try:
        return version("playwright")
    except PackageNotFoundError:
        return "unknown"


def extract_pdf_text(body: bytes) -> str:
    process = subprocess.run(
        ["pdftotext", "-layout", "-", "-"],
        input=body,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise AcquisitionError("pdftotext failed: " + process.stderr.decode("utf-8", errors="replace")[-500:])
    return process.stdout.decode("utf-8", errors="strict")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args(argv)

    pilot, targets = read_manifest(args.manifest)
    base_by_url = {target.product_url: target.base_device for target in targets}
    pdf_by_url: dict[str, tuple[bytes, str, str | None]] = {}
    text_by_sha: dict[str, str] = {}

    def saving_text_extractor(body: bytes) -> str:
        text = extract_pdf_text(body)
        text_by_sha[hashlib.sha256(body).hexdigest()] = text
        return text

    with STDualSurfaceBrowserAcquirer(base_by_url=base_by_url, family_label="STM32U0/C0 ordering-document probe", headless=False) as acquirer:
        def saving_pdf_fetcher(url: str, timeout: float) -> tuple[bytes, str, str | None]:
            browser = getattr(acquirer, "_browser", None)
            if browser is None:
                raise AcquisitionError("browser PDF fetch requires an active product-page browser")
            context = browser.new_context()
            try:
                response = context.request.get(
                    url,
                    timeout=int(min(timeout, 45.0) * 1000),
                    fail_on_status_code=False,
                    headers={"Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8", "Referer": "https://www.st.com/"},
                )
                if response.status == 404:
                    raise AcquisitionError("datasheet HTTP 404")
                if response.status >= 400:
                    raise AcquisitionError(f"datasheet HTTP {response.status}")
                body = response.body()
                if len(body) > MAX_PDF_BYTES:
                    raise AcquisitionError(f"datasheet exceeds {MAX_PDF_BYTES} bytes")
                result = (body, response.url, response.headers.get("content-type"))
                pdf_by_url[url] = result
                return result
            except AcquisitionError:
                raise
            except Exception as exc:
                raise AcquisitionError(f"browser-context datasheet fetch failed: {type(exc).__name__}: {exc}") from exc
            finally:
                context.close()

        summary = run_probe(
            pilot_id=pilot,
            targets=targets,
            product_fetcher=acquirer.fetch,
            pdf_fetcher=saving_pdf_fetcher,
            text_extractor=saving_text_extractor,
            timeout_seconds=args.timeout,
        )
        summary["browser"] = {
            "headless": False,
            "browser_version": acquirer.browser_version,
            "playwright_version": _playwright_version(),
        }
        summary["pdf_transport"] = PDF_TRANSPORT
        summary["pdf_text_tool"] = "pdftotext -layout"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.evidence_dir is not None:
        args.evidence_dir.mkdir(parents=True, exist_ok=True)
        for result in summary["results"]:
            if result.get("disposition") != "accessible":
                continue
            base = str(result["base_device"])
            url = str(result["datasheet_url"])
            body = pdf_by_url[url][0]
            digest = hashlib.sha256(body).hexdigest()
            (args.evidence_dir / f"{base}.pdf").write_bytes(body)
            (args.evidence_dir / f"{base}.txt").write_text(text_by_sha[digest], encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if probe_is_clean(summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
