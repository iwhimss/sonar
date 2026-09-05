"""Gömülü kanal, bus, mikrofon ve preset adlarının **gösterilen** hâli.

Adların iki işi birden var: arayüz etiketi ve PipeWire cihaz açıklaması
(`engine/confgen.py` `node.description`'ı `channel.name`'den üretiyor). Yapılandırmadaki
ad İngilizce ve sabit kalıyor; dile göre değişseydi OBS'te seçili "Sonar Stream Mix"
aygıtı her dil değişiminde kaybolur ve dokümandaki adlar dile bağımlı hâle gelirdi.

Bu modül çeviriyi yalnızca **ekrana yazılan** ada uyguluyor. `gui/bridge.py` ve
`cli/__main__.py` aynı yerden okuyor ki iki arayüz aynı adı göstersin.
"""

from __future__ import annotations

from sonar.core import i18n

__all__ = ["BUILTIN_NAMES", "PRESET_NAMES", "display_name", "preset_label"]


#: Gömülü kimlik → (katalog anahtarı, yapılandırmadaki varsayılan ad).
BUILTIN_NAMES: dict[tuple[str, str], tuple[str, str]] = {
    ("channel", "game"): ("channel.game", "Game"),
    ("channel", "chat"): ("channel.chat", "Chat"),
    ("channel", "media"): ("channel.media", "Media"),
    ("channel", "aux"): ("channel.aux", "Aux"),
    ("bus", "personal"): ("bus.personal", "Personal Mix"),
    ("bus", "stream"): ("bus.stream", "Stream Mix"),
    ("mic", "mic"): ("mic.chain.mic", "Mic"),
    ("mic", "stream_mic"): ("mic.chain.stream_mic", "Stream Mic"),
}

#: Gömülü preset adı → katalog anahtarı. Diskteki dosya adı (`profiles/game/Flat.json`)
#: değişmiyor; yalnızca listede görünen metin çevriliyor.
PRESET_NAMES: dict[str, str] = {
    "Flat": "preset.flat",
    "FPS Footsteps": "preset.fps_footsteps",
    "Bass Boost": "preset.bass_boost",
    "Vocal Clarity": "preset.vocal_clarity",
    "Night Mode": "preset.night_mode",
    "Movie": "preset.movie",
    "Music": "preset.music",
    "Broadcast": "preset.broadcast",
    "Podcast": "preset.podcast",
    "Aggressive Cleanup": "preset.aggressive_cleanup",
    "Default": "preset.default",
}


def display_name(kind: str, ident: str, name: str) -> str:
    """Gömülü bir kanalın/bus'ın/mikrofonun arayüzde görünecek adı.

    Kullanıcı yeniden adlandırmışsa **onun** adı kazanır: çeviri yalnızca ada hiç
    dokunulmamışsa devreye giriyor. Bu sayede "Oyun" yazan kullanıcı dilini İngilizceye
    çevirince "Game" görüyor, ama kanalını "Valorant" diye adlandırmış biri her iki dilde
    de "Valorant" görüyor.
    """
    entry = BUILTIN_NAMES.get((kind, ident))
    if entry is None:
        return name
    key, default = entry
    return i18n.t(key) if name == default else name


def preset_label(name: str) -> str:
    """Gömülü preset adının gösterilecek hâli. Kullanıcının kendi profilleri değişmez."""
    key = PRESET_NAMES.get(name)
    return i18n.t(key) if key else name
