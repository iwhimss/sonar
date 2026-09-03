# Faz 20 — Çoklu çıkış bus'ı

**Durum:** ⚪ Bekliyor
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

- [ ] `BusId` enum'u kalkar; `MasterBus.id` serbest bir dize, yeni alan
      `kind: "output" | "stream"`. `personal` yalnızca varsayılan çıkış bus'ının id'si.
- [ ] `Channel.personal` / `Channel.stream` sabit alanları → `Channel.sends: dict[str, Send]`
      (bus id başına bir gönderi).
- [ ] `Channel.output_bus: str = "personal"` — kanalın hangi çıkışa gittiği.
- [ ] `core/config.py` göçü: eski `[channels.personal]` / `[channels.stream]` blokları
      `sends` sözlüğüne taşınır, `output_bus = "personal"` yazılır, buslara `kind` eklenir.
- [ ] `SonarConfig.output_buses()` / `stream_bus()` yardımcıları.

## Graf

- [ ] `confgen` her kanal için **her** bus'a gönderi loopback'i kurar (bugün iki tane).
- [ ] Kanalın çıkışını değiştirmek yalnızca hangi gönderinin açık olduğunu değiştirir:
      `live_volumes` seçili çıkış bus'ının gönderisine `(volume, muted)`, diğer çıkış
      bus'larının gönderisine `muted=True` yazar. **Yeniden inşa yok.**
- [ ] Yayın gönderisi her zaman ayrıca açıktır.
- [ ] Çıkış bus'ı **eklemek/silmek** yapısaldır (yeniden inşa) — nadir ve kullanıcı tetikli.
- [ ] `chatmix_gains` yalnızca kanalın bağlı olduğu çıkış bus'ında uygulanır.

## API

- [ ] `AddOutputBus(name, device)` → yeni bus id üretir, tüm kanallara gönderi ekler
- [ ] `RemoveOutputBus(id)` → en az bir çıkış bus'ı kalmalı; o bus'a bağlı kanallar
      varsayılana düşer
- [ ] `SetChannelOutput(channel, bus)` — canlı
- [ ] `SetBusDevice(bus, device)` — Faz 18'de canlı hâle geldi
- [ ] `RenameBus(bus, name)`

## Arayüz

- [ ] `MasterStrip` çıkış bus'larını dikey listeler: ad + cihaz açılırı + fader + mute,
      altta "＋ Çıkış ekle".
- [ ] Kanal şeridinde küçük bir çıkış açılırı (hangi bus'a gidiyor).
- [ ] FX sayfasından bus profilleri düzenlenebilir (mevcut hedef listesi genişler).
- [ ] **"Yayın Miksi" satırı düzeltilir.** Bugün fiziksel cihaz listeliyor ama
      `bus.device` stream bus'ta hiç kullanılmıyor — sessiz bir no-op. Yerine salt
      okunur bilgi satırı: `Sonar Stream Mix — Virtual Input`, yanında kopyalama düğmesi
      ve "kanal başına ayrı track" anahtarı (mevcut `stream_source`).
- [ ] `sonar-cli output add|remove|list`, `sonar-cli channel output <kanal> <bus>`

---

## Kabul ölçütü

- [ ] İki çıkış bus'ı kurulur; Game hoparlöre, Media kulaklığa yönlendirilir.
      Her cihazın monitöründe yalnızca kendi kanalının tonu var, diğerinin sızıntısı
      **< −100 dB**.
- [ ] Kanalın çıkışını değiştirmek conf metnini değiştirmiyor (testle korunur)
- [ ] Şema 2 → 3 göçü kullanıcının gerçek `config.toml`'unda çalışıyor
- [ ] ChatMix yalnızca ilgili çıkış bus'ında etkili
