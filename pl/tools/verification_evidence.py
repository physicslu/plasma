"""PLASMA Verification Platform v1: host-only pytest evidence runner/validator.

This tool does not open MMIO, invoke Vivado, access SWPC, deploy or load FPGA.
A receipt is measured evidence for one pytest wrapper, NOT a blanket SIM claim.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "pl/verification/verification-result-v1.schema.json"
SIM_NOT_TESTED = [
    "XSim and vendor-IP simulation (SIM-3)",
    "Vivado synthesis/implementation/timing (SIM-4)",
    "ARMv7 store width, DMB/DSB and Linux MMIO ordering",
    "physical PS7 AXI, SWPC, Z2/PPU, FPGA reload and DUT",
    "eight physically instantiated RTL Sites and real IC programming",
]
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")


class EvidenceError(RuntimeError):
    """Invalid or unsubstantiated verification claim."""


def _run_capture(args: list[str]) -> str:
    completed = subprocess.run(args, cwd=ROOT, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               check=True, timeout=30)
    return completed.stdout.strip()


def git_commit() -> str:
    sha = _run_capture(["git", "rev-parse", "HEAD"])
    if not SHA40.fullmatch(sha):
        raise EvidenceError("HEAD is not a full immutable Git SHA")
    expected = os.getenv("GITHUB_SHA")
    if expected and expected != sha:
        raise EvidenceError("GITHUB_SHA differs from checked-out Git HEAD")
    return sha


def _under_root(path: str) -> tuple[Path, str]:
    absolute = (ROOT / path).resolve()
    if not absolute.is_relative_to(ROOT) or absolute == ROOT:
        raise EvidenceError("Source/suite escapes repository: " + path)
    rel = absolute.relative_to(ROOT).as_posix()
    return absolute, rel


def source_fingerprint(paths: list[str]) -> tuple[list[dict], str]:
    if not paths:
        raise EvidenceError("Explicit RTL source list required")
    records = []
    for item in paths:
        path, relative = _under_root(item)
        if not path.is_file() or path.is_symlink() or not relative.endswith(".sv"):
            raise EvidenceError("Missing/non-regular RTL source: " + relative)
        records.append({"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    records.sort(key=lambda x: x["path"])
    if len({x["path"] for x in records}) != len(records):
        raise EvidenceError("Duplicate RTL source")
    digest = hashlib.sha256()
    for item in records:
        digest.update((item["path"] + "\0" + item["sha256"] + "\n").encode())
    return records, digest.hexdigest()


def assert_pilot_source_contract(suite_path: Path, sources: list[dict],
                                 expected_top: str) -> None:
    """Fail closed unless the receipt exactly matches the RTL that Cocotb compiles.

    First SIM-2 pilot supports the static Cocotb-test runner shape already
    used in this repository; unsupported shapes MUST NOT receive a PASS.
    """
    tree = ast.parse(suite_path.read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and
             isinstance(node.func, ast.Name) and node.func.id == "run"]
    if len(calls) != 1:
        raise EvidenceError("Cannot prove exactly one Cocotb simulator invocation")
    fields = {kw.arg: kw.value for kw in calls[0].keywords}
    try:
        if (ast.literal_eval(fields["simulator"]) != "icarus" or
                ast.literal_eval(fields["toplevel"]) != expected_top):
            raise EvidenceError("RTL simulator/top mismatch with measured evidence")
        entries = fields["verilog_sources"].elts
        parsed = []
        for value in entries:
            if (not isinstance(value, ast.Call) or
                    not isinstance(value.func, ast.Name) or
                    value.func.id != "str" or len(value.args) != 1):
                raise EvidenceError("Unsupported simulator RTL source expression")
            term = value.args[0]
            if (not isinstance(term, ast.BinOp) or
                    not isinstance(term.op, ast.Div) or
                    not isinstance(term.left, ast.Name) or
                    term.left.id != "PL" or
                    not isinstance(term.right, ast.Constant) or
                    not isinstance(term.right.value, str)):
                raise EvidenceError("Cannot prove simulator's RTL source path")
            actual, rel = _under_root("pl/" + term.right.value)
            if not actual.is_file():
                raise EvidenceError("Simulator source file missing: " + rel)
            parsed.append(rel)
        if len(set(parsed)) != len(parsed) or sorted(parsed) != [
                item["path"] for item in sources]:
            raise EvidenceError("Receipt RTL list differs from real Cocotb compilation")
    except (KeyError, AttributeError, ValueError, TypeError) as exc:
        raise EvidenceError("Cannot inspect Cocotb compile inputs fail-closed") from exc


def measured_tools() -> dict:
    def package(name: str) -> str:
        return importlib.metadata.version(name)
    output = _run_capture(["iverilog", "-V"])
    match = re.search(r"Icarus Verilog version\s+([0-9]+(?:\.[0-9]+)+)", output)
    if not match:
        raise EvidenceError("Cannot measure exact Icarus version")
    return {"python": platform.python_version(), "pytest": package("pytest"),
            "cocotb": package("cocotb"), "cocotb_test": package("cocotb-test"),
            "simulator": "Icarus Verilog " + match.group(1)}


def junit_counts(path: Path) -> dict:
    if not path.is_file():
        raise EvidenceError("JUnit XML was not emitted by pytest")
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    if not cases:
        raise EvidenceError("JUnit XML contained zero actual test cases")
    failed = sum(case.find("failure") is not None for case in cases)
    errors = sum(case.find("error") is not None for case in cases)
    skipped = sum(case.find("skipped") is not None for case in cases)
    return {"passed": len(cases) - failed - errors - skipped,
            "failed": failed, "errors": errors, "skipped": skipped}


def _validate_semantics(doc: dict, *, verify_source: bool) -> None:
    status, counts, code = doc["status"], doc["test_counts"], doc["exit_code"]
    if status == "PASS":
        if (code != 0 or counts["passed"] < 1 or counts["failed"] or
            counts["errors"] or doc["reason"] or
            not all(doc["tools"].values()) or
            not doc["rtl_top"] or not doc["driver_module"] and doc["stage"] == "SIM-2" or
            not doc["rtl_source_digest"] or not doc["rtl_sources"] or
            not doc["claims"]):
            raise EvidenceError("A PASS must have actual successful tests, versions and sources")
    elif status == "FAIL":
        if code is None or code == 0 or doc["claims"]:
            raise EvidenceError("FAIL requires non-zero test exit and no PASS claims")
    else:
        if code is not None or any(counts.values()) or doc["claims"] or not doc["reason"]:
            raise EvidenceError("NOT_RUN/BLOCKED must have no executed-test PASS claims")
    if doc["stage"] == "SIM-2" and doc["runner_class"] == "authorized-hil":
        raise EvidenceError("SIM-2 Host-only receipt cannot imply HIL")
    if doc["runner_class"] in ("github-hosted", "local-host-only"):
        if not set(SIM_NOT_TESTED).issubset(doc["not_tested"]):
            raise EvidenceError("Mandatory nonclaims are missing for host-only evidence")
    if doc["rtl_sources"]:
        entries = [x["path"] for x in doc["rtl_sources"]]
        if entries != sorted(set(entries)):
            raise EvidenceError("RTL source listing must be sorted and unique")
        for entry in doc["rtl_sources"]:
            _under_root(entry["path"])
    if verify_source and doc["rtl_sources"]:
        actual, digest = source_fingerprint([x["path"] for x in doc["rtl_sources"]])
        if actual != doc["rtl_sources"] or digest != doc["rtl_source_digest"]:
            raise EvidenceError("Source digest does not match current checkout")


def _schema_check(value: object, schema: dict, *, where: str = "$") -> None:
    """Validate the intentionally small Draft-2020-12 schema vocabulary.

    Avoid a new dependency for every legacy FPGA workflow. Refuse unknown
    schema keywords instead of silently treating an unimplemented rule as PASS.
    """
    allowed = {"$schema", "$id", "title", "description", "type", "const",
               "enum", "properties", "required", "additionalProperties",
               "minLength", "pattern", "minimum", "minItems", "uniqueItems", "items"}
    unknown = set(schema) - allowed
    if unknown:
        raise EvidenceError("Unsupported JSON Schema keywords: " + ", ".join(sorted(unknown)))

    names = schema.get("type")
    if names is not None:
        if isinstance(names, str):
            names = [names]
        check = {
            "object": lambda x: type(x) is dict,
            "array": lambda x: type(x) is list,
            "string": lambda x: type(x) is str,
            "integer": lambda x: type(x) is int,
            "null": lambda x: x is None,
            "boolean": lambda x: type(x) is bool,
        }
        if not isinstance(names, list) or not names or any(x not in check for x in names):
            raise EvidenceError("Unsupported type in JSON Schema at " + where)
        if not any(check[k](value) for k in names):
            raise EvidenceError(where + " does not match JSON Schema type")
    if "const" in schema and value != schema["const"]:
        raise EvidenceError(where + " violates schema const")
    if "enum" in schema and value not in schema["enum"]:
        raise EvidenceError(where + " is outside schema enum")

    if type(value) is dict:
        required = schema.get("required", [])
        if not set(required).issubset(value):
            raise EvidenceError(where + " missing required fields")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise EvidenceError(where + " contains unexpected fields")
        for key, child in properties.items():
            if key in value:
                _schema_check(value[key], child, where=where + "." + key)
    if type(value) is str:
        if len(value) < schema.get("minLength", 0):
            raise EvidenceError(where + " is shorter than minLength")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise EvidenceError(where + " violates schema pattern")
    if type(value) is int and value < schema.get("minimum", value):
        raise EvidenceError(where + " violates minimum")
    if type(value) is list:
        if len(value) < schema.get("minItems", 0):
            raise EvidenceError(where + " has fewer than minItems")
        if schema.get("uniqueItems") and len(
            {json.dumps(item, sort_keys=True) for item in value}
        ) != len(value):
            raise EvidenceError(where + " has duplicate items")
        if "items" in schema:
            for idx, item in enumerate(value):
                _schema_check(item, schema["items"], where=where + "[" + str(idx) + "]")


def validate_receipt(doc: dict, *, verify_source: bool = False) -> None:
    try:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError("Unable to read versioned evidence Schema") from exc
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise EvidenceError("Unexpected evidence JSON Schema dialect")
    _schema_check(doc, schema)
    _validate_semantics(doc, verify_source=verify_source)

def _report_path(value: str) -> Path:
    path, _ = _under_root(value)
    build = (ROOT / "pl/build").resolve()
    if not path.is_relative_to(build) or path == build:
        raise EvidenceError("Receipt output must remain beneath pl/build")
    return path


def _runner_identity() -> tuple[str, str]:
    if os.getenv("GITHUB_ACTIONS") == "true":
        # ImageOS/ImageVersion are observed runner metadata, not a pin.
        name = os.getenv("RUNNER_NAME")
        image = os.getenv("ImageOS")
        image_version = os.getenv("ImageVersion")
        if not name or not image or not image_version:
            raise EvidenceError("GitHub runner identity/image version unavailable")
        return "github-hosted", name + " / " + image + " / " + image_version
    return "local-host-only", platform.node() + " / " + platform.platform()


def _run_url() -> str | None:
    if os.getenv("GITHUB_ACTIONS") != "true":
        return None
    repo = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not run_id.isdigit():
        raise EvidenceError("Cannot authenticate GitHub run URL from environment")
    return "https://github.com/" + repo + "/actions/runs/" + run_id


def execute(args: argparse.Namespace) -> int:
    output = _report_path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    receipt_file = output / "verification-result.json"
    log_file = output / "pytest.stdout.log"
    xml_file = output / "pytest.junit.xml"
    tools_file = output / "measured-pip-freeze.txt"
    suite_path, suite = _under_root(args.suite)
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    receipt = {
        "schema_version": "plasma-verification-v1",
        "commit_sha": "0" * 40,
        "stage": args.stage, "status": "BLOCKED",
        "runner_class": "local-host-only", "runner_identity": "preflight-unavailable",
        "tools": {k: None for k in ("python", "pytest", "cocotb", "cocotb_test", "simulator")},
        "rtl_top": args.rtl_top, "rtl_source_digest": None, "rtl_sources": [],
        "driver_module": args.driver_module, "suite": suite, "test_counts": counts,
        "seed": args.seed, "ci_run_url": None,
        "artifacts": [str(log_file.relative_to(ROOT)), str(xml_file.relative_to(ROOT)),
                      str(tools_file.relative_to(ROOT))],
        "claims": [], "not_tested": list(SIM_NOT_TESTED),
        "exit_code": None, "reason": "Preflight did not finish",
    }
    try:
        receipt["commit_sha"] = git_commit()
        receipt["runner_class"], receipt["runner_identity"] = _runner_identity()
        receipt["ci_run_url"] = _run_url()
        if args.stage != "SIM-2":
            raise EvidenceError("Phase 2 pilot currently supports SIM-2 only")
        if not suite_path.is_file() or not suite.startswith("pl/verification/"):
            raise EvidenceError("Explicit pytest verification suite does not exist")
        receipt["rtl_sources"], receipt["rtl_source_digest"] = source_fingerprint(args.rtl_source)
        assert_pilot_source_contract(suite_path, receipt["rtl_sources"], args.rtl_top)
        receipt["tools"] = measured_tools()
        tools_file.write_text(_run_capture([sys.executable, "-m", "pip", "freeze"]) + "\n",
                              encoding="utf-8")
        cmd = [sys.executable, "-m", "pytest", "-q", suite,
               "--junitxml=" + str(xml_file)]
        with log_file.open("w", encoding="utf-8") as log:
            print("+ " + " ".join(cmd), flush=True)
            proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
            assert proc.stdout is not None
            for line in proc.stdout:
                print(line, end="", flush=True)
                log.write(line)
            code = proc.wait()
        receipt["exit_code"] = code
        receipt["test_counts"] = junit_counts(xml_file)
        if code == 0 and receipt["test_counts"]["passed"] > 0 and not (
            receipt["test_counts"]["failed"] or receipt["test_counts"]["errors"]
        ):
            receipt["status"] = "PASS"
            receipt["reason"] = None
            receipt["claims"] = [
                "Host-only pytest wrapper " + suite + " passed; nested Cocotb "
                "subcases are not separately counted by this JUnit receipt"
            ]
        else:
            receipt["status"] = "FAIL"
            receipt["reason"] = "pytest exit code " + str(code)
    except (EvidenceError, OSError, subprocess.SubprocessError, ET.ParseError,
            importlib.metadata.PackageNotFoundError) as exc:
        # If the pytest process failed without JUnit, retain FAIL, not false PASS.
        if receipt["exit_code"] is not None and receipt["exit_code"] != 0:
            receipt["status"] = "FAIL"
        else:
            receipt["status"] = "BLOCKED"
            receipt["exit_code"] = None
            receipt["test_counts"] = counts
        receipt["reason"] = type(exc).__name__ + ": " + str(exc)
    try:
        validate_receipt(receipt, verify_source=bool(receipt["rtl_sources"]))
    except EvidenceError as exc:
        print("Evidence validation failure: " + str(exc), file=sys.stderr)
        return 2
    receipt_file.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    print("EVIDENCE_STATUS=" + receipt["status"] +
          " EVIDENCE_RECEIPT=" + str(receipt_file.relative_to(ROOT)), flush=True)
    return 0 if receipt["status"] == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="PLASMA SIM-2 evidence pilot (Host-only)")
    sp = p.add_subparsers(dest="action", required=True)
    run = sp.add_parser("run", help="Run a real pytest suite and export one receipt")
    run.add_argument("--stage", choices=["SIM-2"], required=True)
    run.add_argument("--suite", required=True)
    run.add_argument("--rtl-top", required=True)
    run.add_argument("--rtl-source", action="append", required=True)
    run.add_argument("--driver-module", required=True)
    run.add_argument("--output-dir", required=True)
    run.add_argument("--seed", type=int)
    check = sp.add_parser("validate", help="Validate an existing immutable run receipt")
    check.add_argument("--receipt", required=True)
    check.add_argument("--verify-source", action="store_true")
    args = p.parse_args(argv)
    if args.action == "run":
        try:
            return execute(args)
        except EvidenceError as exc:
            print("Evidence runner refused: " + str(exc), file=sys.stderr)
            return 2
    try:
        doc = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
        validate_receipt(doc, verify_source=args.verify_source)
    except (EvidenceError, OSError, json.JSONDecodeError) as exc:
        print("EVIDENCE_INVALID: " + str(exc), file=sys.stderr)
        return 2
    print("EVIDENCE_VALID status=" + doc["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
