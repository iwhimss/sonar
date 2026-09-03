# Faz 28 — Master davranışı, dişli ve %300 fader

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 27

---

- [x] **Master fader her şeyi etkilesin.** Bus sink'lerinin `capture.props` bölümüne
      `monitor.channel-volumes = true` eklensin; böylece monitör portları da master
      fader'ı duyar ve OBS hangi kaynağı seçerse seçsin aynı sesi alır. Ölçümle
      doğrulanacak (bugün `False`).
- [x] `docs/OBS.md`: **yalnızca `Sonar Stream Mix — Virtual Input` eklenmeli.** "Ses
      Çıkışı Yakalama" ile aynı miksi ikinci kez almanın neden yanlış olduğu yazılsın;
      arayüzdeki Yayın Miksi bilgi satırına da kısa bir not düşülsün.
- [x] Kanal şeridindeki **dişli düğmesi kaldırılsın** (üstteki sekmeler zaten FX
      sayfasını açıyor). Master şeridine bir dişli gelsin; cihaz bölümünü (Personal Mix /
      Mikrofon / Yayın Miksi) **katlayıp açsın**. Katlanma durumu `settings`'te saklansın.
- [x] Fader'lar **%300**'e çıksın (`SonarFader` üst sınırı, yüzde metni, `Theme.volumeText`).
      Daemon zaten 0–4 kabul ediyor (`api._level`). %100 üstünde tutamak ve yüzde metni
      uyarı rengine dönsün; metre zaten kırpmayı kırmızı gösteriyor. Ses zincirine
      hiçbir şey eklenmiyor (kullanıcı kararı).
- [x] Fader'ın çift tıkla sıfırlaması 1.0'a (birim kazanç) gitmeye devam etsin.

**Ölçüm:** OBS'in iki kaynağı da master yayın fader'ını takip ediyor (ton enjeksiyonu +
kayıt); %200'de çıkış tam +6.02 dB.


---

## Ölçümler (canlı graf, 2026-09-03)

**Master fader artık her şeyi kısıyor.** `monitor.channel-volumes = true` eklenmeden önce
sink'in monitör portları fader'dan **önce** dallanıyordu:

| master yayın | OBS "Ses Çıkışı Yakalama" (monitör) | OBS "Ses Girişi Yakalama" (sanal kaynak) |
|---|---|---|
| %100 | -23.0 dBFS | -23.0 dBFS |
| %50 | **-29.1 dBFS** | **-29.1 dBFS** |

İkisi de aynı; düzeltmeden önce monitör master'ı hiç duymuyordu ve kullanıcı "master
yayın slider'ı sadece mikrofonu kısıyor" diyordu.

**%300 fader.** Yazılan lineer kazanç ölçüldü:

| fader | `channelVolumes` | dB |
|---|---|---|
| %100 | 1.0 | 0.00 |
| %200 | 2.0 | **+6.02** |
| %300 | 3.0 | **+9.54** |

Daemon üst sınırı 0–4; arayüz 3.0'da duruyor. %100 üstünde tutamak, dolu kısım ve yüzde
metni uyarı rengine dönüyor ve fader'da birim kazanç çizgisi beliriyor. Ses zincirine
koruma **eklenmedi** — kullanıcı kararı.

**Kanal dişlisi kalktı.** Üstteki sekmeler zaten FX sayfasını açıyordu; kısayol olarak
şerit başlığına tıklamak kaldı. Dişli master şeridine taşındı ve orada cihaz bölümünü
katlayıp açıyor.
