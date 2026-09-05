from __future__ import annotations

import pytest

from sonar.core.config import ConfigStore, Paths


@pytest.fixture
def paths(tmp_path) -> Paths:
    return Paths(config_dir=tmp_path / "config", state_dir=tmp_path / "state")


@pytest.fixture
def config_store(paths: Paths) -> ConfigStore:
    return ConfigStore(paths)


@pytest.fixture(autouse=True)
def default_language():
    """Her test varsayılan dille başlasın.

    `sonar.core.i18n` süreç genelinde tek bir dil tutuyor; dil değiştiren bir test
    sonrakileri etkilerdi. Ayrıca geliştiricinin kendi `~/.config/sonar` dili testlerin
    beklediği metinleri değiştirmemeli.
    """
    from sonar.core import i18n

    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)
