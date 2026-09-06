"""Oturum açılışında başlatma.

`core.autostart` iki ayrı mekanizmayı yönetiyor — systemd user unit'i (ses düzeni) ve XDG
autostart girdisi (arayüz, tepside). Testler ikisinin de **gerçek kaynağı** okuduğunu ve
kurulu olmayan bir sistemde sessizce başarısız olmadığını doğruluyor.
"""

from __future__ import annotations

import subprocess

import pytest

from sonar.core import autostart


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Autostart girdisi geçici bir `XDG_CONFIG_HOME` altına yazılsın."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


def test_autostart_path_follows_xdg(home):
    path = autostart.autostart_path()
    assert path.parent.name == "autostart"
    assert path.name == autostart.DESKTOP_ID
    assert str(home) in str(path)


def test_gui_autostart_is_written_from_the_installed_shortcut(home, monkeypatch):
    """Girdi kurulu `.desktop`'tan türetiliyor: ad ve ikon tek kaynaktan gelsin."""
    installed = home / "apps" / autostart.DESKTOP_ID
    installed.parent.mkdir(parents=True)
    installed.write_text(
        "[Desktop Entry]\nType=Application\nName=Sonar\nExec=sonar\nIcon=x\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(autostart, "_DESKTOP_DIRS", (installed.parent,))

    autostart.set_gui_enabled(True)

    assert autostart.is_gui_enabled() is True
    written = autostart.autostart_path().read_text(encoding="utf-8")
    # Pencere açılmadan tepside beklesin.
    assert "Exec=sonar --minimized" in written
    assert "Name=Sonar" in written

    autostart.set_gui_enabled(False)
    assert autostart.is_gui_enabled() is False


def test_gui_autostart_says_why_it_cannot_be_enabled(home, monkeypatch):
    """Depodan çalıştırırken kısayol kurulu değil — sessizce başarısız olmamalı."""
    monkeypatch.setattr(autostart, "_DESKTOP_DIRS", (home / "yok",))
    with pytest.raises(autostart.AutostartError, match="kısayol"):
        autostart.set_gui_enabled(True)


def test_disabling_the_gui_autostart_is_idempotent(home, monkeypatch):
    monkeypatch.setattr(autostart, "_DESKTOP_DIRS", (home / "yok",))
    autostart.set_gui_enabled(False)  # dosya zaten yok
    assert autostart.is_gui_enabled() is False


def test_daemon_state_comes_from_systemd_not_the_setting(monkeypatch):
    """`config.toml`'daki bayrak yalnızca niyeti saklıyor; gerçek durum systemd'de."""
    calls: list[tuple[str, ...]] = []

    def fake(*args, **kwargs):
        calls.append(tuple(args[0]))
        return subprocess.CompletedProcess(args[0], 0, stdout="enabled\n", stderr="")

    monkeypatch.setattr(autostart.subprocess, "run", fake)
    monkeypatch.setattr(autostart.shutil, "which", lambda _name: "/usr/bin/systemctl")

    assert autostart.is_daemon_enabled() is True
    assert calls[0][:3] == ("systemctl", "--user", "is-enabled")


def test_enabling_the_daemon_reports_systemd_failures(monkeypatch):
    """Unit kurulu değilse `systemctl` hata veriyor; bunu yutmak kullanıcıyı yanıltırdı."""

    def fake(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, stdout="", stderr="Unit not found.")

    monkeypatch.setattr(autostart.subprocess, "run", fake)
    monkeypatch.setattr(autostart.shutil, "which", lambda _name: "/usr/bin/systemctl")

    with pytest.raises(autostart.AutostartError, match="Unit not found"):
        autostart.set_daemon_enabled(True)


def test_enabling_does_not_start_or_stop_the_running_daemon(monkeypatch):
    """`--now` kullanılmıyor: "açılışta başlasın" demek çalışanı durdurmak değil."""
    calls: list[tuple[str, ...]] = []

    def fake(*args, **kwargs):
        calls.append(tuple(args[0]))
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr(autostart.subprocess, "run", fake)
    monkeypatch.setattr(autostart.shutil, "which", lambda _name: "/usr/bin/systemctl")

    autostart.set_daemon_enabled(False)

    assert calls == [("systemctl", "--user", "disable", autostart.SERVICE_NAME)]
    assert not any("--now" in call for call in calls)
