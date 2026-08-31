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
from sonar.core.model import BusId, Channel, MasterBus, MicChain, SonarConfig

__all__ = ["dsp_node_for", "dsp_nodes", "generate", "generate_modules"]

#: Sanal kaynakların oturum önceliği. 0 = "beni asla varsayılan mikrofon seçme".
#: EasyEffects'in `easyeffects_source` için kullandığı değerin aynısı; sistemdeki gerçek
#: mikrofonlar 2009–2100 aralığında olduğu için bu onları geride bırakmaz.
VIRTUAL_SOURCE_PRIORITY = 0

#: `media.class` seçimi. PipeWire 1.6.8'de filter-chain `playback.props` içinde
#: `Audio/Source/Virtual` node'u kuramıyor (`can't add port: -28`), süreç ayakta kalır ama
#: hiçbir node oluşmaz. `Audio/Source` sorunsuz çalışıyor. Ayrıntı: .plan/02-confgen.md
VIRTUAL_SOURCE_CLASS = "Audio/Source"

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
    for bus in sorted(cfg.buses, key=lambda b: b.id.value):
        modules.append(_bus_chain(bus, rate, bands))
    for channel in cfg.ordered_channels():
        for bus in BusId:
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
    nodes.update({bus.id.value: bus.sink_node for bus in cfg.buses})
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
    """Bir kanal: `sonar_<id>` (Audio/Sink) → DSP → `sonar_<id>_fx` (Audio/Source).

    `_fx` ayrı bir sanal kaynak olduğu için OBS onu kanal başına ayrı bir track olarak
    yakalayabilir; bize ek loopback maliyeti çıkarmaz çünkü zaten zincirin çıkışıdır.
    """
    return _filter_chain(
        description=f"Sonar {channel.name}",
        graph=_graph(rate, bands, channels=2),
        capture={
            "node.name": channel.sink_node,
            "node.description": f"Sonar {channel.name}",
            "media.class": "Audio/Sink",
            **_stereo(rate),
        },
        playback={
            "node.name": channel.fx_node,
            "node.description": f"Sonar {channel.name} (FX)",
            "media.class": VIRTUAL_SOURCE_CLASS,
            "priority.session": VIRTUAL_SOURCE_PRIORITY,
            **_stereo(rate),
        },
    )


def _send_loopback(channel: Channel, bus: BusId, rate: int) -> dict:
    """Kanalın `_fx` çıkışından bir bus'a giden gönderi. Fader bu node'a uygulanır."""
    name = channel.loopback_node(bus)
    return {
        "name": "libpipewire-module-loopback",
        "args": {
            "node.description": f"Sonar {channel.name} → {bus.value}",
            "audio.position": ["FL", "FR"],
            "capture.props": {
                "node.name": f"{name}_capture",
                "node.passive": True,
                "target.object": channel.fx_node,
                "stream.capture.sink": False,
                **_stereo(rate),
            },
            "playback.props": {
                "node.name": name,
                "node.description": f"Sonar {channel.name}",
                "target.object": _bus_node(bus),
                **_stereo(rate),
            },
        },
    }


# --------------------------------------------------------------------------- bus'lar


def _bus_chain(bus: MasterBus, rate: int, bands: int) -> dict:
    """Bir bus: `sonar_<id>` (Audio/Sink) → master DSP → çıkış.

    Personal bus'ın çıkışı fiziksel cihaza giden bir akıştır. Stream bus'ın çıkışı ise
    `Audio/Source` olarak açığa çıkar; OBS onu "Sonar Stream Mix" adlı bir giriş cihazı
    olarak görür. Böylece yayın miksi hoparlöre gitmez.
    """
    if bus.id is BusId.STREAM:
        playback = {
            "node.name": f"{bus.sink_node}_out",
            "node.description": f"Sonar {bus.name}",
            "media.class": VIRTUAL_SOURCE_CLASS,
            "priority.session": VIRTUAL_SOURCE_PRIORITY,
            **_stereo(rate),
        }
    else:
        playback = {
            "node.name": f"{bus.sink_node}_out",
            "node.description": f"Sonar {bus.name} (çıkış)",
            **_stereo(rate),
        }
        # Cihaz boşsa hedef verilmez; WirePlumber sistem varsayılanına bağlar.
        if bus.device:
            playback["target.object"] = bus.device

    return _filter_chain(
        description=f"Sonar {bus.name}",
        graph=_graph(rate, bands, channels=2),
        capture={
            "node.name": bus.sink_node,
            "node.description": f"Sonar {bus.name}",
            "media.class": "Audio/Sink",
            **_stereo(rate),
        },
        playback=playback,
    )


def _bus_node(bus: BusId) -> str:
    return f"sonar_{bus.value}"


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
                        "node.description": f"Sonar {mic.name}",
                        "media.class": VIRTUAL_SOURCE_CLASS,
                        "priority.session": VIRTUAL_SOURCE_PRIORITY,
                        **_stereo(rate),
                    },
                },
            }
        )
    else:
        capture = {
            "node.name": f"{mic.source_node}_capture",
            "node.description": f"Sonar {mic.name} (giriş)",
            "node.passive": True,
            "stream.capture.sink": False,
            **_stereo(rate),
        }
        if mic.source_device:
            capture["target.object"] = mic.source_device
        modules.append(
            _filter_chain(
                description=f"Sonar {mic.name}",
                graph=_graph(rate, bands, channels=2, mic=True),
                capture=capture,
                playback={
                    "node.name": mic.source_node,
                    "node.description": f"Sonar {mic.name}",
                    "media.class": VIRTUAL_SOURCE_CLASS,
                    "priority.session": VIRTUAL_SOURCE_PRIORITY,
                    **_stereo(rate),
                },
            )
        )

    if mic.monitor_enabled:
        modules.append(_mic_send(mic, BusId.PERSONAL, "monitor", rate))
    if mic.send_to_stream_bus:
        modules.append(_mic_send(mic, BusId.STREAM, "to_stream", rate))
    return modules


def _mic_send(mic: MicChain, bus: BusId, suffix: str, rate: int) -> dict:
    name = f"{mic.source_node}_{suffix}"
    return {
        "name": "libpipewire-module-loopback",
        "args": {
            "node.description": f"Sonar {mic.name} → {bus.value}",
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
                "target.object": _bus_node(bus),
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
