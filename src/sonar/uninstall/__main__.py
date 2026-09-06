"""`sonar-uninstall` — Sonar'ı ve oluşturduğu her şeyi kaldırır.

Kullanıcının isteği (test turu 6): *"Kaldırma kısmını uygulama içerisine gömmüşsün. Fakat
istediğim bu değil. Bunun yerine ayrı bir uygulama gibi olsun. Bu çalıştığında terminalde
bir kod çalıştırsın. Kullanıcı eğer onay verirse sonar programıyla alakalı şeyleri
tamamen silsin. Hiç yüklenmemiş gibi olsun yani. Hiç bir şeyin yedeğini almasına gerek
yok."*

Uygulamanın içindeki pencereden farkı: o **geri alınabilir** bir işlem (sanal kanalları
söker, ayarlar durur), bu ise kalıcı. İkisi ayrı durduğu için karışmıyorlar.

## Sıra önemli

1. **Sanal kanallar** — daemon çalışıyorken sökülüyor ki varsayılan ses cihazı düzgün
   geri verilsin. Daemon'ı önce öldürüp sonra silseydik, sistem varsayılanı Sonar'ın
   silinmiş sink'ini göstermeye devam ederdi.
2. **Servis** — durdurulup devre dışı bırakılıyor.
3. **Dosyalar** — yapılandırma, durum, autostart girdisi.
4. **Root'a ait olanlar** — udev kuralı ve paketin kendisi. Bunları biz çalıştırmıyoruz;
   komutu gösterip **izin istiyoruz**, kullanıcı reddederse yalnızca yazıyoruz.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from sonar.core import autostart, i18n
from sonar.core import config as config_mod

__all__ = ["main"]

UDEV_RULE = Path("/etc/udev/rules.d/60-sonar-headset.rules")


def _daemon_call(method: str, *args: object) -> dict | None:
    """Daemon'a D-Bus çağrısı. Daemon yoksa `None` — kaldırma yine de sürüyor."""
    try:
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtDBus import QDBus, QDBusConnection, QDBusInterface

        from sonar.daemon.dbus_iface import BUS_NAME, INTERFACE, OBJECT_PATH
    except ImportError:  # pragma: no cover - PySide6 yoksa kaldırma yine çalışsın
        return None

    QCoreApplication.instance() or QCoreApplication([])
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return None
    iface = QDBusInterface(BUS_NAME, OBJECT_PATH, INTERFACE, bus)
    if not iface.isValid():
        return None
    message = iface.callWithArgumentList(QDBus.CallMode.Block, method, list(args))
    arguments = message.arguments()
    if not arguments:
        return None
    try:
        return json.loads(arguments[0])
    except (TypeError, json.JSONDecodeError):
        return None


def _run(*command: str) -> bool:
    try:
        return subprocess.run(command, check=False, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _ask(question: str) -> bool:
    """Evet/hayır sorusu. Boş yanıt = hayır; yıkıcı işlem varsayılan olmamalı."""
    try:
        answer = input(f"{question} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in {"e", "evet", "y", "yes"}


def _targets(paths: config_mod.Paths) -> list[tuple[str, Path]]:
    return [
        (i18n.t("uninstall.item.config"), paths.config_dir),
        (i18n.t("uninstall.item.state"), paths.state_dir),
        (i18n.t("uninstall.item.autostart"), autostart.autostart_path()),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sonar-uninstall", description=i18n.t("uninstall.title"))
    parser.add_argument("--yes", action="store_true", help=i18n.t("uninstall.help.yes"))
    args = parser.parse_args(argv)

    paths = config_mod.Paths.default()
    i18n.set_language(config_mod.ConfigStore(paths).load(create_missing=False).settings.language)

    print(i18n.t("uninstall.heading"))
    print()
    for label, path in _targets(paths):
        mark = "·" if path.exists() else " "
        print(f"  {mark} {label:<28} {path}")
    print(f"  · {i18n.t('uninstall.item.channels'):<28} {i18n.t('uninstall.item.channels.note')}")
    print(f"  · {i18n.t('uninstall.item.service'):<28} {autostart.SERVICE_NAME}")
    print()

    if not args.yes and not _ask(i18n.t("uninstall.confirm.prompt")):
        print(i18n.t("uninstall.aborted"))
        return 1

    # 1) Sanal kanallar — daemon ayaktayken, ki varsayılan cihaz geri verilsin.
    print(i18n.t("uninstall.step.channels"))
    result = _daemon_call("Deprovision", True)
    if result is None:
        print("  " + i18n.t("uninstall.no_daemon"))

    # 2) Servis
    print(i18n.t("uninstall.step.service"))
    _run("systemctl", "--user", "stop", autostart.SERVICE_NAME)
    _run("systemctl", "--user", "disable", autostart.SERVICE_NAME)

    # 3) Dosyalar
    print(i18n.t("uninstall.step.files"))
    for label, path in _targets(paths):
        if not path.exists():
            continue
        try:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
            print(f"  ✓ {label}")
        except OSError as error:
            print(f"  ✗ {label}: {error}", file=sys.stderr)

    # 4) Root'a ait olanlar
    print()
    print(i18n.t("uninstall.step.root"))
    if UDEV_RULE.exists():
        command = ("sudo", "rm", "-f", str(UDEV_RULE))
        print("  " + " ".join(command))
        if args.yes or _ask(i18n.t("uninstall.confirm.udev")):
            _run(*command)
            _run("sudo", "udevadm", "control", "--reload")

    if shutil.which("pacman") and _installed_by_pacman():
        print("  sudo pacman -Rns sonar-linux")
        if args.yes or _ask(i18n.t("uninstall.confirm.package")):
            _run("sudo", "pacman", "-Rns", "--noconfirm", "sonar-linux")
    else:
        print("  " + i18n.t("uninstall.package.manual"))

    print()
    print(i18n.t("uninstall.done"))
    return 0


def _installed_by_pacman() -> bool:
    try:
        return subprocess.run(
            ["pacman", "-Qq", "sonar-linux"],
            capture_output=True,
            check=False,
            timeout=10,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
