from __future__ import annotations

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
