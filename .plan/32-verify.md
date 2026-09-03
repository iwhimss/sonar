# Faz 32 — ChatMix tekeri, doğrulama, dokümantasyon

**Durum:** 🟡 Kod tarafı bitti, ekran ve `sudo` kullanıcıda
**Bağımlılık:** Faz 25–31

---

### ChatMix tekeri — udev sırası

Kullanıcının denemesi (`chatmix.txt`) başarısız oldu; sebebi ölçüldü: ACL'i
`73-seat-late.rules` uyguluyor, bizim dosya `99-` ile ondan **sonra** çalışıyor.

- [x] Kural `packaging/60-sonar-headset.rules` olarak yeniden adlandırılsın
      (`70-uaccess.rules`'tan önce). Eski `99-` kopyasının silinmesi de anlatılsın.
- [x] `scripts/sonar-hid-capture` erişim reddedildiğinde **doğru** komutu göstersin ve
      dosyanın nereye kopyalandığını kontrol etsin.
- [ ] Kural çalıştıktan sonra kullanıcı tekeri çevirirken rapor kaydedilsin; biçim
      çözülüp `decode_chatmix()` yazılsın ve kaydedilen raporlarla test edilsin.
      *(Bu adım yine kullanıcının bir kez `sudo` çalıştırmasını gerektiriyor.)*

### Projeyi bırakma / geri dönme

- [x] `scripts/sonar-dev reset` eklensin: daemon'ı durdurur, grafı söker, varsayılan
      sink'i geri verir, kalan `sonar_*` node olup olmadığını doğrular ve EasyEffects'i
      tekrar açmak için ne yapılacağını söyler.
- [x] `README.md` ve `docs/TROUBLESHOOTING.md`'ye **"Sonar'ı bırakırken"** bölümü.

### Doğrulama ve dokümantasyon

- [x] `ruff check src/ tests/` ve `pytest -q` yeşil; yeni testler: metre tick
      regresyonu, zincir kimlikli mic slotları, `QJSValue` dönüşümü, slider bağlaması,
      tek-çıkış göçü, profildeki ducking, crossfeed bypass'ı, EQ band ekleme/silme.
- [x] GUI **sıfır QML uyarısıyla** açılıyor.
- [x] `README.md` / `ARCHITECTURE.md` / `docs/OBS.md` / `docs/PERFORMANCE.md`
      bu turun kararlarına göre güncellensin (çoklu çıkış bölümleri çıkar, crossfeed ve
      Smart Volume'un yeni yeri girer, D-Bus tablosu yeniden üretilir).
- [x] `.plan/00-overview.md` faz tablosu ve sayılar güncellensin.
- [x] Her faz sonunda commit + `iwhimss/sonar` `main` dalına push.


---

## Durum

**Kod tarafı bitti:** 829 test geçiyor, `ruff` temiz, 51 D-Bus metodu, GUI sıfır QML
uyarısıyla açılıyor. Ölçülebilen her madde ölçüldü; sonuçlar `docs/PERFORMANCE.md`
içinde "Test turu 3 ölçümleri" başlığı altında.

### ChatMix tekeri — kök neden bulundu, kullanıcının bir kez `sudo` çalıştırması lazım

Kullanıcının denemesi (`chatmix.txt`) başarısız olmuştu. Sebebi ölçüldü: `uaccess`
etiketini gören ACL'i `/usr/lib/udev/rules.d/73-seat-late.rules` uyguluyor ve udev
kuralları **ad sırasına** göre çalışıyor. Bizim dosya `99-` ile ondan **sonra**
çalıştığı için etiket hiç işlenmiyordu.

Dosya `60-sonar-headset.rules` oldu (systemd'nin `70-uaccess.rules`'ından da önce).

```bash
sudo cp packaging/60-sonar-headset.rules /etc/udev/rules.d/
sudo rm -f /etc/udev/rules.d/99-sonar-headset.rules
sudo udevadm control --reload && sudo udevadm trigger
./scripts/sonar-hid-capture      # tekeri yavaşça uçtan uca çevir, Ctrl+C
```

Çıktıdaki değişen bayt `decode_chatmix()` içine yazılacak ve kaydedilen raporlarla test
edilecek.

### Ekrana bakmayı gerektirenler

- [ ] Sürüklenen kutucuk sürükleme boyunca görünüyor ve sütunların altında kalmıyor
- [ ] Mikser mute (✕) düğmeleri anında tepki veriyor ve gerçekten susturuyor
- [ ] Seviye barları kanal eklendikten/silindikten sonra da oynuyor
- [ ] İkinci giriş kanalının fader ve mute'ları yalnızca kendini etkiliyor
- [ ] EQ eğrisinde boşluğa sağ tık nokta ekliyor, düğüme sağ tık siliyor
- [ ] Master dişlisi cihaz bölümünü açıp kapatıyor
- [ ] Fader'lar %300'e çıkıyor ve %100 üstünde uyarı rengine dönüyor
- [ ] Spatial Audio açık/kapalı farkı duyuluyor
- [ ] Smart Volume kanal profilinde açılıyor ve çalışıyor
- [ ] OBS'te yalnızca `Sonar Stream Mix — Virtual Input` ile kayıt doğru çalışıyor
- [ ] Küçük pencerede hiçbir şey kırpılmıyor (kaydırma çalışıyor)
