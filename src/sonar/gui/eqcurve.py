"""EQ eğrisinin çizimi — `QQuickPaintedItem` alt sınıfı.

QML `Canvas`'ı yerine boyalı öğe seçildi: eğri her sürükleme karesinde yeniden hesaplanıyor
(512 nokta, numpy) ve `Canvas` her karede JavaScript'e dönmek zorunda kalırdı.

Öğe **yalnızca çizer ve koordinat çevirir**; band değerlerini değiştirmez. Sürükleme
mantığı QML tarafında, çünkü değişikliğin köprüye gitmesi gereken yer orası.
"""

from __future__ import annotations

import json

import numpy as np
from PySide6.QtCore import Property, QPointF, Qt, Signal, Slot
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtQml import QmlElement
from PySide6.QtQuick import QQuickPaintedItem

from sonar.core.dsp.response import DISPLAY_MAX_HZ, DISPLAY_MIN_HZ, eq_response, log_frequencies
from sonar.core.model import EqBand, EqBandType, EqState

QML_IMPORT_NAME = "Sonar.Dsp"
QML_IMPORT_MAJOR_VERSION = 1

__all__ = ["EqCurve", "eq_from_json"]

#: Izgara çizgilerinin çizildiği frekanslar (etiketli olanlar kalın).
GRID_FREQS = (20, 50, 100, 200, 500, 1000, 2000, 5000, 10_000, 20_000)

#: SteelSeries'teki gibi üst bant etiketleri.
BAND_LABELS = (
    (20, 60, "SUB BASS"),
    (60, 250, "BASS"),
    (250, 500, "LOW MIDS"),
    (500, 2000, "MID RANGE"),
    (2000, 6000, "UPPER MIDS"),
    (6000, 20_000, "HIGHS"),
)

#: Band düğümlerinin renkleri — hangi noktanın hangi band olduğu ayırt edilebilsin.
NODE_COLORS = (
    "#F0479A",
    "#F2A73B",
    "#E5C037",
    "#22C58B",
    "#3BD6C6",
    "#3B9EFF",
    "#7C6CF0",
    "#B96CF0",
    "#F06C9B",
    "#8B95A5",
)


def eq_from_json(payload: str) -> EqState:
    """Köprüden gelen JSON'u model nesnesine çevirir. Bozuk veri düz bir EQ verir."""
    try:
        data = json.loads(payload) if payload else {}
    except json.JSONDecodeError:
        return EqState()
    bands = []
    for raw in data.get("bands", []):
        try:
            bands.append(
                EqBand(
                    freq=float(raw["freq"]),
                    gain_db=float(raw.get("gain_db", 0.0)),
                    q=float(raw.get("q", 1.41)),
                    band_type=EqBandType(raw.get("band_type", "peak")),
                    slope=int(raw.get("slope", 0)),
                    enabled=bool(raw.get("enabled", True)),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return EqState(
        enabled=bool(data.get("enabled", False)),
        band_count=int(data.get("band_count", len(bands))),
        preamp_db=float(data.get("preamp_db", 0.0)),
        bands=bands,
    )


@QmlElement
class EqCurve(QQuickPaintedItem):
    """Izgara, bileşik eğri ve sürüklenebilir band düğümleri."""

    eqChanged = Signal()
    rangeDbChanged = Signal()
    selectedBandChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._eq_json = ""
        self._eq = EqState()
        self._range_db = 15.0
        self._selected = -1
        self._accent = QColor("#7C6CF0")
        self._freqs = log_frequencies(512)
        self.setAntialiasing(True)

    # ------------------------------------------------------------------ özellikler

    def _get_eq(self) -> str:
        return self._eq_json

    def _set_eq(self, value: str) -> None:
        if value == self._eq_json:
            return
        self._eq_json = value
        self._eq = eq_from_json(value)
        self.eqChanged.emit()
        self.update()

    eq = Property(str, _get_eq, _set_eq, notify=eqChanged)

    def _get_range(self) -> float:
        return self._range_db

    def _set_range(self, value: float) -> None:
        value = max(6.0, min(36.0, float(value)))
        if value != self._range_db:
            self._range_db = value
            self.rangeDbChanged.emit()
            self.update()

    rangeDb = Property(float, _get_range, _set_range, notify=rangeDbChanged)

    def _get_selected(self) -> int:
        return self._selected

    def _set_selected(self, value: int) -> None:
        if value != self._selected:
            self._selected = int(value)
            self.selectedBandChanged.emit()
            self.update()

    selectedBand = Property(int, _get_selected, _set_selected, notify=selectedBandChanged)

    def _get_accent(self) -> QColor:
        return self._accent

    def _set_accent(self, value: QColor) -> None:
        self._accent = QColor(value)
        self.update()

    accent = Property(QColor, _get_accent, _set_accent)

    # ------------------------------------------------------------------ koordinat çevirimi

    @Slot(float, result=float)
    def xForFreq(self, freq: float) -> float:
        freq = max(DISPLAY_MIN_HZ, min(DISPLAY_MAX_HZ, freq))
        span = np.log10(DISPLAY_MAX_HZ / DISPLAY_MIN_HZ)
        return float(np.log10(freq / DISPLAY_MIN_HZ) / span * self.width())

    @Slot(float, result=float)
    def freqForX(self, x: float) -> float:
        if self.width() <= 0:
            return DISPLAY_MIN_HZ
        span = np.log10(DISPLAY_MAX_HZ / DISPLAY_MIN_HZ)
        ratio = max(0.0, min(1.0, x / self.width()))
        return float(DISPLAY_MIN_HZ * 10 ** (ratio * span))

    @Slot(float, result=float)
    def yForGain(self, db: float) -> float:
        db = max(-self._range_db, min(self._range_db, db))
        return float((1 - (db + self._range_db) / (2 * self._range_db)) * self.height())

    @Slot(float, result=float)
    def gainForY(self, y: float) -> float:
        if self.height() <= 0:
            return 0.0
        ratio = max(0.0, min(1.0, 1 - y / self.height()))
        return float(ratio * 2 * self._range_db - self._range_db)

    @Slot(float, float, result=int)
    def bandAt(self, x: float, y: float, radius: float = 18.0) -> int:
        """Verilen noktaya en yakın band düğümü; yoksa -1."""
        best, best_distance = -1, radius
        for index, band in enumerate(self._eq.active_bands()):
            dx = x - self.xForFreq(band.freq)
            dy = y - self.yForGain(band.gain_db)
            distance = float(np.hypot(dx, dy))
            if distance < best_distance:
                best, best_distance = index, distance
        return best

    # ------------------------------------------------------------------ çizim

    def paint(self, painter: QPainter) -> None:
        width, height = self.width(), self.height()
        if width <= 0 or height <= 0:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._paint_grid(painter, width, height)
        self._paint_curve(painter, width, height)
        self._paint_nodes(painter)

    def _paint_grid(self, painter: QPainter, width: float, height: float) -> None:
        painter.fillRect(0, 0, int(width), int(height), QColor("#0B0E12"))

        # yatay dB çizgileri
        step = 3 if self._range_db <= 15 else 6
        pen = QPen(QColor("#1C222B"), 1)
        painter.setPen(pen)
        db = -int(self._range_db)
        while db <= int(self._range_db):
            y = self.yForGain(db)
            painter.setPen(QPen(QColor("#2A323D" if db == 0 else "#181D24"), 1))
            painter.drawLine(QPointF(0, y), QPointF(width, y))
            if db != 0:
                painter.setPen(QColor("#5A6472"))
                painter.drawText(QPointF(4, y - 2), f"{db:+d}")
            db += step

        # dikey frekans çizgileri
        for freq in GRID_FREQS:
            x = self.xForFreq(freq)
            painter.setPen(QPen(QColor("#181D24"), 1))
            painter.drawLine(QPointF(x, 0), QPointF(x, height))
            painter.setPen(QColor("#5A6472"))
            label = f"{freq // 1000}k" if freq >= 1000 else str(freq)
            painter.drawText(QPointF(x + 3, height - 4), label)

        # üst bant etiketleri
        painter.setPen(QColor("#3A424E"))
        for low, high, text in BAND_LABELS:
            x0, x1 = self.xForFreq(low), self.xForFreq(high)
            if x1 - x0 < 46:
                continue
            painter.drawText(QPointF((x0 + x1) / 2 - len(text) * 2.6, 12), text)

    def _paint_curve(self, painter: QPainter, width: float, height: float) -> None:
        _, db = eq_response(self._eq, self._freqs)
        xs = [self.xForFreq(f) for f in self._freqs]
        ys = [self.yForGain(v) for v in db]

        path = QPainterPath()
        path.moveTo(xs[0], ys[0])
        for x, y in zip(xs[1:], ys[1:], strict=True):
            path.lineTo(x, y)

        # eğri altı hafif dolgu — 0 dB çizgisine kadar
        fill = QPainterPath(path)
        fill.lineTo(xs[-1], self.yForGain(0))
        fill.lineTo(xs[0], self.yForGain(0))
        fill.closeSubpath()
        gradient = QLinearGradient(0, 0, 0, height)
        accent = QColor(self._accent)
        top = QColor(accent)
        top.setAlphaF(0.22)
        bottom = QColor(accent)
        bottom.setAlphaF(0.02)
        gradient.setColorAt(0.0, top)
        gradient.setColorAt(1.0, bottom)
        painter.fillPath(fill, gradient)

        painter.setPen(QPen(accent if self._eq.enabled else QColor("#5A6472"), 2))
        painter.drawPath(path)
        del width

    def _paint_nodes(self, painter: QPainter) -> None:
        for index, band in enumerate(self._eq.active_bands()):
            x = self.xForFreq(band.freq)
            y = self.yForGain(band.gain_db)
            color = QColor(NODE_COLORS[index % len(NODE_COLORS)])
            if not band.enabled or band.band_type is EqBandType.OFF:
                color = QColor("#5A6472")
            selected = index == self._selected
            size = 6 if not selected else 8
            # Köşesiz tasarım dili: düğümler de kare.
            painter.setPen(QPen(QColor("#0B0E12"), 1))
            painter.setBrush(color)
            painter.drawRect(int(x - size), int(y - size), size * 2, size * 2)
            if selected:
                painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
