from __future__ import annotations

from pathlib import Path

import pytest

from sonar.engine.headset import KNOWN_HEADSETS, detect_headsets, parse_hid_id


def make_hidraw(root, name: str, hid_id: str) -> None:
    device = root / name / "device"
    device.mkdir(parents=True)
    (device / "uevent").write_text(
        f"DRIVER=hid-generic\nHID_ID={hid_id}\nHID_NAME=Test Cihazı\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------- HID_ID


def test_parse_hid_id():
    assert parse_hid_id("0003:00001038:0000220E") == (0x1038, 0x220E)


def test_parse_hid_id_rejects_garbage():
    for value in ("", "abc", "0003:xyz:0000220E", "0003:00001038"):
        assert parse_hid_id(value) is None


# --------------------------------------------------------------------------- tespit


def test_known_headset_is_found(tmp_path):
    make_hidraw(tmp_path, "hidraw4", "0003:00001038:0000220E")
    found = detect_headsets(tmp_path)
    assert len(found) == 1
    assert found[0].name == "SteelSeries Arctis 7+"
    assert found[0].device == "/dev/hidraw4"


def test_unknown_device_is_ignored(tmp_path):
    make_hidraw(tmp_path, "hidraw0", "0003:0000046D:0000C52B")  # Logitech alıcı
    assert detect_headsets(tmp_path) == []


def test_multiple_interfaces_of_one_headset_are_all_listed(tmp_path):
    """Arctis 7+ üç hidraw düğümü açıyor; hangisinin doğru olduğu okunmadan bilinmiyor."""
    for index in (4, 5, 6):
        make_hidraw(tmp_path, f"hidraw{index}", "0003:00001038:0000220E")
    assert len(detect_headsets(tmp_path)) == 3


def test_missing_directory_is_not_an_error(tmp_path):
    assert detect_headsets(tmp_path / "yok") == []


def test_unreadable_uevent_is_skipped(tmp_path):
    (tmp_path / "hidraw9").mkdir()
    assert detect_headsets(tmp_path) == []


def test_hint_tells_the_user_what_to_do(tmp_path):
    make_hidraw(tmp_path, "hidraw4", "0003:00001038:0000220E")
    info = detect_headsets(tmp_path)[0]
    # Test ortamında /dev/hidraw4 yok → okunamaz sayılır.
    assert info.readable is False
    assert "udev" in info.hint


def test_catalogue_ids_are_plausible():
    for (vendor, product), name in KNOWN_HEADSETS.items():
        assert 0 < vendor <= 0xFFFF
        assert 0 < product <= 0xFFFF
        assert name


# --------------------------------------------------------------------------- teker okuma
#
# Bayt biçimi henüz çözülmedi (udev kuralı kurulmadan cihazdan tek rapor bile
# okunamıyor). Buradaki testler sürücü iskeletini koruyor: cihaz yokken sessizce
# beklemeli, çözülemeyen rapor hiçbir şey tetiklememeli.


def test_an_unknown_report_produces_no_value():
    from sonar.engine.headset import decode_chatmix

    assert decode_chatmix(b"\x00\x45\x32", 0x220E) is None


def test_the_reader_stays_quiet_without_a_readable_device():
    from sonar.engine.headset import ChatMixReader

    seen: list[float] = []
    reader = ChatMixReader(seen.append, detect=list)
    reader.start()
    reader.stop()
    assert seen == []
    assert reader.active is False


def test_repeated_values_are_swallowed():
    """Teker gürültüsü saniyede onlarca D-Bus çağrısına dönüşmemeli."""
    from sonar.engine import headset as mod
    from sonar.engine.headset import ChatMixReader

    seen: list[float] = []
    reader = ChatMixReader(seen.append, epsilon=2.0, detect=list)
    original = mod.decode_chatmix
    try:
        values = iter([50.0, 50.5, 51.0, 60.0])
        mod.decode_chatmix = lambda _report, _product: next(values)
        for _ in range(4):
            reader._handle(b"\x00", 0x220E)
    finally:
        mod.decode_chatmix = original
    assert seen == [50.0, 60.0]


# --------------------------------------------------------------------------- teker biçimi
#
# Aşağıdakiler kullanıcının gerçek kaydıyla yazıldı: `tests/data/arctis7plus-wheel.txt`,
# Arctis 7+ teker uçtan uca çevrilirken `sonar-hid-capture` ile alındı. Biçimi tahmin
# etmiyoruz — doğrulanmamış bir bayt düzeni, kullanıcının ChatMix'ini rastgele bir bayta
# bağlamak olurdu.

WHEEL_CAPTURE = Path(__file__).parent / "data" / "arctis7plus-wheel.txt"


def _captured_reports() -> list[bytes]:
    lines = [
        line
        for line in WHEEL_CAPTURE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return [bytes(int(part, 16) for part in line.split()) for line in lines]


def test_the_capture_is_intact():
    reports = _captured_reports()
    assert len(reports) == 35
    assert all(len(report) == 64 for report in reports)


def test_the_wheel_sweeps_from_one_end_to_the_other():
    """Kayıt uçtan uca bir çevrim: bir uç → orta → öbür uç."""
    from sonar.engine.headset import decode_chatmix

    values = [decode_chatmix(report, 0x220E) for report in _captured_reports()]
    assert None not in values
    assert values[0] == pytest.approx(0.5, abs=1.0)   # neredeyse tamamen bir uçta
    assert max(values) == 100.0                        # öbür uca kadar gitmiş
    assert 50.0 in values                              # ortadan geçmiş


def test_the_sweep_is_monotonic():
    """Teker tek yöne çevrildi; okunan konum geri gitmemeli.

    Baytların yanlış eşlenmesi tam burada yakalanır: game ve chat yer değiştirirse
    değerler ortada zıplar.
    """
    from sonar.engine.headset import decode_chatmix

    values = [decode_chatmix(report, 0x220E) for report in _captured_reports()]
    assert values == sorted(values)


def test_a_report_with_impossible_gains_is_rejected():
    """Aynı düğümden batarya/durum raporları da geliyor; onları ChatMix sanmayalım."""
    from sonar.engine.headset import CHATMIX_REPORT_ID, decode_chatmix

    assert decode_chatmix(bytes([CHATMIX_REPORT_ID, 0xFF, 0x64]), 0x220E) is None
    assert decode_chatmix(bytes([CHATMIX_REPORT_ID, 0x64]), 0x220E) is None  # çok kısa


def test_the_ends_are_the_two_extremes():
    from sonar.engine.headset import CHATMIX_REPORT_ID as ID
    from sonar.engine.headset import decode_chatmix

    assert decode_chatmix(bytes([ID, 100, 0]), 0x220E) == 0.0     # tamamen game
    assert decode_chatmix(bytes([ID, 100, 100]), 0x220E) == 50.0  # orta
    assert decode_chatmix(bytes([ID, 0, 100]), 0x220E) == 100.0   # tamamen chat


def test_all_hid_nodes_are_watched_not_just_the_first(tmp_path, monkeypatch):
    """Teker raporları kulaklığın **hangi** düğümünden gelecek belli değil.

    Arctis 7+ üç `hidraw` düğümü açıyor ve bu makinede teker yalnızca üçüncüsünden
    (`/dev/hidraw2`) rapor veriyor. Reader eskiden ilk okunabilir düğümü seçiyor ve
    oradan hiç rapor gelmediği için sonsuza kadar sessizce bekliyordu — udev kuralı
    doğru kurulmuşken bile teker çalışmıyordu.
    """
    import os

    from sonar.engine import headset as mod
    from sonar.engine.headset import ChatMixReader, HeadsetInfo

    devices = [
        HeadsetInfo(device=str(tmp_path / f"hidraw{i}"), vendor=0x1038, product=0x220E,
                    name="Arctis 7+", readable=True)
        for i in range(3)
    ]
    opened: list[str] = []
    real_open = os.open

    def fake_open(path, _flags):
        opened.append(path)
        return real_open(os.devnull, os.O_RDONLY)

    monkeypatch.setattr(mod.os, "open", fake_open)
    monkeypatch.setattr(mod.select, "select", lambda *_a: ([], [], []))

    reader = ChatMixReader(lambda _v: None, detect=lambda: devices)
    reader._stopping.set()          # tek tur dönsün, sonra çıksın
    reader._listen(devices)

    assert opened == [d.device for d in devices], "üç düğüm de açılmalı"
