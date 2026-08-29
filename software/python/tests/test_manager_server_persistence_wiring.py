from __future__ import annotations

from pathlib import Path

from plasma_manager.server import _build_observation_store


def test_manager_server_wires_optional_observation_persistence() -> None:
    source = Path(__file__).resolve().parents[1] / "plasma_manager" / "server.py"
    text = source.read_text(encoding="utf-8")
    assert "SQLiteObservationPersistence" in text
    assert "observation_db_path" in text
    assert "PS_LOOPBACK_ROUTE_PREFIX" in text
    assert '"/diagnostics/loopback"' in text
    assert "PPUHttpClient(entry.endpoint" in text
