"""`SonarConfig` → `pipewire -c` ile çalıştırılabilir tam `graph.conf` metni.

Üretilen conf **tek bir** `pipewire` süreci içinde tüm sanal cihazları kurar: kanal
filter-chain'leri, iki bus, kanal→bus loopback'leri ve mikrofon zincirleri. Kanal başına
ayrı süreç ~18 süreç ve ~150 MB RSS demekti; hepsi tek conf'ta ~15 MB'a iniyor.

## Değişmez kural: conf profilden bağımsızdır

Conf'a **yalnızca yapısal** bilgi girer (hangi node'lar, hangi eklentiler, hangi linkler) ve
tüm DSP portları **bypass** başlangıç değeriyle yazılır. Gerçek profil değerleri daemon
açılışta ve her değişiklikte canlı yazımla uygulanır (`engine.control`).

Sebep: conf'un değişmesi süreci yeniden başlatmayı, yani ~200 ms ses kesintisini gerektirir.
EQ band'ı sürüklemek veya profil değiştirmek bunu asla tetiklememelidir. `test_confgen.py`
bunu doğrudan test eder.

## Determinizm

Aynı `SonarConfig` her zaman byte-eşdeğer metin üretir. `engine.supervisor` "yeniden inşa
gerekli mi?" kararını iki conf metnini karşılaştırarak verir, bu yüzden sözlük sırası ve
sayı biçimi sabittir.

CLI: `python -m sonar.engine.confgen [--config <yol>]` → stdout'a conf basar.
"""

from __future__ import annotations

import re
from typing import Any

from sonar.core.dsp.chain import build_chain, plan_chain
from sonar.core.model import (
    DEFAULT_OUTPUT_BUS,
    STREAM_BUS,
    Channel,
    MasterBus,
    MicChain,
    SonarConfig,
)

__all__ = [
    "dsp_node_for",
    "dsp_nodes",
    "generate",
    "generate_modules",
    "live_targets",
    "send_links",
]

#: Sanal düğümlerin oturum önceliği. 0 = "beni asla varsayılan cihaz seçme".
#: Hem kaynaklar hem sink'ler için 0: `sonar_personal` varsayılan sink seçilirse kendi
#: çıkışını kendine besler. Varsayılanı devralmak istendiğinde bunu `settings.
#: take_over_default_sink` açıkça, `pw-metadata` ile yapar.
VIRTUAL_SOURCE_PRIORITY = 0

#: `media.class` seçimi. PipeWire 1.6.8'de filter-chain `playback.props` içinde
#: `Audio/Source/Virtual` node'u kuramıyor (`can't add port: -28`), süreç ayakta kalır ama
#: hiçbir node oluşmaz. `Audio/Source` sorunsuz çalışıyor. Ayrıntı: .plan/02-confgen.md
VIRTUAL_SOURCE_CLASS = "Audio/Source"

#: Masaüstü ses arayüzlerinin cihazın yanında gösterdiği simge adları.
SINK_ICON = "audio-card"
SOURCE_ICON = "audio-input-microphone"

_HEADER = """# Sonar — PipeWire graf yapılandırması
#
# BU DOSYA OTOMATİK ÜRETİLİR. Elle yapılan değişiklikler bir sonraki yeniden inşada
# kaybolur; kalıcı değişiklik için ~/.config/sonar/config.toml dosyasını düzenleyin.
#
# Çalıştırma:  pipewire -c <bu dosya>
"""


def generate(cfg: SonarConfig) -> str:
    """Tam `graph.conf` metnini üretir."""
    rate = cfg.settings.sample_rate
    body = {
        "context.properties": {
            "log.level": 2,
            "default.clock.rate": rate,
            "default.clock.allowed-rates": [rate],
        },
        "context.spa-libs": {
            "audio.convert.*": "audioconvert/libspa-audioconvert",
            "support.*": "support/libspa-support",
        },
        "context.modules": generate_modules(cfg),
    }
    return _HEADER + "\n" + "\n".join(f"{key} = {_fmt(value, 0)}" for key, value in body.items())


def generate_modules(cfg: SonarConfig) -> list[dict]:
    """Conf'un `context.modules` listesi — asıl iş burada."""
    modules: list[dict] = [
        {
            "name": "libpipewire-module-rt",
            "args": {"nice.level": -11, "rt.prio": 88},
            "flags": ["ifexists", "nofail"],
        },
        {"name": "libpipewire-module-protocol-native"},
        {"name": "libpipewire-module-client-node"},
        {"name": "libpipewire-module-adapter"},
    ]

    rate = cfg.settings.sample_rate
    bands = cfg.settings.default_band_count

    for channel in cfg.ordered_channels():
        modules.append(_channel_chain(channel, rate, bands))
    for bus in cfg.ordered_buses():
        modules.append(_bus_chain(bus, rate, bands))
    # Her kanaldan **her** bus'a bir gönderi. Kanalın hangi çıkışa gittiği conf'a
    # girmez; yalnızca hangi gönderinin açık olduğu değişir (`supervisor.live_volumes`).
    # Böylece kanalı başka bir cihaza taşımak grafı yeniden kurmuyor.
    for channel in cfg.ordered_channels():
        for bus in cfg.ordered_buses():
            modules.append(_send_loopback(channel, bus, rate))
    for mic in cfg.mic_chains:
        modules.extend(_mic_modules(mic, cfg, rate, bands))
    return modules


def dsp_nodes(cfg: SonarConfig) -> dict[str, str]:
    """Profil hedefi → DSP portlarını taşıyan node adı.

    Filter-chain'in kontrol portları **capture** node'unda açığa çıkar, playback'te değil
    (ölçülerek doğrulandı: `sonar_mic_capture` 315 port, `sonar_mic` 0). Kanal ve bus'larda
    capture node'u zaten sink'in kendisidir; mikrofonda ayrı bir `_capture` node'udur.

    Bu eşleme burada duruyor çünkü node adlarını üreten tek yer burası; `engine.control`
    ve `engine.supervisor` adları tahmin etmek yerine buradan alır.
    """
    nodes = {channel.id: channel.sink_node for channel in cfg.channels}
    nodes.update({bus.id: bus.sink_node for bus in cfg.buses})
    nodes.update(
        {
            mic.id: mic.source_node if mic.share_chain_with_mic else f"{mic.source_node}_capture"
            for mic in cfg.mic_chains
        }
    )
    return nodes


def dsp_node_for(cfg: SonarConfig, target: str) -> str | None:
    """Tek bir hedefin DSP node'u; hedef yoksa `None`."""
    return dsp_nodes(cfg).get(target)


# --------------------------------------------------------------------------- kanallar


def _channel_chain(channel: Channel, rate: int, bands: int) -> dict:
    """Bir kanal: `sonar_<id>` (Audio/Sink) → DSP → `sonar_<id>_fx`.

    `_fx` node'u iki modda kurulur:

    * `channel.stream_source` **açık** → `Audio/Source`. OBS onu kanal başına ayrı bir
      track olarak yakalayabilir; bedeli, kanalın sistemin mikrofon listesinde de
      görünmesidir.
    * **kapalı** (varsayılan) → `media.class` yok, `node.autoconnect = false`. Node
      hâlâ zincirin çıkışıdır ama bir *cihaz* değildir, hiçbir listede görünmez.
      Gönderi bağlantılarını daemon `pw-link` ile açıkça kurar (`send_links`).
    """
    playback = {
        "node.name": channel.fx_node,
        "node.autoconnect": False,
        **_stereo(rate),
    }
    if channel.stream_source:
        playback |= {
            "node.description": f"Sonar {channel.name} — Stream Source (Virtual Input)",
            "node.nick": f"{channel.name} Stream",
            "media.class": VIRTUAL_SOURCE_CLASS,
            "device.icon-name": SOURCE_ICON,
            "priority.session": VIRTUAL_SOURCE_PRIORITY,
        }
    else:
        playback["node.description"] = f"Sonar {channel.name} FX"

    return _filter_chain(
        description=f"Sonar {channel.name}",
        graph=_graph(rate, bands, channels=2),
        capture={
            "node.name": channel.sink_node,
            "node.description": f"Sonar {channel.name} — Virtual Output",
            "node.nick": channel.name,
            "media.class": "Audio/Sink",
            "device.icon-name": SINK_ICON,
            "priority.session": VIRTUAL_SOURCE_PRIORITY,
            **_stereo(rate),
        },
        playback=playback,
    )


def _send_loopback(channel: Channel, bus: MasterBus, rate: int) -> dict:
    """Kanalın `_fx` çıkışından bir bus'a giden gönderi. Fader bu node'a uygulanır.

    Yakalama tarafı bilinçli olarak **bağlantısız** doğar (`node.autoconnect = false`,
    `target.object` yok): `_fx` node'u `media.class` taşımadığında WirePlumber'ın
    yönlendirme politikası onu bir kaynak olarak görmez ve bağlamaz. Bağlantıyı
    `supervisor` graf ayağa kalktıktan sonra `pw-link` ile kendisi kurar. Tek kod yolu
    olsun diye bu, `stream_source` açıkken de böyle yapılır.
    """
    name = channel.loopback_node(bus.id)
    return {
        "name": "libpipewire-module-loopback",
        "args": {
            "node.description": f"Sonar {channel.name} → {bus.id}",
            "audio.position": ["FL", "FR"],
            "capture.props": {
                "node.name": f"{name}_capture",
                "node.passive": True,
                "node.autoconnect": False,
                "stream.capture.sink": False,
                **_stereo(rate),
            },
            "playback.props": {
                "node.name": name,
                "node.description": f"Sonar {channel.name}",
                "target.object": bus.sink_node,
                **_stereo(rate),
            },
        },
    }


def send_links(cfg: SonarConfig) -> list[tuple[str, str]]:
    """Daemon'ın `pw-link` ile kurması gereken (çıkış node'u, giriş node'u) çiftleri.

    Node adı verildiğinde `pw-link` iki node'un portlarını sırayla eşleştirir; port
    adlarını burada sabitlemiyoruz çünkü `_fx`'in çıkış portları moda göre
    `capture_FL` (Audio/Source) veya `output_FL` (sınıfsız) adını alıyor.
    """
    return [
        (channel.fx_node, f"{channel.loopback_node(bus.id)}_capture")
        for channel in cfg.ordered_channels()
        for bus in cfg.ordered_buses()
    ]


def live_targets(cfg: SonarConfig) -> dict[str, str]:
    """Canlı yazılacak `node adı → hedef cihaz` eşlemesi.

    Bu değerler bilinçli olarak conf'un **dışında** tutuluyor: `pw-metadata <node-id>
    target.object <cihaz>` bir akışı kesintisiz taşıyor (ölçüldü: `sonar_personal_out`
    Arctis ↔ Realtek arası gidip geldi, kesinti kayıt gürültüsünün üstüne çıkmadı).
    Conf'a yazılsaydı her cihaz değişimi ~200 ms'lik bir yeniden kurulum olurdu.

    Boş dize "hedef verme" demek — WirePlumber sistem varsayılanına bağlar.
    """
    targets = {bus.out_node: bus.device for bus in cfg.output_buses()}
    targets.update(
        {
            f"{mic.source_node}_capture": mic.source_device
            for mic in cfg.mic_chains
            if not mic.share_chain_with_mic
        }
    )
    return {node: device for node, device in targets.items() if device}


# --------------------------------------------------------------------------- bus'lar


def _bus_chain(bus: MasterBus, rate: int, bands: int) -> dict:
    """Bir bus: `sonar_<id>` (Audio/Sink) → master DSP → çıkış.

    Personal bus'ın çıkışı fiziksel cihaza giden bir akıştır. Stream bus'ın çıkışı ise
    `Audio/Source` olarak açığa çıkar; OBS onu "Sonar Stream Mix" adlı bir giriş cihazı
    olarak görür. Böylece yayın miksi hoparlöre gitmez.
    """
    if bus.is_stream:
        playback = {
            "node.name": bus.out_node,
            "node.description": f"Sonar {bus.name} — Virtual Input",
            "node.nick": bus.name,
            "media.class": VIRTUAL_SOURCE_CLASS,
            "device.icon-name": SOURCE_ICON,
            "priority.session": VIRTUAL_SOURCE_PRIORITY,
            **_stereo(rate),
        }
    else:
        # Hedef cihaz conf'a **yazılmaz**: `pw-metadata <id> target.object <cihaz>` ile
        # canlı veriliyor (bkz. `live_targets`). Conf'a yazılsaydı cihaz değiştirmek
        # conf metnini değiştirir, yani grafı yeniden kurar ve çalan sesi keserdi.
        playback = {
            "node.name": bus.out_node,
            "node.description": f"Sonar {bus.name} Output",
            **_stereo(rate),
        }

    return _filter_chain(
        description=f"Sonar {bus.name}",
        graph=_graph(rate, bands, channels=2),
        capture={
            "node.name": bus.sink_node,
            "node.description": f"Sonar {bus.name} — Virtual Output",
            "node.nick": bus.name,
            "media.class": "Audio/Sink",
            "device.icon-name": SINK_ICON,
            "priority.session": VIRTUAL_SOURCE_PRIORITY,
            **_stereo(rate),
        },
        playback=playback,
    )


# --------------------------------------------------------------------------- mikrofon


def _mic_modules(mic: MicChain, cfg: SonarConfig, rate: int, bands: int) -> list[dict]:
    """Mikrofon zinciri + opsiyonel sidetone / yayına gönderi loopback'leri."""
    modules: list[dict] = []

    if mic.share_chain_with_mic:
        # Kendi DSP'si yok: birincil mikrofonun çıkışını ikinci bir sanal kaynağa kopyalar.
        modules.append(
            {
                "name": "libpipewire-module-loopback",
                "args": {
                    "node.description": f"Sonar {mic.name}",
                    "audio.position": ["FL", "FR"],
                    "capture.props": {
                        "node.name": f"{mic.source_node}_capture",
                        "node.passive": True,
                        "target.object": _primary_mic(cfg).source_node,
                        "stream.capture.sink": False,
                        **_stereo(rate),
                    },
                    "playback.props": {
                        "node.name": mic.source_node,
                        "node.description": f"Sonar {mic.name} — Virtual Input",
                        "node.nick": mic.name,
                        "media.class": VIRTUAL_SOURCE_CLASS,
                        "device.icon-name": SOURCE_ICON,
                        "priority.session": VIRTUAL_SOURCE_PRIORITY,
                        **_stereo(rate),
                    },
                },
            }
        )
    else:
        # `mic.source_device` de conf'a girmez; `live_targets` canlı yazar.
        capture = {
            "node.name": f"{mic.source_node}_capture",
            "node.description": f"Sonar {mic.name} Input",
            "node.passive": True,
            "stream.capture.sink": False,
            **_stereo(rate),
        }
        modules.append(
            _filter_chain(
                description=f"Sonar {mic.name}",
                graph=_graph(rate, bands, channels=2, mic=True),
                capture=capture,
                playback={
                    "node.name": mic.source_node,
                    "node.description": f"Sonar {mic.name} — Virtual Input",
                    "node.nick": mic.name,
                    "media.class": VIRTUAL_SOURCE_CLASS,
                    "device.icon-name": SOURCE_ICON,
                    "priority.session": VIRTUAL_SOURCE_PRIORITY,
                    **_stereo(rate),
                },
            )
        )

    # Her ikisi de **koşulsuz** kurulur; açma/kapama artık mute ile yapılıyor
    # (`supervisor.live_volumes`). Eskiden conf'a bağlıydı, yani sidetone'u açmak
    # grafı yeniden kurup çalan sesi kesiyordu.
    # Sidetone varsayılan çıkışa, yayın gönderisi yayın bus'ına gider.
    modules.append(_mic_send(mic, DEFAULT_OUTPUT_BUS, "monitor", cfg, rate))
    modules.append(_mic_send(mic, STREAM_BUS, "to_stream", cfg, rate))
    return modules


def _mic_send(mic: MicChain, bus_id: str, suffix: str, cfg: SonarConfig, rate: int) -> dict:
    name = f"{mic.source_node}_{suffix}"
    bus = cfg.bus(bus_id) or cfg.default_output_bus()
    target = bus.sink_node if bus is not None else f"sonar_{bus_id}"
    return {
        "name": "libpipewire-module-loopback",
        "args": {
            "node.description": f"Sonar {mic.name} → {bus_id}",
            "audio.position": ["FL", "FR"],
            "capture.props": {
                "node.name": f"{name}_capture",
                "node.passive": True,
                "target.object": mic.source_node,
                "stream.capture.sink": False,
                **_stereo(rate),
            },
            "playback.props": {
                "node.name": name,
                "node.description": f"Sonar {mic.name}",
                "target.object": target,
                **_stereo(rate),
            },
        },
    }


def _primary_mic(cfg: SonarConfig) -> MicChain:
    for mic in cfg.mic_chains:
        if not mic.share_chain_with_mic:
            return mic
    raise ValueError("hiçbir mikrofon zinciri kendi DSP'sine sahip değil")


# --------------------------------------------------------------------------- ortak parçalar


def _filter_chain(*, description: str, graph: dict, capture: dict, playback: dict) -> dict:
    return {
        "name": "libpipewire-module-filter-chain",
        "args": {
            "node.description": description,
            "media.name": description,
            "filter.graph": graph,
            "capture.props": capture,
            "playback.props": playback,
        },
    }


def _graph(rate: int, bands: int, *, channels: int, mic: bool = False) -> dict:
    """DeepFilterNet yalnızca mikrofon zincirinde; oynatma zincirinde anlamı yok."""
    from sonar.core.model import CHAIN_ORDER, FilterStage

    stages = CHAIN_ORDER
    if not mic:
        stages = tuple(s for s in CHAIN_ORDER if s is not FilterStage.DEEPFILTER)
    del rate  # örnekleme hızı zincire değil, node özelliklerine yazılır
    return build_chain(plan_chain(stages, channels=channels, band_count=bands))


def _stereo(rate: int) -> dict:
    return {"audio.rate": rate, "audio.channels": 2, "audio.position": ["FL", "FR"]}


# --------------------------------------------------------------------------- SPA-JSON yazımı

_BARE_KEY = re.compile(r"^[A-Za-z0-9_.*-]+$")


def _fmt(value: Any, depth: int) -> str:
    pad, inner = "    " * depth, "    " * (depth + 1)
    if isinstance(value, dict):
        if not value:
            return "{}"
        rows = [f"{inner}{_key(k)} = {_fmt(v, depth + 1)}" for k, v in value.items()]
        return "{\n" + "\n".join(rows) + f"\n{pad}}}"
    if isinstance(value, list):
        if not value:
            return "[]"
        if all(isinstance(v, str | int | float | bool) for v in value):
            return "[ " + " ".join(_scalar(v) for v in value) + " ]"
        rows = [f"{inner}{_fmt(v, depth + 1)}" for v in value]
        return "[\n" + "\n".join(rows) + f"\n{pad}]"
    return _scalar(value)


def _key(key: str) -> str:
    return key if _BARE_KEY.match(key) else _quote(key)


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # Sabit biçim: determinizm buna bağlı. Tam sayı görünümlü değerler de float kalır.
        text = f"{value:.6f}".rstrip("0")
        return text + "0" if text.endswith(".") else text
    return _quote(str(value))


def _quote(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


# --------------------------------------------------------------------------- CLI


def _main(argv: list[str] | None = None) -> int:
    import argparse

    from sonar.core import config as config_mod

    parser = argparse.ArgumentParser(
        prog="python -m sonar.engine.confgen",
        description="Sonar yapılandırmasından PipeWire graph.conf üretir.",
    )
    parser.add_argument("--config", help="config.toml yolu (varsayılan: XDG)")
    args = parser.parse_args(argv)

    if args.config:
        from pathlib import Path

        path = Path(args.config)
        paths = config_mod.Paths(config_dir=path.parent, state_dir=path.parent)
        cfg = config_mod.ConfigStore(paths).load(create_missing=False)
    else:
        cfg = config_mod.load()

    print(generate(cfg), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
