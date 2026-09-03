# Faz 32 — ChatMix tekeri, doğrulama, dokümantasyon

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 25–31

---

### ChatMix tekeri — udev sırası

Kullanıcının denemesi (`chatmix.txt`) başarısız oldu; sebebi ölçüldü: ACL'i
`73-seat-late.rules` uyguluyor, bizim dosya `99-` ile ondan **sonra** çalışıyor.

- [ ] Kural `packaging/60-sonar-headset.rules` olarak yeniden adlandırılsın
      (`70-uaccess.rules`'tan önce). Eski `99-` kopyasının silinmesi de anlatılsın.
- [ ] `scripts/sonar-hid-capture` erişim reddedildiğinde **doğru** komutu göstersin ve
      dosyanın nereye kopyalandığını kontrol etsin.
- [ ] Kural çalıştıktan sonra kullanıcı tekeri çevirirken rapor kaydedilsin; biçim
      çözülüp `decode_chatmix()` yazılsın ve kaydedilen raporlarla test edilsin.
      *(Bu adım yine kullanıcının bir kez `sudo` çalıştırmasını gerektiriyor.)*

### Projeyi bırakma / geri dönme

- [ ] `scripts/sonar-dev reset` eklensin: daemon'ı durdurur, grafı söker, varsayılan
      sink'i geri verir, kalan `sonar_*` node olup olmadığını doğrular ve EasyEffects'i
      tekrar açmak için ne yapılacağını söyler.
- [ ] `README.md` ve `docs/TROUBLESHOOTING.md`'ye **"Sonar'ı bırakırken"** bölümü.

### Doğrulama ve dokümantasyon

- [ ] `ruff check src/ tests/` ve `pytest -q` yeşil; yeni testler: metre tick
      regresyonu, zincir kimlikli mic slotları, `QJSValue` dönüşümü, slider bağlaması,
      tek-çıkış göçü, profildeki ducking, crossfeed bypass'ı, EQ band ekleme/silme.
- [ ] GUI **sıfır QML uyarısıyla** açılıyor.
- [ ] `README.md` / `ARCHITECTURE.md` / `docs/OBS.md` / `docs/PERFORMANCE.md`
      bu turun kararlarına göre güncellensin (çoklu çıkış bölümleri çıkar, crossfeed ve
      Smart Volume'un yeni yeri girer, D-Bus tablosu yeniden üretilir).
- [ ] `.plan/00-overview.md` faz tablosu ve sayılar güncellensin.
- [ ] Her faz sonunda commit + `iwhimss/sonar` `main` dalına push.
