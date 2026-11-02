"""Host-only normative check for ADR-0004 FPGA build governance.

Policy presence is not proof of a real Vivado Project or SWPC build. Guard only
known MPE build inputs; the full reverse-dependency retirement audit is a
separate gated milestone.
"""
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "pl/projects/z2-mpe-dual-site"
ADR = ROOT / "docs/adr/0004-project-isolated-fpga-build-path2-operator-cli.md"
FORBIDDEN_BUILD_DEPS = (
    "pl/projects/z2-fixed-unified-site1/",
    "scripts/plasma_vivado_host_build.py",
    "fixed-site1-vivado-host-build",
    "fixed_ppu_z2_internal_fixture_axi",
    "swd03_dpidr_responder",
    "pl/projects/z2-swd03-axi/",
    "pl/projects/z2-swd-gpio/",
)


def inspect_new_build_source(path: Path, text: str) -> None:
    """Fail closed for MPE build Tcl/runner/selected manifest sources."""
    for obsolete in FORBIDDEN_BUILD_DEPS:
        if obsolete in text:
            raise AssertionError(f"F1B_OR_LEGACY_BUILD_DEPENDENCY: {path.name}: {obsolete}")


def test_owner_accepted_new_project_standard_is_explicit_not_an_active_build():
    adr = ADR.read_text(encoding="utf-8")
    agents = (ROOT / "pl/AGENTS.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs/development/fpga-development-guide.md").read_text(
        encoding="utf-8")
    mpe = (ROOT / "docs/architecture/plasma-mpe-dual-site-gate1.md").read_text(
        encoding="utf-8")
    index = (ROOT / "docs/adr/README.md").read_text(encoding="utf-8")

    assert "Status: Accepted" in adr
    assert "Path 2 `operator-cli`" in adr
    assert "pl/projects/<project-name>/" in adr
    assert "F1B_BUILD_ENGINE_RETIREMENT_PENDING" in adr
    assert "F1B_BUILD_ENGINE_RETIREMENT_PENDING" in agents
    assert "Path 2 `operator-cli`" in guide
    assert "F1B_BUILD_ENGINE_RETIREMENT_PENDING" in mpe
    assert "ADR-0004" in index
    assert "Build != Deploy" in adr
    assert "Host Build NOT_RUN" in adr
    assert "operator-cli" in mpe


def test_existing_mpe_project_inputs_dont_depend_on_f1b_specific_build_code():
    allowed = {".tcl", ".py", ".json", ".xdc", ".sv"}
    inputs = sorted(path for path in PROJECT.rglob("*")
                    if path.is_file() and path.suffix in allowed)
    assert inputs, "MPE must have a dedicated project ownership directory"
    for path in inputs:
        inspect_new_build_source(path, path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("obsolete", FORBIDDEN_BUILD_DEPS)
def test_new_build_guard_rejects_f1b_and_retired_single_site_sources(obsolete):
    with pytest.raises(AssertionError, match="F1B_OR_LEGACY_BUILD_DEPENDENCY"):
        inspect_new_build_source(Path("new-mpe-build.py"),
                                 f"source {obsolete}build_bitstream.tcl")


def test_no_false_claim_about_new_build_or_retirement():
    doc = ADR.read_text(encoding="utf-8")
    assert "F1B_BUILD_ENGINE_RETIREMENT_PENDING" in doc
    assert "Host Build NOT_RUN" in doc
    assert "NOT_RUN" in doc
    # As implementation progresses, a new Project Tcl is expected to appear.
    # Never make the contract itself reject a correct future implementation.
    build_tcl = PROJECT / "build_bitstream.tcl"
    if build_tcl.exists():
        inspect_new_build_source(build_tcl, build_tcl.read_text(encoding="utf-8"))
