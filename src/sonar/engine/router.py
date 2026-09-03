"""Uygulama akışlarını kanallara dağıtan kural motoru.

Yeni bir ses akışı açıldığında hangi kanala gideceğine karar verir ve oraya taşır.

## Neden her akış yalnızca **bir kez** yönlendirilir

Bir akışı sürekli izleyip "yanlış yerdeyse geri al" yaklaşımı kullanıcıyla kavga eder:
pavucontrol'den elle taşıdığı akışı anında geri çekeriz. Ayrıca akışın gerçekte nereye
bağlı olduğunu `target.object`'ten güvenilir biçimde okuyamıyoruz — WirePlumber kendi
bağladığında bu alan boş kalıyor.

Bunun yerine her akış **ilk görüldüğünde** bir kez karar alınır, sonra bir daha
dokunulmaz. Kullanıcının elle taşıması kalıcı olur, kural motoru sessizce arka planda
kalır. Akış kapanınca kaydı silinir; aynı uygulama yeniden açıldığında kural yeniden
uygulanır.

Kayıtlar node **id**'siyle değil `object.serial` ile tutulur. PipeWire id'leri geri
dönüştürüyor: bir akış kapanıp hemen yenisi açıldığında aynı id'yi alabiliyor ve silinme
olayı bize ulaşmadan önce yeni akış "zaten karar verilmiş" sanılıyordu — ölçümde beş
akıştan ikisi bu yüzden yönlendirilmedi. `object.serial` artan ve asla tekrarlanmayan bir
sayaç.

## Eşleştirme

Öncelik sırası `MatchKey.priority` ile sabit: `binary` → `app_name` → `media_name`.
`application.process.binary` en güvenilir olan, çünkü kullanıcının dilinden ve pencere
başlığından bağımsız. Aynı öncelikte birden fazla kural eşleşirse daha spesifik (daha uzun
desenli) olan kazanır.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from sonar.core.model import MatchKey, RoutingRule, SonarConfig
from sonar.engine.pwstate import GraphState, StreamInfo

__all__ = ["Decision", "Router", "choose_channel", "stream_value"]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Decision:
    """Bir akış için alınan yönlendirme kararı."""

    stream_id: int
    channel_id: str
    reason: str  # "rule" | "default"
    pattern: str = ""
    #: Akışın ilk görülmesinden taşımanın tamamlanmasına kadar geçen süre (saniye).
    latency: float = 0.0

    @property
    def by_rule(self) -> bool:
        return self.reason == "rule"


def stream_value(stream: StreamInfo, key: MatchKey) -> str:
    """Kuralın baktığı akış özelliği."""
    return {
        MatchKey.BINARY: stream.app_binary,
        MatchKey.APP_NAME: stream.app_name,
        MatchKey.MEDIA_NAME: stream.media_name,
    }[key]


def choose_channel(stream: StreamInfo, config: SonarConfig) -> tuple[str, RoutingRule | None]:
    """Akışın gideceği kanalı seçer. Eşleşme yoksa varsayılan kanala düşer."""
    candidates = [
        rule
        for rule in config.rules
        if rule.enabled
        and config.channel(rule.channel_id) is not None
        and rule.matches(stream_value(stream, MatchKey(rule.match_key)))
    ]
    if candidates:
        # Küçük öncelik sayısı daha güvenilir; eşitlikte daha spesifik desen kazanır.
        best = min(
            candidates,
            key=lambda r: (MatchKey(r.match_key).priority, -r.specificity, r.pattern),
        )
        return best.channel_id, best

    fallback = config.settings.default_channel
    if config.channel(fallback) is None:  # pragma: no cover - config bozulmuşsa
        first = config.ordered_channels()
        fallback = first[0].id if first else ""
    return fallback, None


class Router:
    """Kural motorunu canlı grafa bağlar."""

    def __init__(
        self,
        state: GraphState,
        move: Callable[[int, str], bool],
        config_provider: Callable[[], SonarConfig],
        *,
        on_route: Callable[[Decision], None] | None = None,
        enabled: bool = True,
    ) -> None:
        self.state = state
        self.move = move
        self.config_provider = config_provider
        self.on_route = on_route
        self.enabled = enabled
        #: Karar verilmiş akışlar: `object.serial → kanal`. Neden id değil, bkz. modül başlığı.
        self._decided: dict[int, str] = {}

    # ------------------------------------------------------------------ ana akış

    def sync(self) -> list[Decision]:
        """Envanterdeki yeni akışlara karar verir ve taşır.

        `pwstate` her değişiklikte çağırır. Kapanmış akışların kaydını da temizler ki
        PipeWire id'leri geri dönüştürdüğünde yeni akış "zaten karar verilmiş" sanılmasın.
        """
        streams = self.state.streams
        self._forget_closed(streams)
        if not self.enabled:
            return []

        config = self.config_provider()
        decisions: list[Decision] = []
        for stream in list(streams.values()):
            decision = self._route(stream, config)
            if decision is not None:
                decisions.append(decision)
        return decisions

    def mark_manual(self, stream_id: int, channel_id: str) -> None:
        """Kullanıcı bir akışı elle taşıdı; kural motoru bir daha dokunmasın."""
        key = self._key_for(int(stream_id))
        if key is not None:
            self._decided[key] = channel_id

    def forget(self, stream_id: int) -> None:
        key = self._key_for(int(stream_id))
        if key is not None:
            self._decided.pop(key, None)

    def _key_for(self, stream_id: int) -> int | None:
        stream = self.state.streams.get(stream_id)
        if stream is None:
            return None
        return stream.serial or stream.id

    def reset(self) -> None:
        """Kayıtları tümden unutur."""
        self._decided.clear()

    def forget_channel(self, channel_id: str) -> None:
        """Silinen bir kanala verilmiş kararları unutur; akışlar yeniden dağıtılır."""
        for key in [k for k, v in self._decided.items() if v == channel_id]:
            del self._decided[key]

    def reassert(self, node_exists: Callable[[str], bool] | None = None) -> list[Decision]:
        """Yeniden inşadan sonra akışları kararlarının üstüne geri oturtur.

        Eskiden burada `reset()` çağrılıyordu ve sonuç şuydu: kayıtlar silinince
        `sync()` akışlara yeniden bakıyor, ama `_is_routable` hedefi `sonar_` ile
        başlayan akışı "kullanıcı kendi seçmiş" sayıp atlıyordu. Yani **hiçbir akış
        yeniden yerleştirilmiyordu** ve akışın nereye bağlanacağı WirePlumber'ın
        eline kalıyordu. Test turu 2'deki "cihaz değiştirince ses gidiyor" ve
        "kanal değiştirince ses kesiliyor" şikâyetlerinin ikinci ayağı buydu.

        Yeniden inşa kararı **geçersiz kılmaz**, yalnızca node id'lerini eskitir. Bu
        yüzden karar korunur ve taşıma tekrarlanır.
        """
        config = self.config_provider()
        decisions: list[Decision] = []
        for stream in list(self.state.streams.values()):
            key = stream.serial or stream.id
            channel_id = self._decided.get(key)
            if channel_id is None:
                continue
            channel = config.channel(channel_id)
            if channel is None:
                # Kanal silinmiş: kararı unut, `sync()` yeniden karar versin.
                del self._decided[key]
                continue
            if node_exists is not None and not node_exists(channel.sink_node):
                continue
            if self.move(stream.id, channel.sink_node):
                decisions.append(Decision(stream.id, channel_id, "reassert"))
            else:
                log.warning(
                    "akış yeniden oturtulamadı: #%s (%s) → %s",
                    stream.id,
                    stream.label,
                    channel_id,
                )
        if decisions:
            log.info("%d akış yeniden inşadan sonra yerine oturtuldu", len(decisions))
        return decisions

    @property
    def decided(self) -> dict[int, str]:
        return dict(self._decided)

    # ------------------------------------------------------------------ iç kısım

    def _route(self, stream: StreamInfo, config: SonarConfig) -> Decision | None:
        key = stream.serial or stream.id
        if key in self._decided:
            return None
        if not self._is_routable(stream):
            return None

        channel_id, rule = choose_channel(stream, config)
        channel = config.channel(channel_id)
        if channel is None:  # pragma: no cover - kanalsız yapılandırma
            return None

        # Kararı taşımadan **önce** kaydet: taşıma başarısız olsa bile aynı akışı her
        # olayda yeniden denemeyelim; aksi hâlde saniyede onlarca taşıma çağrısı olur.
        self._decided[key] = channel_id
        if not self.move(stream.id, channel.sink_node):
            log.warning("akış taşınamadı: #%s (%s) → %s", stream.id, stream.label, channel_id)
            return None

        seen_at = self.state.stream_seen.get(stream.id)
        latency = time.monotonic() - seen_at if seen_at is not None else 0.0
        decision = Decision(
            stream.id,
            channel_id,
            "rule" if rule is not None else "default",
            rule.pattern if rule is not None else "",
            latency,
        )
        log.info(
            "yönlendirildi: #%s %s → %s (%s) — %.1f ms",
            stream.id,
            stream.label,
            channel_id,
            decision.pattern or "varsayılan",
            latency * 1000,
        )
        if self.on_route is not None:
            try:
                self.on_route(decision)
            except Exception:  # pragma: no cover - dinleyici hatası yönlendirmeyi durdurmasın
                log.exception("yönlendirme dinleyicisi hata verdi")
        return decision

    @staticmethod
    def _is_routable(stream: StreamInfo) -> bool:
        """Kendi tesisatımıza ve kayıt akışlarına dokunmuyoruz."""
        if stream.is_internal or stream.is_capture:
            return False
        # Hedefi zaten bir Sonar kanalı olan akış (uygulama kendi seçmiş olabilir) korunur.
        return not stream.target_node.startswith("sonar_")

    def _forget_closed(self, streams: dict[int, StreamInfo]) -> None:
        alive = {stream.serial or stream.id for stream in streams.values()}
        for key in [k for k in self._decided if k not in alive]:
            del self._decided[key]
