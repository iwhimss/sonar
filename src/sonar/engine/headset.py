"""Donanım ChatMix tekerinin tespiti.

## Durum: tespit var, okuma yok — nedeni

Plan, kulaklığın fiziksel ChatMix tekerini yazılım slider'ına bağlamayı istiyordu. Bu
makinedeki cihaz (SteelSeries **Arctis 7+**, `1038:220e`) araştırıldığında:

* PipeWire cihazı **tek** çıkış + **tek** giriş olarak görüyor. Planın öngördüğü "Game ve
  Chat ayrı iki USB ses cihazı" durumu geçerli değil; teker ALSA'da bir kontrol olarak
  görünmüyor.
* Teker konumu HID üzerinden geliyor ve `/dev/hidraw*` düğümleri `crw------- root root`;
  kullanıcı okuyamıyor.

Yani teker okumak iki şey gerektiriyor: (1) bir udev kuralı, (2) cihaza özel HID rapor
biçiminin çözülmesi. İkincisi cihazdan okumadan **doğrulanamaz**, doğrulanmamış bir protokol
yazmak da HID'e körlemesine veri göndermek anlamına gelir. Bu yüzden burada yalnızca
**tespit** var: cihaz duruyor mu, erişilebilir mi, kullanıcıya ne söylenmeli.

Kural kurulduktan sonra rapor biçimini çözmek küçük bir iş; `.plan/99-backlog.md`'de kayıtlı.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "KNOWN_HEADSETS",
    "UDEV_RULE",
    "HeadsetInfo",
    "detect_headsets",
    "parse_hid_id",
]

#: Donanım ChatMix tekeri olduğu bilinen kulaklıklar: `(vendor, product) → ad`.
#: Hepsi SteelSeries; teker konumu HID üzerinden geliyor.
KNOWN_HEADSETS: dict[tuple[int, int], str] = {
    (0x1038, 0x220E): "SteelSeries Arctis 7+",
    (0x1038, 0x12AD): "SteelSeries Arctis 7 (2019)",
    (0x1038, 0x1260): "SteelSeries Arctis 7 (2017)",
    (0x1038, 0x2202): "SteelSeries Arctis Nova 7",
    (0x1038, 0x12B3): "SteelSeries Arctis 1 Wireless",
}

_SYS_HIDRAW = Path("/sys/class/hidraw")

UDEV_RULE = """\
# Sonar — kulaklığın ChatMix tekerini okuyabilmek için HID erişimi.
# Kurulum:  sudo cp packaging/99-sonar-headset.rules /etc/udev/rules.d/
#           sudo udevadm control --reload && sudo udevadm trigger
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1038", MODE="0660", TAG+="uaccess"
"""


@dataclass(frozen=True, slots=True)
class HeadsetInfo:
    """Bulunan bir kulaklığın HID düğümü."""

    device: str  # /dev/hidrawN
    vendor: int
    product: int
    name: str
    readable: bool

    @property
    def hint(self) -> str:
        """Kullanıcıya gösterilecek mesaj."""
        if self.readable:
            return (
                f"{self.name} bulundu ve erişilebilir. Donanım tekerinin okunması henüz "
                f"uygulanmadı; yazılım ChatMix'i çalışmaya devam ediyor."
            )
        return (
            f"{self.name} bulundu ama {self.device} okunamıyor. Donanım ChatMix tekeri için "
            f"udev kuralı gerekiyor: packaging/99-sonar-headset.rules"
        )


def parse_hid_id(value: str) -> tuple[int, int] | None:
    """`HID_ID=0003:00001038:0000220E` → `(0x1038, 0x220e)`."""
    parts = value.strip().split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[1], 16), int(parts[2], 16)
    except ValueError:
        return None


def detect_headsets(root: Path | None = None) -> list[HeadsetInfo]:
    """Bilinen kulaklıkların HID düğümlerini bulur. Bulamazsa boş liste — hata değil."""
    base = root if root is not None else _SYS_HIDRAW
    found: list[HeadsetInfo] = []
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return found

    for entry in entries:
        uevent = entry / "device" / "uevent"
        try:
            text = uevent.read_text(errors="replace")
        except OSError:
            continue
        ids = next(
            (
                parse_hid_id(line.split("=", 1)[1])
                for line in text.splitlines()
                if line.startswith("HID_ID=")
            ),
            None,
        )
        if ids is None or ids not in KNOWN_HEADSETS:
            continue
        device = f"/dev/{entry.name}"
        found.append(
            HeadsetInfo(
                device=device,
                vendor=ids[0],
                product=ids[1],
                name=KNOWN_HEADSETS[ids],
                readable=os.access(device, os.R_OK),
            )
        )
    return found
