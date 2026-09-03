"""`sonar-cli` — daemon'a D-Bus üzerinden bağlanan komut satırı istemcisi.

GUI olmadan tam kontrol sağlar; aynı zamanda API'nin ilk gerçek istemcisi olduğu için
Faz 7'deki arayüz yazılmadan önce API'yi denemenin yolu.

Tüm çağrılar `daemon.dbus_iface`'in JSON zarfını çözer; `{"ok": false}` gelirse mesaj
stderr'e yazılır ve çıkış kodu 1 olur — betiklerde `&&` ile zincirlenebilsin diye.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from PySide6.QtCore import QCoreApplication
from PySide6.QtDBus import QDBusConnection, QDBusInterface

from sonar.daemon.dbus_iface import BUS_NAME, INTERFACE, OBJECT_PATH

__all__ = ["main"]

_NOT_RUNNING = (
    "Sonar daemon'ına ulaşılamadı.\n"
    "Başlatmak için:  systemctl --user start sonar-daemon\n"
    "Durumu görmek için:  systemctl --user status sonar-daemon"
)


class Client:
    def __init__(self) -> None:
        self._app = QCoreApplication.instance() or QCoreApplication([])
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            raise SystemExit("Oturum D-Bus'ına bağlanılamadı.")
        self.iface = QDBusInterface(BUS_NAME, OBJECT_PATH, INTERFACE, bus)
        if not self.iface.isValid():
            raise SystemExit(_NOT_RUNNING)

    def call(self, method: str, *args: Any) -> Any:
        message = self.iface.call(method, *args)
        arguments = message.arguments()
        if not arguments:
            raise SystemExit(f"'{method}' çağrısı yanıtsız kaldı. {_NOT_RUNNING}")
        try:
            payload = json.loads(arguments[0])
        except (TypeError, json.JSONDecodeError) as exc:
            raise SystemExit(
                f"'{method}' beklenmeyen bir yanıt döndürdü: {arguments[0]!r}"
            ) from exc
        if not payload.get("ok"):
            code = payload.get("code", "hata")
            raise SystemExit(f"hata [{code}]: {payload.get('message', '')}")
        return payload.get("result")


# --------------------------------------------------------------------------- biçimlendirme


def _bar(value: float, width: int = 16) -> str:
    filled = round(min(max(value, 0.0), 1.0) * width)
    return "█" * filled + "·" * (width - filled)


def _pct(value: float) -> str:
    return f"{value * 100:5.1f}%"


def _send_of(channel: dict, bus_id: str) -> dict:
    """Kanalın bir bus'a gönderisi; yoksa nötr (yeni eklenen bus henüz diskte olmayabilir)."""
    send = (channel.get("sends") or {}).get(bus_id)
    return send if isinstance(send, dict) else {"volume": 1.0, "muted": False}


def _print_status(state: dict) -> None:
    config = state["config"]
    channels = sorted(config["channels"], key=lambda c: (c["order"], c["id"]))
    streams = state["streams"]

    buses = {b["id"]: b for b in config["buses"]}
    print(f"{'KANAL':<12} {'PROFİL':<14} {'ÇIKIŞ':<14} {'ÇIKIŞ SEVİYESİ':<26} {'YAYIN':<26}")
    print("─" * 96)
    for channel in channels:
        output_bus = channel.get("output_bus", "personal")
        rows = []
        for bus_id in (output_bus, "stream"):
            send = _send_of(channel, bus_id)
            mark = "M" if send["muted"] else " "
            rows.append(f"{mark} {_bar(send['volume'])} {_pct(send['volume'])}")
        output_name = buses.get(output_bus, {}).get("name", output_bus)
        print(
            f"{channel['name']:<12} {channel['active_profile']:<14} "
            f"{output_name:<14} {rows[0]:<26} {rows[1]:<26}"
        )

    print()
    for bus in config["buses"]:
        mark = "M" if bus["muted"] else " "
        if bus.get("kind") == "stream":
            where = "→ Sonar Stream Mix — Virtual Input (OBS)"
        else:
            where = f"→ {bus['device'] or '(sistem varsayılanı)'}"
        print(f"{bus['name']:<24} {mark} {_bar(bus['volume'])} {_pct(bus['volume'])}  {where}")
    for mic in config["mic_chains"]:
        mark = "M" if mic["muted"] else " "
        device = mic["source_device"] or "(sistem varsayılanı)"
        print(f"{mic['name']:<24} {mark} {_bar(mic['volume'])} {_pct(mic['volume'])}  ← {device}")

    chatmix = config["chatmix"]
    if chatmix["enabled"]:
        print(
            f"\nChatMix: {chatmix['value']:.0f}  "
            f"({chatmix['left_channel']} ←→ {chatmix['right_channel']})"
        )

    playback = [s for s in streams if not s["is_capture"]]
    capture = [s for s in streams if s["is_capture"]]
    print(f"\nÇALAN UYGULAMALAR ({len(playback)})")
    if not playback:
        print("  (yok)")
    for stream in playback:
        # `channel` daemon'ın yönlendirme kaydından geliyor; `target_node` yalnızca
        # uygulamanın kendi seçtiği hedefi gösterir ve genelde boştur.
        target = stream.get("channel") or stream["target_node"] or "(yönlendirilmedi)"
        label = stream["app_name"] or stream["app_binary"] or stream["media_name"]
        print(f"  #{stream['id']:<6} {label:<24} → {target}")
    if capture:
        print(f"\nMİKROFON KULLANANLAR ({len(capture)})")
        for stream in capture:
            label = stream["app_name"] or stream["app_binary"] or stream["media_name"]
            print(f"  #{stream['id']:<6} {label:<24} ← {stream['target_node'] or '?'}")

    if not state["graph_ready"]:
        print("\n⚠ Graf henüz hazır değil.")
    for conflict in state.get("conflicts", []):
        print(f"\n⚠ {conflict['message']}")


# --------------------------------------------------------------------------- komutlar


def _cmd_status(client: Client, args) -> int:
    state = client.call("GetState")
    if args.json:
        json.dump(state, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        _print_status(state)
    return 0


def _cmd_doctor(client: Client, args) -> int:
    """Ses gelmiyorsa ilk bakılacak yer."""
    report = client.call("Diagnose")
    if args.json:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    problems = 0
    print(f"Graf hazır         : {'evet' if report['graph_ready'] else 'HAYIR'}")
    problems += 0 if report["graph_ready"] else 1

    broken = report["broken_links"]
    print(f"Gönderi bağlantısı : {report['expected_links'] - len(broken)}/"
          f"{report['expected_links']}")
    for link in broken:
        print(f"  ✗ {link}")
    problems += len(broken)

    for node in report["missing_nodes"]:
        print(f"  ✗ node grafta yok: {node}")
    problems += len(report["missing_nodes"])

    for stream in report["unrouted_streams"]:
        print(f"  ⚠ yönlendirilmemiş akış: #{stream['id']} {stream['label']}")

    for conflict in report["conflicts"]:
        print(f"  ⚠ {conflict['message']}")

    print("\nSorun bulunamadı." if problems == 0 else f"\n{problems} sorun bulundu.")
    return 0 if problems == 0 else 1


def _cmd_volume(client: Client, args) -> int:
    client.call("SetChannelVolume", args.channel, args.bus, args.value / 100.0)
    return 0


def _cmd_mute(client: Client, args) -> int:
    if args.state == "toggle":
        state = client.call("GetState")
        channel = next((c for c in state["config"]["channels"] if c["id"] == args.channel), None)
        if channel is None:
            raise SystemExit(f"hata [unknown_channel]: böyle bir kanal yok: {args.channel}")
        bus_id = channel.get("output_bus", "personal") if args.bus == "output" else args.bus
        muted = not _send_of(channel, bus_id)["muted"]
    else:
        muted = args.state == "on"
    client.call("SetChannelMute", args.channel, args.bus, muted)
    print(f"{args.channel}/{args.bus}: {'susturuldu' if muted else 'açıldı'}")
    return 0


def _cmd_master(client: Client, args) -> int:
    client.call("SetMasterVolume", args.bus, args.value / 100.0)
    return 0


def _cmd_profile(client: Client, args) -> int:
    if args.name is None:
        names = client.call("ListProfiles", args.target)
        state = client.call("GetState")
        active = _active_profile(state, args.target)
        for name in names:
            print(f"{'*' if name == active else ' '} {name}")
        return 0
    client.call("LoadProfile", args.target, args.name)
    print(f"{args.target} → {args.name}")
    return 0


def _active_profile(state: dict, target: str) -> str:
    config = state["config"]
    for group in ("channels", "mic_chains", "buses"):
        for item in config[group]:
            if item["id"] == target:
                return item["active_profile"]
    return ""


def _cmd_save(client: Client, args) -> int:
    client.call("SaveProfile", args.target, args.name)
    print(f"kaydedildi: {args.target}/{args.name}")
    return 0


def _cmd_route(client: Client, args) -> int:
    client.call("SetRule", args.key, args.pattern, args.channel, args.regex)
    print(f"kural: {args.key}={args.pattern} → {args.channel}")
    return 0


def _cmd_rules(client: Client, args) -> int:
    if args.remove:
        key, _, pattern = args.remove.partition("=")
        if not pattern:
            raise SystemExit("kaldırmak için biçim: --remove <anahtar>=<desen>")
        client.call("RemoveRule", key, pattern)
        print(f"kaldırıldı: {key}={pattern}")
        return 0
    rules = client.call("ListRules")
    if args.json:
        json.dump(rules, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0
    if not rules:
        print("(kural yok)")
    for rule in rules:
        flags = " (regex)" if rule["is_regex"] else ""
        state = "" if rule["enabled"] else " [kapalı]"
        print(f"{rule['match_key']:<12} {rule['pattern']:<28} → {rule['channel_id']}{flags}{state}")
    return 0


def _cmd_move(client: Client, args) -> int:
    client.call("MoveStream", args.stream, args.channel, args.remember)
    suffix = " (kural olarak kaydedildi)" if args.remember else ""
    print(f"#{args.stream} → {args.channel}{suffix}")
    return 0


def _cmd_chatmix(client: Client, args) -> int:
    client.call("SetChatMix", float(args.value))
    print(f"ChatMix: {args.value}")
    return 0


def _cmd_devices(client: Client, args) -> int:
    devices = client.call("GetDevices")
    if args.json:
        json.dump(devices, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0
    for device in devices:
        kind = "giriş " if device["is_source"] else "çıkış "
        print(f"{kind} {device['description'] or device['name']}\n        {device['name']}")
    return 0


def _cmd_device(client: Client, args) -> int:
    if args.mic:
        client.call("SetMicDevice", args.target, args.device)
    else:
        client.call("SetBusDevice", args.target, args.device)
    print(f"{args.target} → {args.device}")
    return 0


def _cmd_new(client: Client, args) -> int:
    client.call("NewProfile", args.target, args.name)
    print(f"{args.target}: yeni düz profil '{args.name}' oluşturuldu ve etkin")
    return 0


def _cmd_favorite(client: Client, args) -> int:
    if args.action == "list":
        for name in client.call("ListFavorites", args.target) or []:
            print(name)
        return 0
    adding = args.action == "add"
    client.call("SetProfileFavorite", args.target, args.name, adding)
    what = "favorilere eklendi" if adding else "favorilerden çıkarıldı"
    print(f"{args.target}: '{args.name}' {what}")
    return 0


def _cmd_channel(client: Client, args) -> int:
    if args.action == "add":
        new_id = client.call("AddChannel", args.name, args.direction, args.color)
        kind = "giriş" if args.direction == "input" else "çıkış"
        print(f"{kind} kanalı eklendi: {new_id}  (graf yeniden kuruluyor)")
    else:
        client.call("RemoveChannel", args.name)
        print(f"kanal silindi: {args.name}  (graf yeniden kuruluyor)")
    return 0


def _cmd_output(client: Client, args) -> int:
    """Çıkış bus'ları: her biri bir fiziksel cihaz + kendi master'ı."""
    if args.action == "list":
        state = client.call("GetState")
        for bus in state["config"]["buses"]:
            if bus.get("kind") == "stream":
                continue
            users = [
                c["name"]
                for c in state["config"]["channels"]
                if c.get("output_bus", "personal") == bus["id"]
            ]
            device = bus["device"] or "(sistem varsayılanı)"
            print(f"{bus['id']:<14} {bus['name']:<18} → {device}")
            print(f"{'':<14} kanallar: {', '.join(users) or '(yok)'}")
        return 0
    if args.action == "add":
        new_id = client.call("AddOutputBus", args.name, args.device or "")
        print(f"çıkış eklendi: {new_id}  (graf yeniden kuruluyor)")
        return 0
    client.call("RemoveOutputBus", args.name)
    print(f"çıkış silindi: {args.name}  (graf yeniden kuruluyor)")
    return 0


def _cmd_route_output(client: Client, args) -> int:
    client.call("SetChannelOutput", args.channel, args.bus)
    print(f"{args.channel} → {args.bus}")
    return 0


def _cmd_obs(client: Client, args) -> int:
    """Kanalın OBS için ayrı bir sanal giriş cihazı yayınlaması."""
    enabled = args.state == "on"
    client.call("SetChannelStreamSource", args.channel, enabled)
    state = "açık" if enabled else "kapalı"
    print(f"{args.channel} OBS kaynağı: {state}  (graf yeniden kuruluyor)")
    return 0


def _cmd_presets(client: Client, args) -> int:
    builtin = set(client.call("ListBuiltinProfiles", args.target) or [])
    for name in client.call("ListProfiles", args.target) or []:
        print(f"{'🔒' if name in builtin else '  '} {name}")
    return 0


def _cmd_import(client: Client, args) -> int:
    from pathlib import Path

    text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    result = client.call("ImportProfile", args.target, text, args.name or "")
    print(f"içe aktarıldı: {result['name']}  (biçim: {result['source']}, {result['bands']} band)")
    for warning in result.get("warnings", []):
        print(f"  ⚠ {warning}")
    return 0


def _cmd_export(client: Client, args) -> int:
    from pathlib import Path

    text = client.call("ExportProfile", args.target, args.name or "", args.autoeq)
    if args.file:
        Path(args.file).write_text(text, encoding="utf-8")
        print(f"yazıldı: {args.file}")
    else:
        print(text, end="")
    return 0


def _cmd_reset(client: Client, args) -> int:
    client.call("ResetProfile", args.target)
    print(f"{args.target}: profil sıfırlandı")
    return 0


def _cmd_meters(client: Client, args) -> int:
    """Seviye metrelerini terminalde göster. Abonelik açılır, çıkışta kapatılır."""
    import time

    client.call("SubscribeMeters", True)
    try:
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            levels = client.call("GetLevels")
            if args.json:
                json.dump(levels, sys.stdout, ensure_ascii=False)
                print()
            else:
                print("\033[2J\033[H", end="")  # ekranı temizle
                for node, level in sorted(levels.items()):
                    clip = " CLIP" if level["clipped"] else ""
                    print(
                        f"{node:<20} {_meter_bar(level['peak_db'])} "
                        f"{level['peak_db']:6.1f} dB{clip}"
                    )
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        client.call("SubscribeMeters", False)
    return 0


def _meter_bar(db: float, width: int = 30) -> str:
    """-60 dB … 0 dB aralığını çubuğa döker."""
    filled = round(max(0.0, min(1.0, (db + 60.0) / 60.0)) * width)
    return "█" * filled + "·" * (width - filled)


def _cmd_reload(client: Client, _args) -> int:
    client.call("Reload")
    print("yapılandırma yeniden okundu")
    return 0


# --------------------------------------------------------------------------- ayrıştırıcı


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sonar-cli", description="Sonar komut satırı istemcisi")
    parser.add_argument("--json", action="store_true", help="çıktıyı JSON olarak ver")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="kanallar, fader'lar, profiller, çalan uygulamalar")
    doctor = sub.add_parser("doctor", help="ses yolu teşhisi — ses gelmiyorsa buraya bakın")
    doctor.add_argument("--json", action="store_true", help="ham çıktı")

    p = sub.add_parser("volume", help="kanal ses seviyesi (0-100)")
    p.add_argument("channel")
    p.add_argument("bus", help="çıkış bus'ının kimliği, 'output' (kanalın seçili çıkışı) "
                                "veya 'stream'")
    p.add_argument("value", type=float)

    p = sub.add_parser("mute", help="kanalı sustur/aç")
    p.add_argument("channel")
    p.add_argument("bus", help="çıkış bus'ının kimliği, 'output' (kanalın seçili çıkışı) "
                                "veya 'stream'")
    p.add_argument("state", nargs="?", default="toggle", choices=["on", "off", "toggle"])

    p = sub.add_parser("master", help="Personal/Stream master seviyesi (0-100)")
    p.add_argument("bus", help="çıkış bus'ının kimliği, 'output' (kanalın seçili çıkışı) "
                                "veya 'stream'")
    p.add_argument("value", type=float)

    p = sub.add_parser("profile", help="profil listele veya yükle")
    p.add_argument("target")
    p.add_argument("name", nargs="?")

    p = sub.add_parser("save", help="çalışılan profili yeni adla kaydet")
    p.add_argument("target")
    p.add_argument("name")

    p = sub.add_parser("route", help="uygulama → kanal kuralı ekle")
    p.add_argument("pattern")
    p.add_argument("channel")
    p.add_argument("--key", default="binary", choices=["binary", "app_name", "media_name"])
    p.add_argument("--regex", action="store_true")

    p = sub.add_parser("rules", help="kuralları listele veya kaldır")
    p.add_argument("--remove", metavar="ANAHTAR=DESEN")

    p = sub.add_parser("move", help="çalan bir akışı başka kanala taşı")
    p.add_argument("stream", type=int)
    p.add_argument("channel")
    p.add_argument(
        "--remember", action="store_true", help="bu uygulamayı bundan sonra hep bu kanala gönder"
    )

    p = sub.add_parser("chatmix", help="ChatMix konumu (0-100)")
    p.add_argument("value", type=float)

    sub.add_parser("devices", help="fiziksel ses cihazlarını listele")

    p = sub.add_parser("device", help="bir bus veya mikrofon zincirinin cihazını ayarla")
    p.add_argument("target")
    p.add_argument("device")
    p.add_argument("--mic", action="store_true", help="hedef bir mikrofon zinciri")

    p = sub.add_parser("new", help="sıfırdan düz bir profil oluştur")
    p.add_argument("target")
    p.add_argument("name")

    p = sub.add_parser("favorite", help="profilleri favorilere ekle/çıkar veya listele")
    p.add_argument("action", choices=("add", "remove", "list"))
    p.add_argument("target")
    p.add_argument("name", nargs="?", default="")

    p = sub.add_parser("channel", help="kanal ekle veya sil")
    p.add_argument("action", choices=("add", "remove"))
    p.add_argument("name", help="ekleme: görünen ad · silme: kanal id'si")
    p.add_argument(
        "--direction", choices=("output", "input"), default="output", help="yalnızca ekleme"
    )
    p.add_argument("--color", default="#8B95A5")

    p = sub.add_parser("output", help="çıkış bus'ları (fiziksel cihaz başına bir master)")
    p.add_argument("action", choices=("list", "add", "remove"))
    p.add_argument("name", nargs="?", default="", help="ekleme: görünen ad · silme: bus id'si")
    p.add_argument("--device", default="", help="yalnızca ekleme: fiziksel cihaz node adı")

    p = sub.add_parser("send", help="bir kanalı başka bir çıkışa taşı (canlı)")
    p.add_argument("channel")
    p.add_argument("bus", help="çıkış bus'ının kimliği")

    p = sub.add_parser("obs", help="kanal için OBS'e ayrı sanal giriş cihazı ver")
    p.add_argument("channel")
    p.add_argument("state", choices=("on", "off"))

    p = sub.add_parser("presets", help="gömülü presetleri ve profilleri listele")
    p.add_argument("target")

    p = sub.add_parser("import", help="AutoEQ / EasyEffects / .sonarprofile içe aktar")
    p.add_argument("target")
    p.add_argument("file")
    p.add_argument("--name", help="profil adı (varsayılan: dosyadan)")

    p = sub.add_parser("export", help="profili dışa aktar")
    p.add_argument("target")
    p.add_argument("name", nargs="?")
    p.add_argument("--file", help="dosyaya yaz (varsayılan: stdout)")
    p.add_argument("--autoeq", action="store_true", help="AutoEQ/APO metin biçimi")

    p = sub.add_parser("reset", help="aktif profili düz hâle döndür")
    p.add_argument("target")

    p = sub.add_parser("meters", help="seviye metrelerini canlı göster")
    p.add_argument("--seconds", type=float, default=10.0, help="kaç saniye izlensin")

    sub.add_parser("reload", help="config.toml'u diskten yeniden oku")
    return parser


_COMMANDS = {
    "status": _cmd_status,
    "doctor": _cmd_doctor,
    "volume": _cmd_volume,
    "mute": _cmd_mute,
    "master": _cmd_master,
    "profile": _cmd_profile,
    "save": _cmd_save,
    "route": _cmd_route,
    "rules": _cmd_rules,
    "move": _cmd_move,
    "chatmix": _cmd_chatmix,
    "devices": _cmd_devices,
    "device": _cmd_device,
    "obs": _cmd_obs,
    "channel": _cmd_channel,
    "output": _cmd_output,
    "send": _cmd_route_output,
    "new": _cmd_new,
    "favorite": _cmd_favorite,
    "presets": _cmd_presets,
    "import": _cmd_import,
    "export": _cmd_export,
    "reset": _cmd_reset,
    "meters": _cmd_meters,
    "reload": _cmd_reload,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return _COMMANDS[args.command](Client(), args)


if __name__ == "__main__":
    raise SystemExit(main())
