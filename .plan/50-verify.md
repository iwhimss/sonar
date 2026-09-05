# Faz 50 — Yanlış alarm ve doğrulama

**Durum:** 🟡 Ekran testleri kullanıcıda
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

## Kullanıcının bakması gerekenler (test turu 8)

- [ ] Ekolayzer: band değeri yaz + Enter → odak kalkmalı; başka banda geç → o bandın
      değerleri görünmeli; Q'ya 0.707 yaz → 0.707 kalmalı; harf yazılamamalı
- [ ] Band 1'in filtre tipini değiştir → band 2 kendi tipini göstermeli
- [ ] Favorilerden profil seç → üstteki açılır liste de değişmeli
- [ ] Var olan bir adla "Yeni profil" → kırmızı bildirim, pencere açık kalmalı
- [ ] Dışa aktar → bildirimde tam yol; içe aktar → aynı klasör
- [ ] Her efekt panelinde ↺ → ayarlar varsayılana dönmeli, ses kesilmemeli
- [ ] Efekt ekle → "Ses yolu onarıldı" bildirimi **çıkmamalı**
- [ ] **ChatMix tekerinin yönü** — hâlâ bekliyor
- [ ] **Mikrofon zinciri** (DeepFilterNet, gate, sidetone) hâlâ hiç ölçülmedi
