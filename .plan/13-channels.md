# Faz 13 — Kanal yönetimi: silme ve yön seçimi

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 12
**Çıktı:** `src/sonar/core/model.py`, `src/sonar/daemon/api.py`,
`src/sonar/daemon/dbus_iface.py`, `src/sonar/gui/qml/Mixer.qml`,
`src/sonar/gui/qml/ChannelStrip.qml`, `src/sonar/cli/__main__.py`

---

## Amaç

Kullanıcının iki isteği:

> İstediğim kanalları silemiyorum. Silebilmeliyim. Örnek olarak aux kanalını
> kullanamayacaksam silebilmeliyim.

> Yeni kanal eklerken giriş kanalı mı çıkış kanalı mı diye sormalı. Ona göre sanal
> ses cihazını oluşturmalı.

Kullanıcı kararı: **hepsi silinebilsin**, yerleşik koruması tamamen kalksın.

---

## Yaklaşım

### Silme

`Channel.builtin` alanı korumaya değil, yalnızca "ilk kurulumda geldi" bilgisine
işaret eder. `api.remove_channel()` artık `builtin` kontrolü yapmaz. Kalan kısıtlar:

| Kısıt | Davranış |
|---|---|
| Son çıkış kanalı | Silinemez — `ApiError("last_channel", …)` |
| Silinen kanal `settings.default_channel` ise | Varsayılan, kalan ilk çıkış kanalına geçer |
| Kanala bağlı `RoutingRule`'lar | Silinir |
| Kanalın profil dosyaları (`profiles/<id>/`) | Silinir |
| Kanalın favorileri | `config.favorites`'tan düşer |
| `chatmix.left_channel` / `right_channel` | Silinen kanal listeden çıkarılır; taraf boşalırsa ChatMix kapanır |
| O kanalda çalan akışlar | `default_channel`'a taşınır |

### Giriş kanalları

`MicChain` genelleşir: kullanıcı ekleyip silebilir, `name` ve `color` taşır.
`mic` / `stream_mic` artık ayrıcalıklı değil — sadece ilk kurulumda oluşturulan iki
giriş kanalı. `confgen._primary_mic()` "kendi DSP'si olan ilk giriş kanalı" mantığını
korur; hiç giriş kanalı kalmazsa mikrofon modülleri hiç üretilmez.

`Channel.direction` (Faz 12) çıkış kanallarını, `MicChain` giriş kanallarını temsil
eder. Arayüz ikisini tek bir "kanal" kavramı altında gösterir; ayrım yalnızca hangi
sanal cihazın üretildiğidir:

| Yön | Üretilen |
|---|---|
| Çıkış | `sonar_<id>` (Virtual Output) + DSP + iki bus gönderisi |
| Giriş | fiziksel kaynak → DSP → `sonar_<id>` (Virtual Input) |

### API

| Metot | Değişiklik |
|---|---|
| `AddChannel(name, direction, color)` | `direction` parametresi eklendi (`"output"` / `"input"`) |
| `RemoveChannel(id)` | Giriş kanallarını da kabul eder |
| `SetChannelDevice(id, device)` | Giriş kanalının kaynak cihazını da ayarlar |

### Arayüz

- Kanal ekleme penceresi: ad + **Çıkış / Giriş** seçimi + renk seçici.
  Giriş seçilirse kaynak cihaz seçici de görünür.
- Şerit başlığındaki dişli menüsünde "Kanalı sil" — her kanalda aktif.
  Onay penceresi kanalın ne kaybedeceğini yazar (kurallar, profiller).
- `sonar-cli channel add <ad> --direction input|output` ve
  `sonar-cli channel remove <id>`.

---

## Görevler

- [ ] `remove_channel()` yerleşik koruması kalkar, yeni kısıtlar eklenir
- [ ] Kanal silinince kurallar / profiller / favoriler / ChatMix temizlenir
- [ ] `MicChain`'e `color`, kullanıcı tarafından eklenebilir/silinebilir olması
- [ ] `add_channel(name, direction, color)` + D-Bus imzası
- [ ] `RemoveChannel` giriş kanallarını kabul eder
- [ ] Kanal ekleme penceresi: yön seçimi + renk + (giriş için) cihaz
- [ ] Şerit menüsünde "Kanalı sil"
- [ ] `sonar-cli channel add|remove`
- [ ] Testler: son kanal koruması, varsayılan kanal devri, ChatMix temizliği

---

## Doğrulama

- Aux silinir → graf yeniden kurulur, kalan kanallar çalışmaya devam eder
- Media (varsayılan kanal) silinir → varsayılan başka kanala geçer, yeni açılan
  uygulama oraya düşer
- "Podcast" adında bir giriş kanalı eklenir → `pactl list short sources` içinde
  `Sonar Podcast — Virtual Input` görünür, Discord onu seçebilir
- Tüm çıkış kanalları silinmeye çalışılır → sonuncusunda hata döner

---

## Yol boyunca yakalananlar

_(faz sırasında doldurulacak)_
