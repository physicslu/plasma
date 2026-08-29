from pathlib import Path

import pytest

from plasma_manager.config import ManagerConfigError, load_manager_config


def test_manager_config_rejects_duplicate_ppu_aliases(tmp_path: Path) -> None:
    config = tmp_path / "manager.yaml"
    config.write_text(
        """
manager:
  host: 127.0.0.1
ppus:
  - alias: ppu-a
    endpoint: http://127.0.0.1:18080
  - alias: ppu-a
    endpoint: http://127.0.0.1:18081
""".lstrip(),
        encoding="utf-8",
    )
    with pytest.raises(ManagerConfigError, match="PPU aliases must be unique"):
        load_manager_config(config)
