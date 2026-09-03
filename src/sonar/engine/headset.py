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

import logging
import os
import select
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

__all__ = [
    "KNOWN_HEADSETS",
    "UDEV_RULE",
    "UDEV_RULE_NAME",
    "ChatMixReader",
    "HeadsetInfo",
    "decode_chatmix",
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

#: Kural dosyasının adı. **60** olması şart: `uaccess` etiketini gören ACL'i systemd'nin
#: `73-seat-late.rules` dosyası uyguluyor ve udev kuralları ad sırasına göre çalışıyor.
#: Dosya bir dönem `99-` adıyla duruyordu; kural kurulmasına rağmen `/dev/hidraw*`
#: erişilemez kalıyordu çünkü etiket ACL uygulandıktan **sonra** ekleniyordu (ölçüldü).
UDEV_RULE_NAME = "60-sonar-headset.rules"

UDEV_RULE = """\
# Sonar — kulaklığın ChatMix tekerini okuyabilmek için HID erişimi.
# Kurulum:  sudo cp packaging/60-sonar-headset.rules /etc/udev/rules.d/
#           sudo udevadm control --reload && sudo udevadm trigger
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1038", TAG+="uaccess"
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
            f"udev kuralı gerekiyor: packaging/{UDEV_RULE_NAME}"
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


# --------------------------------------------------------------------------- teker okuma


def decode_chatmix(report: bytes, product: int) -> float | None:
    """Bir HID raporundan ChatMix konumunu (0–100) çıkarır; tanımadıysa `None`.

    ## Durum: biçim henüz çözülmedi

    `/dev/hidraw*` düğümleri varsayılan olarak `root`'a kapalı, yani cihazdan tek bir
    rapor bile okunamıyor. Doğrulanmamış bir bayt düzeni yazmak, kullanıcının ChatMix'ini
    rastgele bir bayta bağlamak olurdu — sessizce yanlış çalışan bir özellik, hiç
    çalışmayandan kötüdür.

    Yol açık: `packaging/99-sonar-headset.rules` kurulduktan sonra
    `scripts/sonar-hid-capture` ile teker uçtan uca çevrilirken raporlar kaydediliyor,
    hangi baytın nasıl değiştiği görülüyor ve bu fonksiyon o ölçüme göre yazılıyor.
    Kaydedilen raporlar `tests/data/` altına konup testi onlarla yazılacak.

    Faz 9'da da aynı karar verilmişti; Faz 23'te kural kuruluyor ve iş buraya geliyor.
    """
    del report, product
    return None


class ChatMixReader:
    """Kulaklığın HID düğümünü dinleyen iş parçacığı.

    Cihaz gidince sessizce durur, gelince kendiliğinden bağlanır — kulaklık kapatılıp
    açıldığında kullanıcının hiçbir şey yapması gerekmesin diye.

    Değer değişimini `on_value(0..100)` ile bildirir. Aynı değeri tekrar tekrar
    yollamaz: teker gürültüsü saniyede onlarca D-Bus çağrısına dönüşmesin diye
    `epsilon`dan küçük değişimler yutulur.
    """

    #: Cihaz yokken yeniden deneme aralığı.
    RETRY_SECONDS = 3.0

    def __init__(
        self,
        on_value: Callable[[float], None],
        *,
        epsilon: float = 1.0,
        detect: Callable[[], list[HeadsetInfo]] | None = None,
    ) -> None:
        self.on_value = on_value
        self.epsilon = epsilon
        self._detect = detect if detect is not None else detect_headsets
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._last: float | None = None
        #: Son okuma denemesinin sonucu — arayüz "teker yönetiyor" rozetini buna bakarak
        #: gösteriyor. Yalnızca gerçekten değer geldiğinde `True`.
        self.active = False

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name="sonar-chatmix", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self.active = False

    # ------------------------------------------------------------------ iç kısım

    def _run(self) -> None:
        while not self._stopping.is_set():
            headset = next((h for h in self._detect() if h.readable), None)
            if headset is None:
                self.active = False
                if self._stopping.wait(self.RETRY_SECONDS):
                    return
                continue
            self._listen(headset)

    def _listen(self, headset: HeadsetInfo) -> None:
        try:
            fd = os.open(headset.device, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as error:
            log.debug("%s açılamadı: %s", headset.device, error)
            self._stopping.wait(self.RETRY_SECONDS)
            return
        try:
            while not self._stopping.is_set():
                ready, _, _ = select.select([fd], [], [], 1.0)
                if not ready:
                    continue
                try:
                    report = os.read(fd, 64)
                except OSError:
                    return  # cihaz gitti; dış döngü yeniden arar
                if not report:
                    continue
                self._handle(report, headset.product)
        finally:
            os.close(fd)
            self.active = False

    def _handle(self, report: bytes, product: int) -> None:
        value = decode_chatmix(report, product)
        if value is None:
            return
        value = min(max(value, 0.0), 100.0)
        if self._last is not None and abs(value - self._last) < self.epsilon:
            return
        self._last = value
        self.active = True
        try:
            self.on_value(value)
        except Exception:  # pragma: no cover - dinleyici hatası okumayı durdurmasın
            log.exception("ChatMix dinleyicisi hata verdi")
