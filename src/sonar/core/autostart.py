"""Oturum açılışında başlatma: systemd user unit'i ve XDG autostart girdisi.

İki ayrı şey var ve kullanıcı ikisini ayrı ayrı açıp kapatabiliyor:

* **Ses düzeni** — `sonar-daemon.service` systemd user unit'i. Açıkken oturum açılır
  açılmaz kanallar hazır oluyor, arayüz hiç açılmasa bile. SteelSeries GG'nin yaptığı da
  bu.
* **Arayüz** — `~/.config/autostart/` altındaki bir `.desktop` girdisi, `--minimized`
  ile. Pencere açılmıyor, uygulama tepside bekliyor.

## Neden ayarın kendisine güvenilmiyor

`config.toml`'daki bayrak yalnızca kullanıcının **niyetini** saklıyor. Gerçek durumu
systemd ve dosya sistemi belirliyor ve ikisi ayrışabilir: kullanıcı `systemctl --user
disable` diyebilir, paket kaldırılıp unit yok olabilir. Bu yüzden arayüz durumu
`is_daemon_enabled()` / `is_gui_enabled()` ile **gerçek kaynaktan** okuyor.

## Depodan çalıştırırken

Unit kurulu değilse `systemctl --user enable` başarısız olur. Bu bir hata değil, bilgi:
çağıran taraf sonucu kullanıcıya söylüyor, sessizce yutmuyor.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

__all__ = [
    "DESKTOP_ID",
    "SERVICE_NAME",
    "AutostartError",
    "autostart_path",
    "is_available",
    "is_daemon_enabled",
    "is_gui_enabled",
    "set_daemon_enabled",
    "set_gui_enabled",
]

log = logging.getLogger(__name__)

SERVICE_NAME = "sonar-daemon.service"
DESKTOP_ID = "io.github.iwhimss.Sonar.desktop"

#: Kurulu `.desktop` dosyasının aranacağı yerler; ilki paketin, ikincisi kullanıcı kurulumu.
_DESKTOP_DIRS = (
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local/share/applications",
)


class AutostartError(RuntimeError):
    """Otomatik başlatma değiştirilemedi — sebebi mesajda."""


def autostart_path() -> Path:
    """XDG autostart girdisinin yolu."""
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config").expanduser()
    return base / "autostart" / DESKTOP_ID


def _systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    if shutil.which("systemctl") is None:
        raise AutostartError("systemctl bulunamadı")
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def is_daemon_enabled() -> bool:
    """Unit oturum açılışında başlayacak mı — systemd'nin **kendi** cevabı."""
    try:
        result = _systemctl("is-enabled", SERVICE_NAME)
    except (AutostartError, OSError, subprocess.SubprocessError):
        return False
    return result.stdout.strip() == "enabled"


def set_daemon_enabled(enabled: bool) -> None:
    """Unit'i etkinleştirir/devre dışı bırakır. Başarısızlıkta `AutostartError`.

    `--now` **kullanılmıyor**: kullanıcı "oturum açılışında başlasın" derken çalışan
    daemon'ı durdurmayı kastetmiyor. Kapatmak yalnızca bir sonraki oturumu etkiliyor.
    """
    try:
        result = _systemctl("enable" if enabled else "disable", SERVICE_NAME)
    except (OSError, subprocess.SubprocessError) as error:
        raise AutostartError(str(error)) from error
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise AutostartError(message or f"systemctl {result.returncode} döndürdü")


def is_gui_enabled() -> bool:
    return autostart_path().exists()


def is_available() -> bool:
    """Otomatik başlatma **kurulabilir** mi: unit ve kısayol yerinde mi.

    Depodan çalıştırırken ikisi de yok; arayüz kutucukları pasifleştirip nedenini
    söylüyor, sessizce başarısız olmuyor.
    """
    if _installed_desktop_file() is None:
        return False
    try:
        return _systemctl("cat", SERVICE_NAME).returncode == 0
    except (AutostartError, OSError, subprocess.SubprocessError):
        return False


def set_gui_enabled(enabled: bool) -> None:
    """Arayüzü tepside açan XDG autostart girdisini yazar veya siler."""
    path = autostart_path()
    if not enabled:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            raise AutostartError(str(error)) from error
        return

    source = _installed_desktop_file()
    if source is None:
        raise AutostartError("uygulama kısayolu kurulu değil")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Kurulu girdiyi kopyalayıp `Exec`e `--minimized` ekliyoruz: pencere açılmadan
        # tepside beklesin. Adları ve ikonu kurulu dosyadan alıyoruz ki tek kaynak olsun.
        lines = []
        for line in source.read_text(encoding="utf-8").splitlines():
            if line.startswith("Exec="):
                line = f"{line} --minimized"
            lines.append(line)
        lines.append("X-GNOME-Autostart-enabled=true")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as error:
        raise AutostartError(str(error)) from error


def _installed_desktop_file() -> Path | None:
    for directory in _DESKTOP_DIRS:
        candidate = directory / DESKTOP_ID
        if candidate.is_file():
            return candidate
    return None
