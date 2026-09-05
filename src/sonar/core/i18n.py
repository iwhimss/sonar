"""Çeviri katalogları ve dil seçimi.

Metinler `src/sonar/i18n/<kod>.json` altında düz `{"anahtar": "metin"}` sözlükleri hâlinde
durur. Üç süreç de (daemon, CLI, GUI) aynı katalogu okur; böylece bir hata mesajının
daemon'da ürettiği metinle arayüzün gösterdiği metin aynı kaynaktan gelir.

## Neden Qt'nin `.ts`/`qsTr` sistemi değil

Projenin derleme adımı yok. `.qm` üretmek `pyside6-lrelease` bağımlılığı ve paketleme
adımında bir derleme demekti. Ayrıca aynı metinler **daemon ve CLI** tarafında da
gerekiyor; Qt'nin çeviri sistemi orada ikinci bir katman olurdu. Düz JSON tek kaynak:
diff'lenebilir, `tests/test_i18n.py` ile bütünlüğü doğrulanabilir, çalışma zamanında
yeniden yüklenebilir.

## Eksik anahtar

Anahtar bulunamazsa **anahtarın kendisi** döner ve uyarı loglanır. Sessizce boş string
döndürmek arayüzde boş bir etiket bırakır ve fark edilmez; anahtarın kendisi ekranda
hemen göze batar. `tests/test_i18n.py` zaten iki katalogun anahtar kümelerinin birebir
eşit olmasını şart koşuyor, yani bu yol pratikte yalnızca yazım hatasında görülür.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

__all__ = [
    "DEFAULT_LANGUAGE",
    "LANGUAGES",
    "available",
    "catalog",
    "catalog_dir",
    "language",
    "normalize",
    "set_language",
    "t",
]

log = logging.getLogger(__name__)

#: Kullanıcı hiçbir şey seçmediyse. Kullanıcının açık isteği (test turu 5).
DEFAULT_LANGUAGE = "tr"

#: Desteklenen diller: kod → o dilin **kendi dilindeki** adı. Dil listesi hiçbir zaman
#: çevrilmez; "Türkçe" satırını arayan kişi arayüzü okuyamıyor olabilir.
LANGUAGES: dict[str, str] = {
    "tr": "Türkçe",
    "en": "English",
}

_catalogs: dict[str, dict[str, str]] = {}
_language = DEFAULT_LANGUAGE


def catalog_dir() -> Path:
    """Katalog dosyalarının kökü. Kurulu paketten de çalışır."""
    return Path(__file__).resolve().parent.parent / "i18n"


def normalize(code: str) -> str:
    """`tr_TR.UTF-8`, `TR`, `tr-TR` → `tr`. Tanınmayan dil varsayılana düşer."""
    base = str(code or "").strip().replace("-", "_").split("_")[0].split(".")[0].lower()
    return base if base in LANGUAGES else DEFAULT_LANGUAGE


def catalog(code: str) -> dict[str, str]:
    """Bir dilin kataloğu. İlk erişimde diskten okunur, sonra bellekte kalır."""
    code = normalize(code)
    cached = _catalogs.get(code)
    if cached is not None:
        return cached
    path = catalog_dir() / f"{code}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        log.error("çeviri kataloğu okunamadı (%s): %s", path, error)
        data = {}
    _catalogs[code] = data
    return data


def set_language(code: str) -> str:
    """Etkin dili değiştirir ve normalize edilmiş kodu döndürür."""
    global _language
    _language = normalize(code)
    catalog(_language)  # ilk `t()` çağrısında disk okuması olmasın
    return _language


def language() -> str:
    return _language


def available() -> list[dict[str, str]]:
    """Arayüzün dil seçicisi için: `[{"code": "tr", "label": "Türkçe"}, ...]`."""
    return [{"code": code, "label": label} for code, label in LANGUAGES.items()]


def t(key: str, /, **kwargs: object) -> str:
    """Anahtarı etkin dilde metne çevirir.

    `kwargs` verilirse `str.format` uygulanır. Biçimlendirme başarısız olursa (çeviride
    eksik veya fazla yer tutucu) ham metin döner — bir çeviri hatası yüzünden çağrının
    istisna atması, gösterilecek metnin kaybolmasından daha kötü.
    """
    if not key:
        # Boş anahtar bir hata değil: arayüzde "ipucu varsa göster" gibi koşullu
        # bağlamalar boş anahtarla da değerleniyor.
        return ""
    text = catalog(_language).get(key)
    if text is None:
        log.warning("çeviri yok: %s (%s)", key, _language)
        text = key
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        log.warning("çeviri biçimlendirilemedi: %s", key)
        return text
