"""Donanım ChatMix tekerinin tespiti ve okunması.

## Yol nasıl açıldı

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

Kural (`packaging/60-sonar-headset.rules`) kurulduktan sonra kullanıcı tekeri uçtan uca
çevirirken raporlar kaydedildi ve biçim çözüldü — bkz. `decode_chatmix`. Kayıt
`tests/data/arctis7plus-wheel.txt` içinde duruyor ve testin kaynağı o.

Kural dosyasının adının **60** olması şart; sebebi `UDEV_RULE_NAME` yorumunda.
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
    "CHATMIX_REPORT_ID",
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

#: Teker raporunun kimliği. Kullanıcının `sonar-hid-capture` kaydında teker çevrilirken
#: gelen **tek** rapor türü buydu.
CHATMIX_REPORT_ID = 0x45

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

    ## Biçim — kullanıcının kaydından çözüldü

    Arctis 7+ (`1038:220e`), 64 baytlık rapor, yalnızca ilk üç bayt anlamlı:

    ```
    45 64 01   bayt0 = 0x45 rapor kimliği, bayt1 = 100, bayt2 = 1     (bir uç)
    45 64 64   orta:    bayt1 = 100, bayt2 = 100
    45 00 64   öbür uç: bayt1 = 0,   bayt2 = 100
    ```

    İki bağımsız 0–100 kazancı: biri 100'de sabit dururken diğeri iniyor, teker ortayı
    geçince rol değişiyor. SteelSeries'in klasik ChatMix düzeni — teker bir kısma değil,
    iki kısma. Konum ikisinin farkından çıkıyor:

        konum = 50 + (chat - game) / 2

    0 = tamamen game, 50 = orta (iki kazanç da 100), 100 = tamamen chat.

    Aynı düğümden batarya/durum raporları da geliyor; onlar başka bir rapor kimliği
    taşıdığı için `None` dönüyoruz. **Tanımadığımız bir raporu tahmin etmiyoruz:**
    kullanıcının ChatMix'ini rastgele bir bayta bağlamak, sessizce yanlış çalışan bir
    özellik demek.

    Ham kayıt `tests/data/arctis7plus-wheel.txt` içinde; test onunla yazıldı.
    """
    del product  # bugün bilinen tüm SteelSeries kulaklıkları aynı raporu veriyor
    if len(report) < 3 or report[0] != CHATMIX_REPORT_ID:
        return None
    game, chat = report[1], report[2]
    if game > 100 or chat > 100:
        return None  # bu rapor kimliğini taşıyan başka bir şey; kazanç değil
    return 50.0 + (chat - game) / 2.0


class ChatMixReader:
    """Kulaklığın HID düğümünü dinleyen iş parçacığı.

    Cihaz gidince sessizce durur, gelince kendiliğinden bağlanır — kulaklık kapatılıp
    açıldığında kullanıcının hiçbir şey yapması gerekmesin diye.

    Değer değişimini `on_value(0..100)` ile bildirir. Aynı değeri tekrar tekrar
    yollamaz: teker gürültüsü saniyede onlarca D-Bus çağrısına dönüşmesin diye
    `epsilon`dan küçük değişimler yutulur.

    Eşik 1.0'dan 2.0'a çıkarıldı: kullanıcının kaydında ardışık raporlar 120 ms arayla ve
    çoğu **1 birim** farkla geliyordu, yani eşik 1.0 hiçbir şeyi yutmuyordu. 2.0'da
    saniyede en fazla birkaç yazım kalıyor ve teker hâlâ akıcı görünüyor (%100'lük
    aralıkta 2 birim, 4 px'lik bir slider adımı).
    """

    #: Cihaz yokken yeniden deneme aralığı.
    RETRY_SECONDS = 3.0

    def __init__(
        self,
        on_value: Callable[[float], None],
        *,
        epsilon: float = 2.0,
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
            headsets = [h for h in self._detect() if h.readable]
            if not headsets:
                self.active = False
                if self._stopping.wait(self.RETRY_SECONDS):
                    return
                continue
            self._listen(headsets)

    def _listen(self, headsets: list[HeadsetInfo]) -> None:
        """Kulaklığın **tüm** HID düğümlerini aynı anda dinler.

        Tek düğüm seçmek yetmiyor: Arctis 7+ üç `hidraw` düğümü açıyor ve teker
        raporları yalnızca birinden (bu makinede `/dev/hidraw2`) geliyor. Reader eskiden
        ilk okunabilir düğümü seçiyordu — `/dev/hidraw0` — ve oradan hiç rapor gelmediği
        için sonsuza kadar sessizce bekliyordu. Hangi düğümün doğru olduğu cihaza ve
        çekirdek sıralamasına göre değişiyor, yani tahmin edilemez; hepsini dinleyip
        tanımadığımız raporları `decode_chatmix`'in elemesi hem basit hem doğru.
        """
        fds: dict[int, HeadsetInfo] = {}
        for headset in headsets:
            try:
                fds[os.open(headset.device, os.O_RDONLY | os.O_NONBLOCK)] = headset
            except OSError as error:
                log.debug("%s açılamadı: %s", headset.device, error)
        if not fds:
            self._stopping.wait(self.RETRY_SECONDS)
            return
        try:
            while not self._stopping.is_set():
                ready, _, _ = select.select(list(fds), [], [], 1.0)
                if not ready:
                    continue
                for fd in ready:
                    try:
                        report = os.read(fd, 64)
                    except OSError:
                        return  # cihaz gitti; dış döngü yeniden arar
                    if report:
                        self._handle(report, fds[fd].product)
        finally:
            for fd in fds:
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
