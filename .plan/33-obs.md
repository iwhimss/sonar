# Faz 33 — OBS görünürlüğü ve yayın kurulumu

> Test turu 4'ün ana maddesi. Kullanıcı: *"Obs hala açıkken sonar üzerinde uygulama
> listesinde gözükmüyor"*, *"steelseries gg deki stream mix ayarının aynısını istiyorum
> ama bu kısımda. Biraz yardımına ihtiyacım var."*

## Ölçülen kök nedenler

**1. OBS aslında doğru kurulu.** `pw-dump` node #356:
`node.name=OBS`, `media.name=Masaüstü Ses`, `stream.capture.sink=True`,
`target.object=sonar_stream`; `pw-link` `sonar_stream:monitor_FL/FR → OBS:input_FL/FR`.
Yani Masaüstü Sesi yayın miksinin sink'ini dinliyor — Windows'taki düzenin birebir aynısı.

**2. Mikrofon yayın miksine hiç gitmiyor.** `sonar_mic_to_stream` → `mute = True`.
`MicChain.send_to_stream_bus` varsayılanı `False` (`core/model.py:380`) ve **arayüzü yok**:
D-Bus'ta `SetMicStreamSend` duruyor (`daemon/dbus_iface.py:315`), GUI'de ve CLI'de yok.
Üçüncü turdaki "mikrofon yayın fader'ı hiçbir şey yapmıyor" bunun belirtisiydi.

**3. Doküman olmayan cihazı tarif ediyor.** `docs/OBS.md` altı yerde
"Sonar Stream Mic — Virtual Input" diyor; o, varsayılan yapılandırmadaki `stream_mic`
zinciri (`core/model.py:679`). Kullanıcı onu silmiş.

**4. OBS neden arayüzde yok.** `gui/bridge.py:143` bus dinleyicilerini bus kimliğine
eşliyor, `streamsFor("stream")` OBS'i döndürüyor — ama `MasterStrip.qml` hiçbir uygulama
listesi çizmiyor. Satır üretiliyor, çizen yok.

## Kararlar

| Konu | Karar |
|---|---|
| Resmî OBS yolu | Masaüstü Sesi = **Sonar Stream Mix** (sink'in monitörü) |
| Mikrofon | Yayın miksine katılsın, **varsayılan açık** |
| `sonar_stream_out` | Kalsın, adı "(alternatif giriş)" olsun |

## Görevler

### 33.1 OBS arayüzde görünsün
- [x] `MasterStrip.qml`'e uygulama listesi (`ChannelStrip.qml:296–320` deseninin aynısı)
- [x] Bu kutucuklar sürüklenemez; bir bus'ı dinliyorlar, kanala taşınamazlar
- [x] Hangi node'u yakaladığı kutucukta yazsın (Stream Mix / Personal Mix)

### 33.2 Yayın kurulumu tanı paneli
- [x] `api.stream_setup()` — yayın bus'ını dinleyen akışlar, mikrofon gönderi durumu, sorunlar
- [x] Master şeridinde panel: "OBS'te şunu seç" + kopyala, "şu an ne oluyor", uyarılar
- [x] Çift yakalama uyarısı (`sonar_stream` monitörü **ve** `sonar_stream_out` aynı anda)
- [x] Mikrofon → yayın anahtarı (`SetMicStreamSend`); köprü ve `sonar-cli` karşılığı
- [x] `sonar-cli doctor` çıktısına girsin

### 33.3 Mikrofon şeridi doğru şeyi söylesin
- [x] 📡 fader'ın etiketi "Mikrofon seviyesi", 🎧 fader'ınki "Kendini duy"
- [x] Yayın gönderisi kapalıyken şeritte "yayına gitmiyor" satırı

### 33.4 Cihaz adları
- [x] `sonar_stream` açıklaması → **"Sonar Stream Mix"**
- [x] `sonar_stream_out` açıklaması → **"Sonar Stream Mix (alternatif giriş)"**
- [x] Node adları ve `media.class` değişmiyor — OBS'teki seçim bozulmasın

### 33.5 `docs/OBS.md` sıfırdan
- [x] Başta tek kurulum, üç adım
- [x] Sabit cihaz adları temizlensin
- [x] Mikrofonun yayın miksinde olduğu ve nasıl ayrılacağı
- [x] Kanal başına track bölümü sona

## Ölçüm
- Mikser master şeridinde "OBS — Stream Mix yakalıyor" satırı
- Gönderi açıkken `sonar_mic_to_stream` mute `False`, OBS kaydında mikrofon duyuluyor
- İkinci kaynak eklendiğinde tanı paneli uyarıyor
