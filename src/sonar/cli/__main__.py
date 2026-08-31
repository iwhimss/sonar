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


def _print_status(state: dict) -> None:
    config = state["config"]
    channels = sorted(config["channels"], key=lambda c: (c["order"], c["id"]))
    streams = state["streams"]

    print(f"{'KANAL':<12} {'PROFİL':<16} {'KULAKLIK':<26} {'YAYIN':<26}")
    print("─" * 82)
    for channel in channels:
        rows = []
        for bus in ("personal", "stream"):
            send = channel[bus]
            mark = "M" if send["muted"] else " "
            rows.append(f"{mark} {_bar(send['volume'])} {_pct(send['volume'])}")
        print(f"{channel['name']:<12} {channel['active_profile']:<16} {rows[0]:<26} {rows[1]:<26}")

    print()
    for bus in config["buses"]:
        mark = "M" if bus["muted"] else " "
        device = bus["device"] or "(sistem varsayılanı)"
        print(f"{bus['name']:<24} {mark} {_bar(bus['volume'])} {_pct(bus['volume'])}  → {device}")
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
        target = stream["target_node"] or "?"
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


def _cmd_volume(client: Client, args) -> int:
    client.call("SetChannelVolume", args.channel, args.bus, args.value / 100.0)
    return 0


def _cmd_mute(client: Client, args) -> int:
    if args.state == "toggle":
        state = client.call("GetState")
        channel = next((c for c in state["config"]["channels"] if c["id"] == args.channel), None)
        if channel is None:
            raise SystemExit(f"hata [unknown_channel]: böyle bir kanal yok: {args.channel}")
        muted = not channel[args.bus]["muted"]
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
    client.call("MoveStream", args.stream, args.channel)
    print(f"#{args.stream} → {args.channel}")
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
    print(f"{args.target} → {args.device}  (graf yeniden kuruluyor)")
    return 0


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

    p = sub.add_parser("volume", help="kanal ses seviyesi (0-100)")
    p.add_argument("channel")
    p.add_argument("bus", choices=["personal", "stream"])
    p.add_argument("value", type=float)

    p = sub.add_parser("mute", help="kanalı sustur/aç")
    p.add_argument("channel")
    p.add_argument("bus", choices=["personal", "stream"])
    p.add_argument("state", nargs="?", default="toggle", choices=["on", "off", "toggle"])

    p = sub.add_parser("master", help="Personal/Stream master seviyesi (0-100)")
    p.add_argument("bus", choices=["personal", "stream"])
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

    p = sub.add_parser("chatmix", help="ChatMix konumu (0-100)")
    p.add_argument("value", type=float)

    sub.add_parser("devices", help="fiziksel ses cihazlarını listele")

    p = sub.add_parser("device", help="bir bus veya mikrofon zincirinin cihazını ayarla")
    p.add_argument("target")
    p.add_argument("device")
    p.add_argument("--mic", action="store_true", help="hedef bir mikrofon zinciri")

    sub.add_parser("reload", help="config.toml'u diskten yeniden oku")
    return parser


_COMMANDS = {
    "status": _cmd_status,
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
    "reload": _cmd_reload,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return _COMMANDS[args.command](Client(), args)


if __name__ == "__main__":
    raise SystemExit(main())
