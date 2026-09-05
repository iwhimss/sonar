# Faz 45 — Doğrulama ve dokümantasyon

**Durum:** 🟡 Ekran testleri kullanıcıda
**Bağımlılık:** Faz 41–44

---

## Otomatik doğrulama

- [x] `ruff check src/ tests/` temiz
- [x] **998 test** geçiyor, 2 atlanıyor (turun başında 907)
- [x] `tests/test_qml.py` — yeni kural: kendine referans veren `x: x` ataması yok.
      Test turu 6'nın üç hatası bu desendendi
- [x] `test_every_effect_kind_builds_a_graph` — katalogdaki 16 efektin hepsi tek başına
      zincir kurabiliyor
- [x] `test_every_effect_starts_bypassed` — her efekt conf'a bypass'ta doğuyor; bypass
      yolu üç desende (LSP `enabled`, Calf `bypass`, Calf Reverb `on`) ve yönü ters
      çevirmek sessiz bir ses değişikliği demekti
- [x] `test_every_effect_is_actually_installed` — kataloğa girip kurulu olmayan eklenti yok
- [x] Şema 6 → 7 profil göçü: kapalı aşamalar düşüyor, açıklar sırasıyla slota dönüyor
- [x] Altın `graph.conf` yenilendi; fark yalnızca mikrofon zincirlerinden düşen sekiz ölü
      crossfeed node'u

## Elle ölçüm

- [x] `SonarValueField`: 0.5 → "50%", 1.0 → "100%", 0.25 → "25%" (önce hepsi bir adım
      geriydi)
- [x] Mikser kaydırma tutamağı 0 → 127.5 px, tam yol
- [x] `settingsDialog.bridge` ve `uninstallDialog.bridge` artık **bağlı**
- [x] Canlı grafta dokuz efekt birden: giriş -24.7 dBFS → hepsi açık -2.2 dBFS (tepe
      440 Hz) → hepsi kapalı -24.7 dBFS (**bit-şeffaf**)
- [x] Efekt ekle/sil/sırala conf'u değiştiriyor ve graf ayakta kalıyor (`doctor` 6/6)
- [x] FX sayfası iki dilde offscreen açıldı; QML uyarısı yok

## Dokümantasyon

- [x] `ARCHITECTURE.md` — "DSP zinciri" sabit topolojiden liste modeline göre yeniden
      yazıldı; 16 efektlik katalog tablosu, bypass desenleri, kataloğa **girmeyenlerin**
      nedenleri, node adı = slot kimliği
- [x] D-Bus tablosu 62 metot
- [x] `README.md` — efekt grupları ve "ne kesinti yaratır" ayrımı
- [x] `docs/TROUBLESHOOTING.md` — "eklemek istediğim efekt listede yok", "profil
      değiştirince ses kısa süre kesiliyor"
- [x] `.plan/00-overview.md`, `.plan/11-packaging.md` (`sonar-uninstall` görevi)

---

## Kullanıcının bakması gerekenler (test turu 7)

- [ ] Düzeltilen yedi hata: dil, ayar kutucukları, kaldırma, yüzde metni, mute hizası,
      mikser kaydırma, karşılama listesi başlığı
- [ ] FX sayfası: efekt ekle, sürükleyerek sırala, sil
- [ ] Yeni efektlerin **sesi** — ölçüm sinyal geçtiğini söylüyor, ama "yankı yankı gibi
      mi duyuluyor" kulakla anlaşılır
- [ ] Profil değiştirirken kesinti hissi (efekt listeleri farklıysa ~200 ms)
- [ ] **ChatMix tekerinin yönü** — hâlâ bekliyor
- [ ] **Mikrofon zinciri** (DeepFilterNet, gate, sidetone) hâlâ hiç ölçülmedi
