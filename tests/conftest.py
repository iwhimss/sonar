from __future__ import annotations

import pytest

from sonar.core.config import ConfigStore, Paths


@pytest.fixture
def paths(tmp_path) -> Paths:
    return Paths(config_dir=tmp_path / "config", state_dir=tmp_path / "state")


@pytest.fixture
def config_store(paths: Paths) -> ConfigStore:
    return ConfigStore(paths)
