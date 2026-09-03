# Faz 28 — Master davranışı, dişli ve %300 fader

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 27

---

- [ ] **Master fader her şeyi etkilesin.** Bus sink'lerinin `capture.props` bölümüne
      `monitor.channel-volumes = true` eklensin; böylece monitör portları da master
      fader'ı duyar ve OBS hangi kaynağı seçerse seçsin aynı sesi alır. Ölçümle
      doğrulanacak (bugün `False`).
- [ ] `docs/OBS.md`: **yalnızca `Sonar Stream Mix — Virtual Input` eklenmeli.** "Ses
      Çıkışı Yakalama" ile aynı miksi ikinci kez almanın neden yanlış olduğu yazılsın;
      arayüzdeki Yayın Miksi bilgi satırına da kısa bir not düşülsün.
- [ ] Kanal şeridindeki **dişli düğmesi kaldırılsın** (üstteki sekmeler zaten FX
      sayfasını açıyor). Master şeridine bir dişli gelsin; cihaz bölümünü (Personal Mix /
      Mikrofon / Yayın Miksi) **katlayıp açsın**. Katlanma durumu `settings`'te saklansın.
- [ ] Fader'lar **%300**'e çıksın (`SonarFader` üst sınırı, yüzde metni, `Theme.volumeText`).
      Daemon zaten 0–4 kabul ediyor (`api._level`). %100 üstünde tutamak ve yüzde metni
      uyarı rengine dönsün; metre zaten kırpmayı kırmızı gösteriyor. Ses zincirine
      hiçbir şey eklenmiyor (kullanıcı kararı).
- [ ] Fader'ın çift tıkla sıfırlaması 1.0'a (birim kazanç) gitmeye devam etsin.

**Ölçüm:** OBS'in iki kaynağı da master yayın fader'ını takip ediyor (ton enjeksiyonu +
kayıt); %200'de çıkış tam +6.02 dB.
