# Faz 13 — Kanal yönetimi: silme ve yön seçimi

**Durum:** 🟢 Tamamlandı
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

- [x] `remove_channel()` yerleşik koruması kalkar, yeni kısıtlar eklenir
- [x] Kanal silinince kurallar / profiller / ChatMix / yönlendirme kaydı temizlenir
      (favoriler Faz 16'da eklenecek, orada bağlanacak)
- [x] `MicChain`'e `color`, kullanıcı tarafından eklenebilir/silinebilir olması
- [x] `add_channel(name, direction, color)` + D-Bus imzası
- [x] `RemoveChannel` giriş kanallarını kabul eder
- [x] Kanal ekleme penceresi: yön seçimi (renk ve cihaz seçici Faz 15'e ertelendi —
      ikisi de yeni popup altyapısını bekliyor)
- [x] Şerit menüsünde "Kanalı sil"
- [x] `sonar-cli channel add|remove`
- [x] Testler: son kanal koruması, varsayılan kanal devri, ChatMix temizliği

---

## Doğrulama (2026-09-01, gerçek grafta)

- `sonar-cli channel add Podcast --direction input` → `sonar_podcast` sanal giriş
  cihazı olarak listede belirdi ✅
- `sonar-cli channel remove podcast` ve `remove aux` → ikisi de silindi, graf 4
  sink'e düştü ✅
- Aux geri eklendi, 440 Hz test sinyali yine **-13.98 dBFS** — kanal ekleyip silmek
  sinyal yolunu bozmuyor ✅
- Aux silinir → graf yeniden kurulur, kalan kanallar çalışmaya devam eder
- Media (varsayılan kanal) silinir → varsayılan başka kanala geçer, yeni açılan
  uygulama oraya düşer
- "Podcast" adında bir giriş kanalı eklenir → `pactl list short sources` içinde
  `Sonar Podcast — Virtual Input` görünür, Discord onu seçebilir
- Tüm çıkış kanalları silinmeye çalışılır → sonuncusunda hata döner

---

## Yol boyunca yakalananlar

**Giriş kanalları artık mikserde şerit olarak görünüyor.** Eskiden `channel_rows()`
`id != "mic"` diye eleyip yalnızca birincil mikrofonu gösteriyordu; kullanıcı kendi
giriş kanalını ekleyebildiğine göre bu tutmuyordu. Yeni kural: kendi DSP zinciri olan
her giriş kanalı bir şerittir, `share_chain_with_mic` olanlar (başka bir zincirin
kopyası) değildir. Yan etkisi: `Stream Mic` de artık ayrı bir şerit.

**"Kendi zincirine sahip son mikrofon" korunuyor.** `confgen._primary_mic()`,
`share_chain_with_mic` olan zincirlerin besleneceği bir kaynak arıyor ve bulamazsa
`ValueError` yükseltiyor — yani conf üretimi patlıyordu. `_remove_input_channel()`
bu durumu önceden yakalayıp anlaşılır bir hata döndürüyor.

**Aynı id iki listede olamaz.** `add_channel` çakışmayı `config.channel(id)` yerine
`config.profile_targets()` üzerinden yokluyor: profiller kanal, mikrofon ve bus'lar
için tek bir isim uzayında tutuluyor, "Podcast" adlı hem giriş hem çıkış kanalı
profilleri birbirine karıştırırdı.

**ChatMix silinen kanalı gösteriyorsa kapanıyor.** `chatmix.left_channel` virgüllü
bir liste; silinen kanal listeden düşüyor, taraflardan biri boşalırsa ChatMix
tamamen kapatılıyor. Aksi hâlde `chatmix_gains()` var olmayan bir kanala kazanç
yazmaya çalışıyordu.
