# Faz 20 — Çoklu çıkış bus'ı

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 18 (canlı cihaz değişimi), Faz 19 (canlı arayüz)
**Çıktı:** `src/sonar/core/model.py`, `core/config.py`, `engine/confgen.py`,
`engine/supervisor.py`, `daemon/api.py`, `daemon/dbus_iface.py`, `gui/`, `cli/`

---

## Amaç

Kullanıcının isteği: *"Game kanalı laptopun hoparlörünü kullanırken media kanalı
kulaklığın çıkış cihazını kullanabilmeli."*

Seçilen mimari (kullanıcı onayı): **her fiziksel cihaz kendi master bus'ını alır**
(fader + EQ + profil), kanal hangi bus'a gideceğini seçer. Kanalın doğrudan cihaza
bağlanması — master işlemeyi atladığı için — tercih edilmedi.

```
Game  ─┐
Chat  ─┼─> Kişisel Miks (master EQ+fader) ─> Kulaklık
Media ─┘
Aux   ───> Çıkış 2 (kendi EQ+fader'ı)     ─> Hoparlör
   hepsi ─> Yayın Miksi                    ─> OBS
```

---

## Model değişikliği (şema 2 → 3)

- [x] `BusId` enum'u kalkar; `MasterBus.id` serbest bir dize, yeni alan
      `kind: "output" | "stream"`. `personal` yalnızca varsayılan çıkış bus'ının id'si.
- [x] `Channel.personal` / `Channel.stream` sabit alanları → `Channel.sends: dict[str, Send]`
      (bus id başına bir gönderi).
- [x] `Channel.output_bus: str = "personal"` — kanalın hangi çıkışa gittiği.
- [x] `core/config.py` göçü: eski `[channels.personal]` / `[channels.stream]` blokları
      `sends` sözlüğüne taşınır, `output_bus = "personal"` yazılır, buslara `kind` eklenir.
- [x] `SonarConfig.output_buses()` / `stream_bus()` yardımcıları.

## Graf

- [x] `confgen` her kanal için **her** bus'a gönderi loopback'i kurar (bugün iki tane).
- [x] Kanalın çıkışını değiştirmek yalnızca hangi gönderinin açık olduğunu değiştirir:
      `live_volumes` seçili çıkış bus'ının gönderisine `(volume, muted)`, diğer çıkış
      bus'larının gönderisine `muted=True` yazar. **Yeniden inşa yok.**
- [x] Yayın gönderisi her zaman ayrıca açıktır.
- [x] Çıkış bus'ı **eklemek/silmek** yapısaldır (yeniden inşa) — nadir ve kullanıcı tetikli.
- [x] `chatmix_gains` yalnızca kanalın bağlı olduğu çıkış bus'ında uygulanır.

## API

- [x] `AddOutputBus(name, device)` → yeni bus id üretir, tüm kanallara gönderi ekler
- [x] `RemoveOutputBus(id)` → en az bir çıkış bus'ı kalmalı; o bus'a bağlı kanallar
      varsayılana düşer
- [x] `SetChannelOutput(channel, bus)` — canlı
- [x] `SetBusDevice(bus, device)` — Faz 18'de canlı hâle geldi
- [x] `RenameBus(bus, name)`

## Arayüz

- [x] `MasterStrip` çıkış bus'larını dikey listeler: ad + cihaz açılırı + fader + mute,
      altta "＋ Çıkış ekle".
- [x] Kanal şeridinde küçük bir çıkış açılırı (hangi bus'a gidiyor).
- [x] FX sayfasından bus profilleri düzenlenebilir (mevcut hedef listesi genişler).
- [x] **"Yayın Miksi" satırı düzeltilir.** Bugün fiziksel cihaz listeliyor ama
      `bus.device` stream bus'ta hiç kullanılmıyor — sessiz bir no-op. Yerine salt
      okunur bilgi satırı: `Sonar Stream Mix — Virtual Input`, yanında kopyalama düğmesi
      ve "kanal başına ayrı track" anahtarı (mevcut `stream_source`).
- [x] `sonar-cli output add|remove|list`, `sonar-cli channel output <kanal> <bus>`

---

## Kabul ölçütü

- [x] İki çıkış bus'ı kurulur; Game hoparlöre, Media kulaklığa yönlendirilir.
      Her cihazın monitöründe yalnızca kendi kanalının tonu var, diğerinin sızıntısı
      **< −100 dB**.
- [x] Kanalın çıkışını değiştirmek conf metnini değiştirmiyor (testle korunur)
- [x] Şema 2 → 3 göçü kullanıcının gerçek `config.toml`'unda çalışıyor
- [x] ChatMix yalnızca ilgili çıkış bus'ında etkili


---

## Uygulanan hâli

`BusId` enum'u kalktı; yerine `BusKind` (`output` / `stream`) ve serbest string bus
kimlikleri geldi. `DEFAULT_OUTPUT_BUS` ve `STREAM_BUS` yalnızca **varsayılan** kimlikler;
kod hiçbir yerde "personal her zaman vardır" varsaymıyor.

`Channel.personal` / `Channel.stream` sabit alanları `sends: dict[str, BusSend]` oldu.
`Channel.output` seçili çıkışın gönderisini, `Channel.stream` yayın gönderisini veriyor.
`SonarConfig.ensure_sends()` yükleme ve bus ekleme sonrasında eksik gönderileri dolduruyor
— tembel `send()` yalnızca bellekte çalışıyordu, `config.toml`'da görünmüyordu.

Arayüzdeki kulaklık fader'ı artık `"output"` adını kullanıyor: "kanalın seçili çıkışı"
demek, hangi bus olduğunu daemon çözüyor (`api._bus`). Böylece kanal başka bir cihaza
taşınınca fader kendiliğinden doğru bus'a yazıyor.

## Ölçümler (canlı graf, 2026-09-03)

| Ölçüm | Sonuç |
|---|---|
| Şema 2 → 3 göçü | kullanıcının gerçek `config.toml`'unda çalıştı: `[channels.sends.personal]`, `output_bus`, bus'larda `kind`/`order` |
| Varsayılan yapılandırmada conf | **byte-eş** — çoklu bus refaktörü tek kanallı kurulumda grafı hiç değiştirmedi |
| İzolasyon | Game hoparlörde, Media kulaklıkta: her biri kendi bus'ında **-37.0 dBFS**, diğerinde **-240 dBFS** (dijital sessizlik) |
| Kanal çıkışını değiştirmek | `sonar_game` node id'si 304 → 304 → 304 (yeniden inşa yok) |
| Fiziksel bağlantı | `sonar_personal_out` → Arctis, `sonar_hoparlor_out` → Realtek |
| `sonar-cli doctor` | iki bus'la 9/9 gönderi, sorun yok |

## Yol boyunca yakalananlar

**`slugify` Türkçe harfleri düşürüyordu.** "Hoparlör" → `hoparl_r`. Kimlik hem node adına
(`sonar_<id>`) hem kullanıcıya gösterilen çıktılara giriyor. Artık çeviriyor:
ö→o, ü→u, ı→i, ş→s, ç→c, ğ→g (ve yaygın Latin harfler). Bu, kanal ekleme için de
Faz 13'ten beri geçerli olan bir hataydı.

**`sonar-cli volume/mute` artık `choices` listesi tutmuyor:** çıkış bus'ları kullanıcı
tarafından ekleniyor. Bilinmeyen ad daemon'da `unknown_bus` hatasına düşüyor ve var olan
bus'ları sayıyor.
