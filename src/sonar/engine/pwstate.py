"""PipeWire graf durumunun izleyicisi.

`pw-dump -m` bir alt süreç olarak çalışır ve her değişiklikte stdout'a bir JSON dizisi
basar. Bu modül o akışı ayrıştırıp üç envanteri güncel tutar:

* `nodes` — `node.name → id`. Canlı parametre yazımı id ile yapıldığı için bu harita
  `engine.control`'ün çalışma koşuludur.
* `streams` — çalan uygulama akışları (Faz 5'teki yönlendirme kuralları bunları eşleştirir).
* `devices` — fiziksel sink/source envanteri (arayüzdeki cihaz seçicileri).

## Ayrıştırma kuralı

`pw-dump -m` ardışık JSON dizileri basar; her dizi 0. sütunda `[` ile başlar, 0. sütunda `]`
ile biter. Blok sınırı bu satırlardır — JSON'u satır satır ayrıştırmaya çalışmak yanlış olur,
çünkü tek bir olay binlerce satır sürebilir. Silinen nesneler `"info": null` ile gelir.

## Neden Qt yok

Plan `QProcess` diyordu; yerine `subprocess` + okuma iş parçacığı kullanıldı. Böylece
`engine/` katmanı Qt olay döngüsü olmadan da çalışır ve test edilebilir: ayrıştırma
mantığının tamamı (`EventSplitter`, `GraphState`) saf ve yan etkisizdir, süreç yönetimi
`PwMonitor` içinde ayrı durur. Daemon (Faz 4) callback'leri kendi olay döngüsüne bağlar.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

__all__ = [
    "DeviceInfo",
    "EventSplitter",
    "GraphState",
    "NodeInfo",
    "PwMonitor",
    "StreamInfo",
]

log = logging.getLogger(__name__)

#: Uygulama akışlarının `media.class` değerleri.
_STREAM_CLASSES = frozenset({"Stream/Output/Audio", "Stream/Input/Audio"})
_SINK_CLASSES = frozenset({"Audio/Sink"})
_SOURCE_CLASSES = frozenset({"Audio/Source", "Audio/Source/Virtual"})


@dataclass(frozen=True, slots=True)
class NodeInfo:
    id: int
    name: str
    media_class: str = ""
    description: str = ""


@dataclass(frozen=True, slots=True)
class StreamInfo:
    """Bir uygulamanın ses akışı — yönlendirme kurallarının eşleştirdiği nesne."""

    id: int
    #: PipeWire'ın **asla tekrar kullanmadığı** artan sayaç. `id` geri dönüştürülüyor:
    #: kapanan bir akışın id'si saniyeler içinde yeni bir akışa verilebiliyor. Yönlendirme
    #: kayıtları bu yüzden `serial` ile tutuluyor.
    serial: int = 0
    node_name: str = ""
    app_binary: str = ""
    app_name: str = ""
    media_name: str = ""
    target_node: str = ""
    pid: int = 0
    is_capture: bool = False
    #: Masaüstü sesini yakalıyor (`stream.capture.sink`), mikrofonu değil. cava, OBS'in
    #: "Masaüstü Sesi" kaynağı ve ekran kaydediciler böyle. Bunları mikrofon zincirine
    #: taşımak kullanıcının görselleştiricisini/kaydını bozar — ölçüldü: cava sessizce
    #: `sonar_mic`'e çekildi.
    captures_sink: bool = False

    @property
    def label(self) -> str:
        return self.app_name or self.app_binary or self.media_name or f"#{self.id}"

    @property
    def is_internal(self) -> bool:
        """Sonar'ın kendi tesisatı mı?

        Kanal→bus loopback'leri ve bus çıkışları da `Stream/Output/Audio` sınıfında görünüyor;
        envanterde dursunlar (graf doğru olsun) ama kullanıcıya "çalan uygulama" diye
        gösterilmesinler, yönlendirme kuralları da onlara dokunmasın.

        Ölçüm süreçlerimiz de buraya giriyor: `pw-cat` kendi adıyla doğduğunda mikserde
        yedi ayrı "pw-cat" uygulaması görünüyordu, bu yüzden `engine.meters` onlara
        `sonar_meter_<hedef>` adını veriyor.
        """
        return self.node_name.startswith("sonar_")


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    id: int
    name: str
    description: str = ""
    is_source: bool = False
    priority: int = 0


class EventSplitter:
    """`pw-dump -m` akışını olay bloklarına böler. Saf, süreçten habersiz."""

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._inside = False
        self._tail = ""

    def feed(self, chunk: str) -> Iterator[list[dict]]:
        """Gelen metin parçasını tüketir, tamamlanan her olayı üretir.

        Parça sınırı satır sınırıyla örtüşmeyebilir; yarım kalan satır `_tail`'de bekler.
        """
        self._tail += chunk
        *lines, self._tail = self._tail.split("\n")
        for line in lines:
            if line == "[":
                self._inside, self._lines = True, []
                continue
            if not self._inside:
                continue
            if line == "]":
                self._inside = False
                try:
                    yield json.loads("[" + "\n".join(self._lines) + "]")
                except json.JSONDecodeError:
                    log.warning("pw-dump çıktısı ayrıştırılamadı, olay atlandı")
                self._lines = []
                continue
            self._lines.append(line)


@dataclass
class GraphState:
    """Grafın anlık envanteri. Saf: yalnızca `apply()` ile değişir.

    `apply()` hangi envanterlerin değiştiğini döndürür; çağıran taraf yalnızca gerçekten
    değişenler için sinyal yayar. Aksi hâlde `pw-dump -m` saniyede onlarca olay ürettiği
    için arayüz gereksiz yere yeniden çizilirdi.
    """

    nodes: dict[str, int] = field(default_factory=dict)
    streams: dict[int, StreamInfo] = field(default_factory=dict)
    devices: dict[int, DeviceInfo] = field(default_factory=dict)
    #: Akışın ilk görüldüğü an (`time.monotonic`). Yönlendirme gecikmesini ölçmek için
    #: ayrı tutuluyor — `StreamInfo`'ya konsaydı her güncelleme "değişmiş" görünür ve
    #: gereksiz sinyal yağardı.
    stream_seen: dict[int, float] = field(default_factory=dict, repr=False)
    _by_id: dict[int, NodeInfo] = field(default_factory=dict, repr=False)

    NODES = "nodes"
    STREAMS = "streams"
    DEVICES = "devices"

    def node_id(self, name: str) -> int | None:
        return self.nodes.get(name)

    def node_name(self, node_id: int) -> str | None:
        info = self._by_id.get(node_id)
        return info.name if info else None

    def sonar_nodes(self) -> dict[str, int]:
        return {name: nid for name, nid in self.nodes.items() if name.startswith("sonar_")}

    def apply(self, objects: list[dict]) -> frozenset[str]:
        """Bir `pw-dump` olayını uygular; değişen envanterlerin adlarını döndürür."""
        changed: set[str] = set()
        for obj in objects:
            if not isinstance(obj, dict) or "id" not in obj:
                continue
            # Silme olayı `{"id": N, "info": null}` biçiminde gelir ve **`type` alanı
            # taşımaz**. Eskiden `type` süzgeci bu olayları eleyip `_remove()`
            # çağrılmasını tümden engelliyordu: kapanan uygulamalar akış listesinde,
            # çıkarılan cihazlar cihaz listesinde kalıyor, `nodes` haritası ölü
            # id'lerle büyüyordu. Ölçüldü (2026-09-01, `pw-dump -m`).
            if obj.get("info") is None:
                changed |= self._remove(obj["id"])
                continue
            if obj.get("type") != "PipeWire:Interface:Node":
                continue
            changed |= self._apply_node(obj)
        return frozenset(changed)

    def reset(self) -> None:
        """Tam yeniden senkron öncesi envanteri boşaltır."""
        self.nodes.clear()
        self.streams.clear()
        self.stream_seen.clear()
        self.devices.clear()
        self._by_id.clear()

    # ------------------------------------------------------------------ iç kısım

    def _apply_node(self, obj: dict) -> set[str]:
        node_id = obj["id"]
        info = obj.get("info")
        if info is None:
            return self._remove(node_id)

        props = info.get("props") or {}
        name = props.get("node.name")
        if not name:
            # Adı olmayan node'u haritalayamayız; ama önceki hâli varsa düşürmeyelim.
            return set()

        media_class = props.get("media.class", "")
        changed: set[str] = set()

        previous = self._by_id.get(node_id)
        if previous is None or previous.name != name:
            if previous is not None and self.nodes.get(previous.name) == node_id:
                del self.nodes[previous.name]
            self.nodes[name] = node_id
            changed.add(self.NODES)
        self._by_id[node_id] = NodeInfo(
            node_id, name, media_class, props.get("node.description", "")
        )

        if media_class in _STREAM_CLASSES:
            stream = StreamInfo(
                id=node_id,
                serial=int(props.get("object.serial", 0) or 0),
                node_name=name,
                app_binary=props.get("application.process.binary", ""),
                app_name=props.get("application.name", ""),
                media_name=props.get("media.name", ""),
                target_node=str(props.get("target.object", "") or ""),
                pid=int(props.get("application.process.id", 0) or 0),
                is_capture=media_class == "Stream/Input/Audio",
                captures_sink=_truthy(props.get("stream.capture.sink")),
            )
            previous_stream = self.streams.get(node_id)
            if previous_stream is None or previous_stream.serial != stream.serial:
                # Geri dönüştürülmüş bir id yeni bir akıştır: zaman damgası sıfırlanmalı,
                # yoksa yönlendirme gecikmesi eski akıştan sayılır (ölçümde 3.2 s görüldü).
                self.stream_seen[node_id] = time.monotonic()
            if previous_stream != stream:
                self.streams[node_id] = stream
                changed.add(self.STREAMS)
        elif media_class in _SINK_CLASSES or media_class in _SOURCE_CLASSES:
            device = DeviceInfo(
                id=node_id,
                name=name,
                description=props.get("node.description", ""),
                is_source=media_class in _SOURCE_CLASSES,
                priority=int(props.get("priority.session", 0) or 0),
            )
            if self.devices.get(node_id) != device:
                self.devices[node_id] = device
                changed.add(self.DEVICES)
        return changed

    def _remove(self, node_id: int) -> set[str]:
        changed: set[str] = set()
        info = self._by_id.pop(node_id, None)
        if info is not None and self.nodes.get(info.name) == node_id:
            del self.nodes[info.name]
            changed.add(self.NODES)
        self.stream_seen.pop(node_id, None)
        if self.streams.pop(node_id, None) is not None:
            changed.add(self.STREAMS)
        if self.devices.pop(node_id, None) is not None:
            changed.add(self.DEVICES)
        return changed


class PwMonitor:
    """`pw-dump -m` alt sürecini canlı tutar ve `GraphState`'i günceller.

    Süreç ölürse (PipeWire yeniden başlatıldığında olur) envanter sıfırlanıp süreç yeniden
    başlatılır — kısmi bir envanterle devam etmek, silinmiş node id'lerine yazmaya çalışmak
    demek olurdu.
    """

    def __init__(
        self,
        state: GraphState | None = None,
        *,
        command: tuple[str, ...] = ("pw-dump", "-m"),
        retry_delay: float = 1.0,
        on_change: Callable[[frozenset[str]], None] | None = None,
    ) -> None:
        self.state = state if state is not None else GraphState()
        self.command = command
        self.retry_delay = retry_delay
        self._listeners: list[Callable[[frozenset[str]], None]] = []
        if on_change is not None:
            self._listeners.append(on_change)
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._ready = threading.Event()
        self._lock = threading.RLock()

    def listen(self, callback: Callable[[frozenset[str]], None]) -> None:
        self._listeners.append(callback)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name="sonar-pwstate", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stopping.set()
        with self._lock:
            process, self._process = self._process, None
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:  # pragma: no cover - nadir
                process.kill()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def wait_ready(self, timeout: float = 5.0) -> bool:
        """İlk tam envanter gelene kadar bekler. Graf kurulumundan sonra şart."""
        return self._ready.wait(timeout)

    def wait_for_node(self, name: str, timeout: float = 5.0, interval: float = 0.05) -> int | None:
        """Bir node adının haritada belirmesini bekler; graf yeniden kurulduktan sonra şart."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            node_id = self.state.node_id(name)
            if node_id is not None:
                return node_id
            time.sleep(interval)
        return None

    # ------------------------------------------------------------------ iç kısım

    def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                self._pump()
            except FileNotFoundError:
                log.error("pw-dump bulunamadı; PipeWire araçları kurulu mu?")
                return
            except Exception:  # pragma: no cover - beklenmeyen
                log.exception("pw-dump izleyicisi beklenmedik şekilde düştü")
            if self._stopping.wait(self.retry_delay):
                return
            log.info("pw-dump yeniden başlatılıyor")
            self.state.reset()
            self._ready.clear()
            self._emit(frozenset({GraphState.NODES, GraphState.STREAMS, GraphState.DEVICES}))

    def _pump(self) -> None:
        process = subprocess.Popen(
            list(self.command),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        with self._lock:
            self._process = process
        splitter = EventSplitter()
        assert process.stdout is not None
        for line in process.stdout:
            if self._stopping.is_set():
                break
            for objects in splitter.feed(line):
                changed = self.state.apply(objects)
                self._ready.set()
                if changed:
                    self._emit(changed)
        process.wait()

    def _emit(self, changed: frozenset[str]) -> None:
        for callback in list(self._listeners):
            try:
                callback(changed)
            except Exception:  # pragma: no cover - dinleyici hatası izleyiciyi düşürmemeli
                log.exception("pwstate dinleyicisi hata verdi")


def _truthy(value: object) -> bool:
    """`pw-dump` bu bayrağı bazen `true`, bazen `"true"` olarak veriyor."""
    if isinstance(value, str):
        return value.strip().casefold() in ("1", "true", "yes")
    return bool(value)
