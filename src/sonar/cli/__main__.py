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
from PySide6.QtDBus import QDBus, QDBusConnection, QDBusInterface

from sonar.core import config as config_mod
from sonar.core import i18n
from sonar.core.names import display_name, preset_label
from sonar.daemon.dbus_iface import BUS_NAME, INTERFACE, OBJECT_PATH

__all__ = ["main"]

def _not_running() -> str:
    """Dil, `main()` içinde daemon'a bağlanmadan önce kuruluyor; bu metin de çevrili."""
    return i18n.t("cli.not_running")


class Client:
    def __init__(self) -> None:
        self._app = QCoreApplication.instance() or QCoreApplication([])
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            raise SystemExit(i18n.t("cli.no_session_bus"))
        self.iface = QDBusInterface(BUS_NAME, OBJECT_PATH, INTERFACE, bus)
        if not self.iface.isValid():
            raise SystemExit(_not_running())

    def call(self, method: str, *args: Any) -> Any:
        # `iface.call(method, *args)` PySide6'da en fazla 4 argüman alıyor; beşincisinde
        # `TypeError` veriyor (ölçüldü: 5 argümanlı `SetRule`). `callWithArgumentList`
        # sınırsız ve aynı işi yapıyor.
        message = self.iface.callWithArgumentList(QDBus.CallMode.Block, method, list(args))
        arguments = message.arguments()
        if not arguments:
            raise SystemExit(i18n.t("cli.no_reply", method=method) + " " + _not_running())
        try:
            payload = json.loads(arguments[0])
        except (TypeError, json.JSONDecodeError) as exc:
            raise SystemExit(
                i18n.t("cli.bad_reply", method=method, payload=repr(arguments[0]))
            ) from exc
        if not payload.get("ok"):
            code = payload.get("code", "error")
            raise SystemExit(
                i18n.t("cli.error", code=code, message=payload.get("message", ""))
            )
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
    if not state.get("provisioned", True):
        # Kurulmamış bir sistemde tabloyu basmak yanıltıcı olurdu: yapılandırma var ama
        # PipeWire'da hiçbir node yok.
        print(i18n.t("cli.not_provisioned"))
        print()
    channels = sorted(config["channels"], key=lambda c: (c["order"], c["id"]))
    streams = state["streams"]

    output_bus = next(
        (b["id"] for b in config["buses"] if b.get("kind") != "stream"), "personal"
    )
    print(
        f"{i18n.t('cli.col.channel'):<12} {i18n.t('cli.col.profile'):<16} "
        f"{i18n.t('cli.col.headphones'):<26} {i18n.t('cli.col.stream'):<26}"
    )
    print("─" * 82)
    for channel in channels:
        rows = []
        for bus_id in (output_bus, "stream"):
            send = _send_of(channel, bus_id)
            mark = "M" if send["muted"] else " "
            rows.append(f"{mark} {_bar(send['volume'])} {_pct(send['volume'])}")
        name = display_name("channel", channel["id"], channel["name"])
        profile = preset_label(channel["active_profile"])
        print(f"{name:<12} {profile:<16} {rows[0]:<26} {rows[1]:<26}")

    print()
    for bus in config["buses"]:
        mark = "M" if bus["muted"] else " "
        if bus.get("kind") == "stream":
            # Sabit metin değil: OBS'te seçilecek ad bus'ın adından üretiliyor ve
            # doküman ile birebir aynı olmalı.
            where = "→ " + i18n.t("cli.obs_desktop_audio", device=f"Sonar {bus['name']}")
        else:
            where = f"→ {bus['device'] or i18n.t('cli.system_default')}"
        name = display_name("bus", bus["id"], bus["name"])
        print(f"{name:<24} {mark} {_bar(bus['volume'])} {_pct(bus['volume'])}  {where}")
    for mic in config["mic_chains"]:
        mark = "M" if mic["muted"] else " "
        device = mic["source_device"] or i18n.t("cli.system_default")
        in_stream = mic.get("send_to_stream_bus", True)
        stream = "" if in_stream else "  [" + i18n.t("cli.not_in_stream") + "]"
        name = display_name("mic", mic["id"], mic["name"])
        print(
            f"{name:<24} {mark} {_bar(mic['volume'])} {_pct(mic['volume'])}  "
            f"← {device}{stream}"
        )

    chatmix = config["chatmix"]
    if chatmix["enabled"]:
        print(
            f"\nChatMix: {chatmix['value']:.0f}  "
            f"({chatmix['left_channel']} ←→ {chatmix['right_channel']})"
        )

    playback = [s for s in streams if not s["is_capture"]]
    capture = [s for s in streams if s["is_capture"]]
    print(f"\n{i18n.t('cli.playing_apps')} ({len(playback)})")
    if not playback:
        print("  " + i18n.t("cli.none"))
    for stream in playback:
        # `channel` daemon'ın yönlendirme kaydından geliyor; `target_node` yalnızca
        # uygulamanın kendi seçtiği hedefi gösterir ve genelde boştur.
        target = stream.get("channel") or stream["target_node"] or i18n.t("cli.unrouted")
        label = stream["app_name"] or stream["app_binary"] or stream["media_name"]
        print(f"  #{stream['id']:<6} {label:<24} → {target}")
    if capture:
        print(f"\n{i18n.t('cli.mic_apps')} ({len(capture)})")
        for stream in capture:
            label = stream["app_name"] or stream["app_binary"] or stream["media_name"]
            target = stream.get("channel") or stream["target_node"] or i18n.t("cli.unrouted")
            print(f"  #{stream['id']:<6} {label:<24} ← {target}")

    if state.get("provisioned", True) and not state["graph_ready"]:
        print("\n⚠ " + i18n.t("cli.graph_not_ready"))
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
    yes, no = i18n.t("cli.yes"), i18n.t("cli.no")
    print(f"{i18n.t('cli.doctor.graph_ready'):<19}: {yes if report['graph_ready'] else no}")
    problems += 0 if report["graph_ready"] else 1

    broken = report["broken_links"]
    print(f"{i18n.t('cli.doctor.send_links'):<19}: "
          f"{report['expected_links'] - len(broken)}/{report['expected_links']}")
    for link in broken:
        print(f"  ✗ {link}")
    problems += len(broken)

    for node in report["missing_nodes"]:
        print("  ✗ " + i18n.t("cli.doctor.missing_node", node=node))
    problems += len(report["missing_nodes"])

    # Uyarılar sorun sayısına girmiyor: OBS kapalıyken "dinleyen yok" normal ve
    # `doctor`ın çıkış kodunu 1 yapmamalı. Ama sayılmadıkları için ekranda ⚠ dururken
    # "Sorun bulunamadı." yazıyordu — kendi kendini yalanlayan bir çıktı. Artık ayrıca
    # sayılıyor ve son satır ikisini birden söylüyor.
    warnings = 0
    for stream in report["unrouted_streams"]:
        print("  ⚠ " + i18n.t("cli.doctor.unrouted", id=stream["id"], label=stream["label"]))
        warnings += 1

    for conflict in report["conflicts"]:
        print(f"  ⚠ {conflict['message']}")
        warnings += 1

    # Yayın kurulumu: kullanıcının en çok takıldığı yer, o yüzden doctor'da da duruyor.
    setup = client.call("StreamSetup")
    listeners = setup["listeners"]
    print(f"\n{i18n.t('cli.doctor.stream_mix'):<19}: {setup['device']}")
    if listeners:
        for row in listeners:
            way = i18n.t("cli.via.monitor" if row["via"] == "monitor" else "cli.via.source")
            print(f"  · #{row['id']} {row['label']} — {way}")
    else:
        print("  · " + i18n.t("cli.doctor.no_listener"))
    for mic in setup["mics"]:
        where = i18n.t("cli.doctor.mic_on" if mic["in_stream"] else "cli.doctor.mic_off")
        name = display_name("mic", mic["id"], mic["name"])
        print(f"  · {i18n.t('cli.microphone')} {name}: {where}")
    for problem in setup["problems"]:
        print(f"  ⚠ {problem['message']}")
        warnings += 1

    if problems:
        summary = i18n.t("cli.doctor.problems", count=problems)
    elif warnings:
        summary = i18n.t("cli.doctor.warnings", count=warnings)
    else:
        summary = i18n.t("cli.doctor.clean")
    print("\n" + summary)
    return 0 if problems == 0 else 1


def _cmd_volume(client: Client, args) -> int:
    client.call("SetChannelVolume", args.channel, args.bus, args.value / 100.0)
    return 0


def _cmd_mute(client: Client, args) -> int:
    if args.state == "toggle":
        state = client.call("GetState")
        channel = next((c for c in state["config"]["channels"] if c["id"] == args.channel), None)
        if channel is None:
            raise SystemExit(
                i18n.t("cli.error", code="unknown_channel",
                       message=i18n.t("error.no_such_channel", name=args.channel))
            )
        bus_id = channel.get("output_bus", "personal") if args.bus == "output" else args.bus
        muted = not _send_of(channel, bus_id)["muted"]
    else:
        muted = args.state == "on"
    client.call("SetChannelMute", args.channel, args.bus, muted)
    print(f"{args.channel}/{args.bus}: "
          + i18n.t("cli.muted" if muted else "cli.unmuted"))
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
            print(f"{'*' if name == active else ' '} {preset_label(name)}")
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
    print(i18n.t("cli.saved", name=f"{args.target}/{args.name}"))
    return 0


def _cmd_route(client: Client, args) -> int:
    client.call("SetRule", args.key, args.pattern, args.channel, args.regex, args.direction)
    arrow = "←" if args.direction == "in" else "→"
    print(i18n.t("cli.rule_set", key=args.key, pattern=args.pattern,
                 arrow=arrow, channel=args.channel))
    return 0


def _cmd_rules(client: Client, args) -> int:
    if args.remove:
        key, _, pattern = args.remove.partition("=")
        if not pattern:
            raise SystemExit(i18n.t("cli.remove_format"))
        client.call("RemoveRule", key, pattern, args.direction)
        print(i18n.t("cli.removed", name=f"{key}={pattern}"))
        return 0
    rules = client.call("ListRules")
    if args.json:
        json.dump(rules, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0
    if not rules:
        print(i18n.t("cli.no_rules"))
    for rule in rules:
        flags = " (regex)" if rule["is_regex"] else ""
        state = "" if rule["enabled"] else " [" + i18n.t("cli.off") + "]"
        way = rule.get("direction", "out")
        arrow = "← " + i18n.t("cli.mic_short") if way == "in" \
            else "→ " + i18n.t("cli.audio_short")
        print(
            f"{rule['match_key']:<12} {rule['pattern']:<28} "
            f"{arrow} {rule['channel_id']}{flags}{state}"
        )
    return 0


def _cmd_move(client: Client, args) -> int:
    client.call("MoveStream", args.stream, args.channel, args.remember)
    suffix = " (kural olarak kaydedildi)" if args.remember else ""
    print(f"#{args.stream} → {args.channel}{suffix}")
    return 0


def _cmd_chatmix(client: Client, args) -> int:
    if args.invert is not None:
        client.call("SetChatMixInvert", args.invert == "on")
        print(i18n.t("cli.wheel_direction",
                     value=i18n.t("cli.inverted" if args.invert == "on" else "cli.normal")))
        return 0
    if args.value is None:
        raise SystemExit(i18n.t("cli.chatmix_usage"))
    client.call("SetChatMix", float(args.value))
    print(f"ChatMix: {args.value}")
    return 0


def _cmd_install(client: Client, args) -> int:
    """Sanal kanalları kurar — karşılama ekranındaki düğmenin terminal karşılığı."""
    summary = client.call("Provision")
    print(i18n.t("cli.installed"))
    for bus in summary["buses"]:
        print(f"  · {bus['device']}")
    for channel in summary["channels"]:
        print(f"  · {channel['device']}")
    for mic in summary["mics"]:
        print(f"  · {mic['device']}")
    return 0


def _cmd_uninstall(client: Client, args) -> int:
    result = client.call("Deprovision", bool(args.purge))
    print(i18n.t("cli.uninstalled"))
    if args.purge:
        print(i18n.t("cli.purged" if result["purged"] else "cli.purge_failed"))
    print("\n" + i18n.t("cli.manual_steps"))
    for step in result["manual_steps"]:
        print(f"  {step['note']}:\n    {step['command']}")
    return 0


def _cmd_effect(client: Client, args) -> int:
    """Efekt zinciri: listele, ekle, sil, taşı.

    Ekleme/silme/taşıma **yapısal**: graf yeniden kurulur (~200 ms sessizlik).
    """
    if args.action == "list":
        chain = client.call("ListEffects", args.target) or []
        for index, effect in enumerate(chain):
            mark = " " if effect["enabled"] else "M"
            print(f"{index:>2} {mark} {effect['slot']:<12} {effect['kind']}")
        print()
        kinds = [e["kind"] for e in client.call("ListEffectKinds", args.target) or []]
        print(i18n.t("cli.effect.available", kinds=", ".join(kinds)))
        return 0
    if args.action == "add":
        slot = client.call("AddEffect", args.target, args.value, -1)
        print(i18n.t("cli.effect.added", slot=slot))
        return 0
    if args.action == "remove":
        client.call("RemoveEffect", args.target, args.value)
        print(i18n.t("cli.effect.removed", slot=args.value))
        return 0
    if args.index is None:
        raise SystemExit(i18n.t("cli.effect.move_usage"))
    client.call("MoveEffect", args.target, args.value, args.index)
    print(i18n.t("cli.effect.moved", slot=args.value, index=args.index))
    return 0


def _cmd_lang(client: Client, args) -> int:
    if not args.code:
        current = i18n.language()
        for entry in i18n.available():
            mark = "→" if entry["code"] == current else " "
            print(f"{mark} {entry['code']}  {entry['label']}")
        return 0
    code = client.call("SetLanguage", args.code)
    i18n.set_language(code or args.code)
    print(i18n.t("cli.lang.set", label=i18n.LANGUAGES.get(i18n.language(), "?")))
    return 0


def _cmd_devices(client: Client, args) -> int:
    devices = client.call("GetDevices")
    if args.json:
        json.dump(devices, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0
    for device in devices:
        kind = i18n.t("cli.input" if device["is_source"] else "cli.output")
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
    print(i18n.t("cli.profile_created", target=args.target, name=args.name))
    return 0


def _cmd_favorite(client: Client, args) -> int:
    if args.action == "list":
        for name in client.call("ListFavorites", args.target) or []:
            print(name)
        return 0
    adding = args.action == "add"
    client.call("SetProfileFavorite", args.target, args.name, adding)
    print(i18n.t("cli.favorite_added" if adding else "cli.favorite_removed",
                 target=args.target, name=args.name))
    return 0


def _cmd_channel(client: Client, args) -> int:
    if args.action == "add":
        new_id = client.call("AddChannel", args.name, args.direction, args.color)
        kind = i18n.t("cli.input" if args.direction == "input" else "cli.output")
        print(i18n.t("cli.channel_added", kind=kind, id=new_id))
    else:
        client.call("RemoveChannel", args.name)
        print(i18n.t("cli.channel_removed", name=args.name))
    return 0


def _cmd_smart(client: Client, args) -> int:
    """Smart Volume: bu kanal konuşurken diğerlerini kıs.

    Ayar kanalın **aktif profilinde** duruyor (şema 4), yani profil başına farklı
    olabiliyor.
    """
    fields: dict = {}
    if args.state:
        fields["enabled"] = args.state == "on"
    if args.targets is not None:
        fields["target_channels"] = args.targets
    for name in ("reduction_db", "threshold_db", "attack_ms", "hold_ms", "release_ms"):
        value = getattr(args, name)
        if value is not None:
            fields[name] = value

    if fields:
        duck = client.call("SetDucking", args.channel, json.dumps(fields))
    else:
        state = client.call("GetState")
        duck = ((state["profiles"] or {}).get(args.channel) or {}).get("ducking") or {}

    profile = _active_profile(client.call("GetState"), args.channel)
    targets = duck.get("target_channels") or [i18n.t("cli.smart.all_others")]
    on = i18n.t("cli.on" if duck.get("enabled") else "cli.off")
    print(f"{args.channel} / {profile}")
    print(f"{i18n.t('cli.smart.state'):<13}: {on}")
    print(f"{i18n.t('cli.smart.targets'):<13}: {', '.join(targets)}")
    print(f"{i18n.t('cli.smart.reduction'):<13}: {duck.get('reduction_db', 0):.1f} dB  "
          f"({i18n.t('param.threshold').lower()} {duck.get('threshold_db', 0):.1f} dB)")
    print(f"{i18n.t('cli.smart.envelope'):<13}: {i18n.t('param.attack').lower()} "
          f"{duck.get('attack_ms', 0):.0f} ms · {i18n.t('param.hold').lower()} "
          f"{duck.get('hold_ms', 0):.0f} ms · {i18n.t('param.release').lower()} "
          f"{duck.get('release_ms', 0):.0f} ms")
    return 0


def _cmd_obs(client: Client, args) -> int:
    """Kanalın OBS için ayrı bir sanal giriş cihazı yayınlaması."""
    enabled = args.state == "on"
    client.call("SetChannelStreamSource", args.channel, enabled)
    print(i18n.t("cli.obs_source", channel=args.channel,
                 state=i18n.t("cli.on" if enabled else "cli.off")))
    return 0


def _cmd_presets(client: Client, args) -> int:
    builtin = set(client.call("ListBuiltinProfiles", args.target) or [])
    for name in client.call("ListProfiles", args.target) or []:
        print(f"{'🔒' if name in builtin else '  '} {preset_label(name)}")
    return 0


def _cmd_import(client: Client, args) -> int:
    from pathlib import Path

    text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    result = client.call("ImportProfile", args.target, text, args.name or "")
    print(i18n.t("cli.imported", name=result["name"],
                 source=result["source"], bands=result["bands"]))
    for warning in result.get("warnings", []):
        print(f"  ⚠ {warning}")
    return 0


def _cmd_export(client: Client, args) -> int:
    from pathlib import Path

    text = client.call("ExportProfile", args.target, args.name or "", args.autoeq)
    if args.file:
        Path(args.file).write_text(text, encoding="utf-8")
        print(i18n.t("cli.written", file=args.file))
    else:
        print(text, end="")
    return 0


def _cmd_reset(client: Client, args) -> int:
    client.call("ResetProfile", args.target)
    print(i18n.t("cli.profile_reset", target=args.target))
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


def _cmd_mic(client: Client, args) -> int:
    """Mikrofon zincirinin yayın ve sidetone anahtarları."""
    if args.what == "stream":
        client.call("SetMicStreamSend", args.chain, args.state == "on")
        print(i18n.t("cli.mic_stream", chain=args.chain,
                     state=i18n.t("cli.on" if args.state == "on" else "cli.off")))
    else:
        client.call("SetMicMonitor", args.chain, args.state == "on")
        print(i18n.t("cli.mic_sidetone", chain=args.chain,
                     state=i18n.t("cli.on" if args.state == "on" else "cli.off")))
    return 0


def _cmd_reload(client: Client, _args) -> int:
    client.call("Reload")
    print(i18n.t("cli.reloaded"))
    return 0


# --------------------------------------------------------------------------- ayrıştırıcı


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sonar-cli", description=i18n.t("cli.help.prog"))
    parser.add_argument("--json", action="store_true", help=i18n.t("cli.help.json"))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help=i18n.t("cli.help.status"))
    doctor = sub.add_parser("doctor", help=i18n.t("cli.help.doctor"))
    doctor.add_argument("--json", action="store_true", help=i18n.t("cli.help.raw"))

    p = sub.add_parser("volume", help=i18n.t("cli.help.volume"))
    p.add_argument("channel")
    p.add_argument("bus", help=i18n.t("cli.help.bus_arg"))
    p.add_argument("value", type=float)

    p = sub.add_parser("mute", help=i18n.t("cli.help.mute"))
    p.add_argument("channel")
    p.add_argument("bus", help=i18n.t("cli.help.bus_arg"))
    p.add_argument("state", nargs="?", default="toggle", choices=["on", "off", "toggle"])

    p = sub.add_parser("master", help=i18n.t("cli.help.master"))
    p.add_argument("bus", help=i18n.t("cli.help.bus_arg"))
    p.add_argument("value", type=float)

    p = sub.add_parser("profile", help=i18n.t("cli.help.profile"))
    p.add_argument("target")
    p.add_argument("name", nargs="?")

    p = sub.add_parser("save", help=i18n.t("cli.help.save"))
    p.add_argument("target")
    p.add_argument("name")

    p = sub.add_parser("route", help=i18n.t("cli.help.route"))
    p.add_argument("pattern")
    p.add_argument("channel")
    p.add_argument("--key", default="binary", choices=["binary", "app_name", "media_name"])
    p.add_argument("--regex", action="store_true")
    p.add_argument(
        "--direction",
        default="out",
        choices=["out", "in"],
        help=i18n.t("cli.help.direction"),
    )

    p = sub.add_parser("rules", help=i18n.t("cli.help.rules"))
    p.add_argument("--remove", metavar=i18n.t("cli.meta.key_pattern"))
    p.add_argument("--direction", default="", choices=["", "out", "in"],
                   help=i18n.t("cli.help.rules_direction"))

    p = sub.add_parser("move", help=i18n.t("cli.help.move"))
    p.add_argument("stream", type=int)
    p.add_argument("channel")
    p.add_argument(
        "--remember", action="store_true", help=i18n.t("cli.help.remember")
    )

    p = sub.add_parser("chatmix", help=i18n.t("cli.help.chatmix"))
    p.add_argument("value", type=float, nargs="?")
    # Kulaklık tekerinin hangi ucunun Game olduğu HID raporundan çıkmıyor; ters
    # geliyorsa kullanıcı bir kez söylüyor.
    p.add_argument("--invert", choices=["on", "off"], help=i18n.t("cli.help.invert"))

    sub.add_parser("devices", help=i18n.t("cli.help.devices"))

    p = sub.add_parser("device", help=i18n.t("cli.help.device"))
    p.add_argument("target")
    p.add_argument("device")
    p.add_argument("--mic", action="store_true", help=i18n.t("cli.help.mic_flag"))

    p = sub.add_parser("new", help=i18n.t("cli.help.new"))
    p.add_argument("target")
    p.add_argument("name")

    p = sub.add_parser("favorite", help=i18n.t("cli.help.favorite"))
    p.add_argument("action", choices=("add", "remove", "list"))
    p.add_argument("target")
    p.add_argument("name", nargs="?", default="")

    p = sub.add_parser("channel", help=i18n.t("cli.help.channel"))
    p.add_argument("action", choices=("add", "remove"))
    p.add_argument("name", help=i18n.t("cli.help.channel_name"))
    p.add_argument(
        "--direction", choices=("output", "input"), default="output",
        help=i18n.t("cli.help.add_only"),
    )
    p.add_argument("--color", default="#8B95A5")

    p = sub.add_parser("smart", help=i18n.t("cli.help.smart"))
    p.add_argument("channel", help=i18n.t("cli.help.smart_channel"))
    p.add_argument("state", nargs="?", choices=("on", "off"), help=i18n.t("cli.help.show_only"))
    p.add_argument("--targets", nargs="*", metavar=i18n.t("cli.meta.channel"),
                   help=i18n.t("cli.help.smart_targets"))
    p.add_argument("--reduction-db", type=float, dest="reduction_db")
    p.add_argument("--threshold-db", type=float, dest="threshold_db")
    p.add_argument("--attack-ms", type=float, dest="attack_ms")
    p.add_argument("--hold-ms", type=float, dest="hold_ms")
    p.add_argument("--release-ms", type=float, dest="release_ms")

    p = sub.add_parser("obs", help=i18n.t("cli.help.obs"))
    p.add_argument("channel")
    p.add_argument("state", choices=("on", "off"))

    p = sub.add_parser("presets", help=i18n.t("cli.help.presets"))
    p.add_argument("target")

    p = sub.add_parser("import", help=i18n.t("cli.help.import"))
    p.add_argument("target")
    p.add_argument("file")
    p.add_argument("--name", help=i18n.t("cli.help.import_name"))

    p = sub.add_parser("export", help=i18n.t("cli.help.export"))
    p.add_argument("target")
    p.add_argument("name", nargs="?")
    p.add_argument("--file", help=i18n.t("cli.help.export_file"))
    p.add_argument("--autoeq", action="store_true", help=i18n.t("cli.help.autoeq"))

    p = sub.add_parser("reset", help=i18n.t("cli.help.reset"))
    p.add_argument("target")

    p = sub.add_parser("meters", help=i18n.t("cli.help.meters"))
    p.add_argument("--seconds", type=float, default=10.0, help=i18n.t("cli.help.seconds"))

    p = sub.add_parser("mic", help=i18n.t("cli.help.mic"))
    p.add_argument("chain", help=i18n.t("cli.help.mic_chain"))
    p.add_argument("what", choices=["stream", "sidetone"])
    p.add_argument("state", choices=["on", "off"])

    p = sub.add_parser("effect", help=i18n.t("cli.help.effect"))
    p.add_argument("action", choices=("list", "add", "remove", "move"))
    p.add_argument("target")
    p.add_argument("value", nargs="?", default="", help=i18n.t("cli.help.effect_value"))
    p.add_argument("--index", type=int, help=i18n.t("cli.help.effect_index"))

    sub.add_parser("install", help=i18n.t("cli.help.install"))
    p = sub.add_parser("uninstall", help=i18n.t("cli.help.uninstall"))
    p.add_argument("--purge", action="store_true", help=i18n.t("cli.help.purge"))

    p = sub.add_parser("lang", help=i18n.t("cli.help.lang"))
    p.add_argument("code", nargs="?", choices=sorted(i18n.LANGUAGES))

    sub.add_parser("reload", help=i18n.t("cli.help.reload"))
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
    "effect": _cmd_effect,
    "install": _cmd_install,
    "uninstall": _cmd_uninstall,
    "lang": _cmd_lang,
    "devices": _cmd_devices,
    "device": _cmd_device,
    "obs": _cmd_obs,
    "smart": _cmd_smart,
    "channel": _cmd_channel,
    "new": _cmd_new,
    "favorite": _cmd_favorite,
    "presets": _cmd_presets,
    "import": _cmd_import,
    "export": _cmd_export,
    "reset": _cmd_reset,
    "meters": _cmd_meters,
    "mic": _cmd_mic,
    "reload": _cmd_reload,
}


def _startup_language() -> str:
    """Dili diskten okur.

    Daemon'a **bağlanmadan önce** gerekiyor: `--help` çıktısı ve "daemon'a ulaşılamadı"
    mesajı da kullanıcının dilinde olmalı, ikisi de bağlantı kurulmadan basılıyor.
    Yapılandırma okunamıyorsa varsayılana düşülür — dil yüzünden komut çalışmamazlık
    etmemeli.
    """
    try:
        return config_mod.ConfigStore().load(create_missing=False).settings.language
    except (OSError, ValueError):
        return i18n.DEFAULT_LANGUAGE


def main(argv: list[str] | None = None) -> int:
    i18n.set_language(_startup_language())
    args = build_parser().parse_args(argv)
    return _COMMANDS[args.command](Client(), args)


if __name__ == "__main__":
    raise SystemExit(main())
