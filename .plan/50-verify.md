# Faz 50 — Yanlış alarm ve doğrulama

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 46–49

---

## Yanlış alarm

Efekt eklemek grafı yeniden kuruyor; o sırada **tüm** `pw-link` bağlantıları bir an yok
oluyor ve node'lar conf'un kurduğu sırayla, birbirinden bağımsız anlarda doğuyor. Bekçi
üst üste "eksik" ölçüp eşiği aşınca kullanıcıya "ses yolu koptu", bağlantılar gelince de
"Ses yolu onarıldı." diyordu.

- [x] `REBUILD_SETTLE_SECONDS` (2.5 sn) yerleşme penceresi: `_rebuild` sayacı sıfırlıyor
      ve pencere boyunca eksiklikler sayaca yazılmıyor
- [x] Pencere dolduktan sonra **gerçekten** kopan bağlantı yine bildiriliyor (test)
- [x] Canlı ölçüm: efekt ekle/sil → köprüde hiçbir bildirim yayılmıyor

**Takılmanın kendisi kalıyor** (kullanıcı kararı). Nedeni `ARCHITECTURE.md`'de:
`filter-chain` modülünün grafı çalışırken değiştirilemiyor.

### Plandan sapma

Plan "yeniden kurulum sırasında arayüz kısa bir bilgi göstersin" diyordu; **yapılmadı**.
Sıralama sürükleyerek yapılıyor ve `moveEffect` her sürükleme temasında çağrılıyor — her
çağrıda bildirim, bildirim fırtınası demekti. "Efekt ekle" penceresi maliyeti zaten
yazıyor.

---

## Doğrulama

- [x] `ruff check src/ tests/` temiz
- [x] **1026 test** geçiyor, 2 atlanıyor (turun başında 998)
- [x] Yeni testler: sayı alanının üç davranışı, açılır listenin bağlamayı koruması,
      `ui/` bileşenlerinin kendi API özelliğine yazmaması, reddedilen çağrının
      `errorRaised`'a dönüşmesi, bağlantı kopmasının bildirim üretmemesi,
      `reset_effect` (üç senaryo), yeniden kurulumun yanlış alarm üretmemesi
- [x] Canlı ölçümler: `reset_effect` 1.5 → 9.0 → 1.5 ve graf yeniden kurulmuyor;
      efekt ekle/sil sonrası hiçbir bildirim yok

## Dokümantasyon

- [x] `ARCHITECTURE.md` — "Neden efekt eklemek ~200 ms sessizlik yaratıyor": modülün
      grafı çalışırken değiştirilemiyor, EasyEffects'in farkı, alternatifin ölçülmüş
      bedeli, yerleşme penceresi
- [x] D-Bus tablosu 63 metot
- [x] `README.md` — panel başlığındaki ↺
- [x] `docs/TROUBLESHOOTING.md` — "dışa aktardığım profil içe aktarmada görünmüyor"
- [x] `.plan/00-overview.md`

---

## Kullanıcının ekran testleri (test turu 8) — 🟢 geçti

- [x] Ekolayzer: band değerleri, filtre tipleri, Q — sorun bildirilmedi
- [x] Favorilerden profil seçimi, profil pencereleri
- [x] Filtre başına sıfırlama
- [x] Efekt ekleme sonrası yanlış bildirim çıkmıyor
- [x] **ChatMix donanım tekeri sorunsuz çalışıyor.** Faz 23'ten (test turu 2) beri açık
      olan tek doğrulama maddesi kapandı: `decode_chatmix` protokolü doğru, yön doğru
      (`chatmix_invert = false` kaldı), `--invert` gerekmedi.
- [x] **Mikrofon zinciri kullanıldı.** Kullanıcı `mic` zincirine gürültü kapısı ekledi
      (zincir: `eq → gate`) ve birden fazla giriş kanalıyla denedi; sorun bildirilmedi.
      Faz 10'dan beri "hiç test edilmedi" diye taşınan madde kapandı.

Geriye ölçülmemiş tek şey **DeepFilterNet**: eklenti kurulu ve listede görünüyor
(`df`), ama kullanıcı henüz eklemedi.
