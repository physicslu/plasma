from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "z2like-demo-browser-live-acceptance.py"


def test_live_acceptance_script_parses_and_defines_main() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert "run" in functions
    assert "main" in functions
    assert "_upload_and_deploy" in functions
    assert "_wait_public_deployment" in functions


def test_live_acceptance_uses_bounded_chunk_size_under_bff_limit() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "CHUNK_BYTES = 768 * 1024" in source
    assert "data_base64" in source
    assert "sha256" in source
