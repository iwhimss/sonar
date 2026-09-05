"""DSP zincirinden PipeWire `filter.graph` sözlüğü üretir.

Zincir **profilin efekt listesinden** kuruluyor (şema 7). Bir efekti açıp kapatmak grafı
değiştirmez, yalnızca o slotun bypass portuna yazar (bkz. `params.stage_params`); ama efekt
**eklemek, silmek veya sıralamak** conf'u değiştirir ve süreci yeniden başlatır (~200 ms).
Aynı ayrım kanal ekleme/silmede de geçerli.

Eklenti sistemde **kurulu değilse** o slot zincirden düşer ve linkler yeniden bağlanır.

Node adları slot kimlikleridir (`eq`, `gate`, `comp2`), çünkü canlı parametre anahtarları
`"<node>:<port>"` biçimindedir: `"eq:g_3"`.
"""

from __future__ import annotations

from dataclasses import dataclass

from sonar.core.dsp import registry
from sonar.core.dsp.params import eq_bypass_ports, stage_bypass_ports
from sonar.core.model import EffectSlot, FilterStage

__all__ = ["ChainPlan", "StageBlock", "build_chain", "effect_block", "plan_chain"]


@dataclass(frozen=True, slots=True)
class StageBlock:
    """Bir aşamanın graf karşılığı: bir ya da **birden çok** node.

    Aşamaların çoğu tek bir eklenti node'u (`gate`, `eq`, …) ve bu sınıf onların da
    kapsayıcısı. Ama Spatial Audio altı node'dan oluşan bir alt graf, Volume Boost ise
    kanal başına bir node — PipeWire'ın `linear` ve `spatializer` eklentileri **mono**.

    `audio_in` / `audio_out` dışarıya açılan portlar, kanal sırasıyla ve
    `"node:port"` biçiminde tam nitelikli.
    """

    nodes: tuple[dict, ...]
    audio_in: tuple[str, ...]
    audio_out: tuple[str, ...]
    links: tuple[dict, ...] = ()


@dataclass(frozen=True, slots=True)
class ChainPlan:
    """Bir zincirin çözülmüş hâli: hangi slotlar var, her biri hangi eklentiyle."""

    slots: tuple[EffectSlot, ...]
    #: Slot kimliği → eklenti. Builtin bloklar (Spatial, Boost) burada yok.
    plugins: dict[str, registry.PluginSpec]
    channels: int
    skipped: tuple[EffectSlot, ...]

    @property
    def eq_capacity(self) -> int:
        """EQ eklentisinin band kapasitesi; EQ yoksa 0."""
        for effect in self.slots:
            if effect.kind is FilterStage.EQ:
                spec = self.plugins.get(effect.slot)
                return spec.band_capacity if spec else 0
        return 0


def plan_chain(
    slots: tuple[EffectSlot, ...],
    *,
    channels: int = 2,
    band_count: int = 10,
    require_installed: bool = True,
) -> ChainPlan:
    """İstenen slotlardan kurulabilir olanları **verilen sırayla** seçer.

    Sıra artık `CHAIN_ORDER` değil kullanıcının dizdiği sıra: EasyEffects'te olduğu gibi
    sinyal listedeki sırayla akıyor.

    `require_installed` yalnızca testlerde kapatılır; çalışma zamanında eksik eklenti
    zincirden düşmelidir, aksi hâlde `pipewire -c` grafı hiç kuramaz.
    """
    if channels not in (1, 2):
        raise ValueError(f"kanal sayısı 1 veya 2 olmalı, {channels} verildi")

    kept: list[EffectSlot] = []
    skipped: list[EffectSlot] = []
    plugins: dict[str, registry.PluginSpec] = {}

    for effect in slots:
        # Boost ve Spatial bir LV2/LADSPA eklentisine dayanmıyor; katalogda yoklar.
        if effect.kind is FilterStage.BOOST:
            kept.append(effect)
            continue
        if effect.kind is FilterStage.SPATIAL:
            # Crossfeed PipeWire'ın kendi bloklarıyla kuruluyor: kurulum gerektirmiyor.
            # Mono zincirde (mikrofon) kulaklık simülasyonunun karşılığı yok.
            (kept if channels == 2 else skipped).append(effect)
            continue
        key = _plugin_key(effect.kind, channels, band_count)
        if key is None or (require_installed and not registry.is_available(key)):
            skipped.append(effect)
            continue
        plugins[effect.slot] = registry.plugin(key)
        kept.append(effect)

    return ChainPlan(tuple(kept), plugins, channels, tuple(skipped))


def build_chain(plan: ChainPlan) -> dict:
    """`ChainPlan`'ı PipeWire `filter.graph` sözlüğüne çevirir.

    Boş bir zincir (kullanıcı tüm efektleri sildi, ya da hiçbir eklenti kurulu değil) için
    aşamasız bir graf döndürmek anlamsız olurdu — çağıran taraf `plan.slots` boşsa
    filter-chain yerine düz bir loopback kurmalıdır. Bu durumda `ValueError` atılır.
    """
    if not plan.slots:
        raise ValueError("zincirde hiç efekt yok; filter-chain yerine loopback kullanın")

    blocks = [effect_block(effect, plan, plan.channels) for effect in plan.slots]

    nodes: list[dict] = []
    links: list[dict] = []
    for block in blocks:
        nodes.extend(block.nodes)
    # Link sırası: her bloğun kendi iç linkleri, sonra bir sonrakine geçiş. Tek node'lu
    # aşamalarda iç link yok, yani bu sıra eski `pairwise` düzeniyle birebir aynı —
    # mevcut altın conf byte olarak değişmiyor.
    for index, block in enumerate(blocks):
        links.extend(block.links)
        if index + 1 < len(blocks):
            nxt = blocks[index + 1]
            for channel in range(plan.channels):
                links.append({"output": block.audio_out[channel], "input": nxt.audio_in[channel]})

    graph: dict = {
        "nodes": nodes,
        "inputs": list(blocks[0].audio_in),
        "outputs": list(blocks[-1].audio_out),
    }
    if links:
        graph["links"] = links
    return graph


def effect_block(effect: EffectSlot, plan: ChainPlan, channels: int) -> StageBlock:
    """Bir slotun node'ları, iç linkleri ve dışarı açılan portları."""
    if effect.kind is FilterStage.SPATIAL:
        return _spatial_block(effect.slot, channels)
    if effect.kind is FilterStage.BOOST:
        return _boost_block(effect.slot, channels)
    spec = plan.plugins[effect.slot]
    return StageBlock(
        nodes=(_node(effect, spec),),
        audio_in=tuple(f"{effect.slot}:{p}" for p in spec.audio_in[:channels]),
        audio_out=tuple(f"{effect.slot}:{p}" for p in spec.audio_out[:channels]),
    )


# --------------------------------------------------------------------------- Volume Boost


def _boost_block(slot: str, channels: int) -> StageBlock:
    """Kanal başına bir PipeWire `linear` node'u.

    `linear` mono: `Out = In * Mult + Add`. Bypass `Mult = 1.0`, yani conf bypass'ta
    doğuyor ve boost'u açıp kapatmak grafı değiştirmiyor.
    """
    names = _channel_names(slot, channels)
    nodes = tuple(
        {
            "type": registry.PluginKind.BUILTIN.value,
            "name": name,
            "label": "linear",
            "control": {"Mult": 1.0, "Add": 0.0},
        }
        for name in names
    )
    return StageBlock(
        nodes=nodes,
        audio_in=tuple(f"{name}:In" for name in names),
        audio_out=tuple(f"{name}:Out" for name in names),
    )


# --------------------------------------------------------------------------- Spatial Audio


def _spatial_block(slot: str, channels: int) -> StageBlock:
    """Spatial Audio — kulaklar arası sızıntı (crossfeed).

    Alt graf (stereo):

    ```
    cp_l ─┬──────────────────────────────────► mix_l:"In 1"   (doğrudan)
          └─► delay_l ─► lowpass_l ──────────► mix_r:"In 2"   (karşı kulağa sızıntı)
    cp_r ─┬──────────────────────────────────► mix_r:"In 1"
          └─► delay_r ─► lowpass_r ──────────► mix_l:"In 2"
    ```

    Gerçek hoparlörlerde sol hoparlörün sesi sağ kulağa da ulaşır: biraz geç ve kafanın
    gölgelediği tizler kısılmış hâlde. Kulaklıkta bu hiç olmaz, ses "kafanın içinde"
    kalır. Blok tam bunu geri koyuyor — `delay` gecikmeyi, `bq_lowpass` kafa gölgesini.

    ## Neden HRTF değil

    İlk sürüm PipeWire'ın `sofa` `spatializer`'ıyla iki sanal hoparlör kuruyordu.
    Ölçüm onu çürüttü: ses akan tek bir kanalda tek çekirdeğin **%17'sini** yiyordu ve
    bir konvolveri bypass etmek onu ucuzlatmadığı için aşamayı açıp kapatmak grafı
    yeniden kurmayı gerektiriyordu (boştaki CPU %0.0 → %14.4). Kullanıcı bunun yerine
    ucuz bir çözüm istedi.

    Burada her şey PipeWire'ın kendi `builtin` blokları: bir gecikme hattı, bir biquad
    ve bir mikser. Bypass mikserin sızıntı kazancını 0 yapmak, yani **bit-şeffaf** ve
    graf hiç değişmiyor. Ölçüldü: kapalıyken sol-tek sinyal L=-17.0 / R=-240 dBFS,
    açıkken R=-23.0 dBFS ve kulaklar arası gecikme 0.40 ms.

    Bu gerçek bir surround simülasyonu değil, stereo sahnenin kafanın dışına çıkması.
    """
    if channels != 2:  # pragma: no cover - plan_chain buraya izin vermez
        raise ValueError("Spatial Audio yalnızca stereo zincirde kurulabilir")

    nodes = (
        _builtin(f"{slot}_copy_l", "copy"),
        _builtin(f"{slot}_copy_r", "copy"),
        _delay(f"{slot}_delay_l"),
        _delay(f"{slot}_delay_r"),
        _lowpass(f"{slot}_lp_l"),
        _lowpass(f"{slot}_lp_r"),
        _mixer(f"{slot}_mix_l"),
        _mixer(f"{slot}_mix_r"),
    )
    links = (
        {"output": f"{slot}_copy_l:Out", "input": f"{slot}_mix_l:In 1"},
        {"output": f"{slot}_copy_r:Out", "input": f"{slot}_mix_r:In 1"},
        {"output": f"{slot}_copy_l:Out", "input": f"{slot}_delay_l:In"},
        {"output": f"{slot}_copy_r:Out", "input": f"{slot}_delay_r:In"},
        {"output": f"{slot}_delay_l:Out", "input": f"{slot}_lp_l:In"},
        {"output": f"{slot}_delay_r:Out", "input": f"{slot}_lp_r:In"},
        # Sol kanalın sızıntısı **sağ** kulağa gider, sağınki sola.
        {"output": f"{slot}_lp_l:Out", "input": f"{slot}_mix_r:In 2"},
        {"output": f"{slot}_lp_r:Out", "input": f"{slot}_mix_l:In 2"},
    )
    return StageBlock(
        nodes=nodes,
        audio_in=(f"{slot}_copy_l:In", f"{slot}_copy_r:In"),
        audio_out=(f"{slot}_mix_l:Out", f"{slot}_mix_r:Out"),
        links=links,
    )


def _delay(name: str) -> dict:
    """Gecikme hattı. `max-delay` en uzun "Mesafe" ayarını kapsamalı."""
    node = _builtin(name, "delay", {"Delay (s)": 0.0})
    node["config"] = {"max-delay": 0.01}
    return node


def _lowpass(name: str) -> dict:
    """Kafa gölgesi: sızıntının tizleri kısılır."""
    return _builtin(name, "bq_lowpass", {"Freq": 1000.0, "Q": 0.707})


def _builtin(name: str, label: str, control: dict | None = None) -> dict:
    node = {"type": registry.PluginKind.BUILTIN.value, "name": name, "label": label}
    if control:
        node["control"] = control
    return node


def _mixer(name: str) -> dict:
    """Doğrudan sinyal + karşı kanaldan sızıntı. Bypass: sızıntı kazancı 0."""
    return _builtin(name, "mixer", {"Gain 1": 1.0, "Gain 2": 0.0})


def _sofa(name: str, config: dict) -> dict:
    return {
        "type": registry.PluginKind.SOFA.value,
        "name": name,
        "label": "spatializer",
        "config": config,
        "control": {"Azimuth": 0.0, "Elevation": 0.0, "Radius": 1.0},
    }


def _channel_names(slot: str, channels: int) -> tuple[str, ...]:
    """Kanal başına node adı. Mono zincirde sonek yok, stereo'da `_l` / `_r`."""
    if channels == 1:
        return (slot,)
    return (f"{slot}_l", f"{slot}_r")


def _node(effect: EffectSlot, spec: registry.PluginSpec) -> dict:
    node: dict = {
        "type": spec.kind.value,
        "name": effect.slot,
        "plugin": registry.plugin_reference(spec),
    }
    if spec.kind is registry.PluginKind.LADSPA:
        node["label"] = spec.label
    node["control"] = _neutral_control(effect.kind, spec)
    return node


def _neutral_control(stage: FilterStage, spec: registry.PluginSpec) -> dict[str, float]:
    """Conf'a yazılacak **başlangıç** değerleri.

    Bilinçli olarak nötr: her aşama bypass'ta doğar. Gerçek profil değerleri daemon açılışta
    canlı yazımla uygular. Aksi hâlde her EQ dokunuşu conf'u değiştirir ve süreci yeniden
    başlatırdı — Faz 2'nin en önemli kısıtı bu.
    """
    ports = eq_bypass_ports(spec) if stage is FilterStage.EQ else stage_bypass_ports(stage)
    return {port: spec.clamp(port, value) for port, value in ports.items()}


def _plugin_key(stage: FilterStage, channels: int, band_count: int) -> str | None:
    """Aşamanın eklenti anahtarı; katalogda karşılığı yoksa `None`."""
    if stage is FilterStage.EQ:
        return registry.eq_plugin_for(band_count, channels=channels).key
    suffix = "mono" if channels == 1 else "stereo"
    return {
        FilterStage.DEEPFILTER: f"deepfilter_{suffix}",
        FilterStage.GATE: f"lsp_gate_{suffix}",
        FilterStage.COMP: f"lsp_compressor_{suffix}",
        FilterStage.LIMITER: f"lsp_limiter_{suffix}",
    }.get(stage)
