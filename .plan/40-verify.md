# Faz 40 — Doğrulama ve dokümantasyon

**Durum:** 🟡 Ekran testleri kullanıcıda
**Bağımlılık:** Faz 37–39

---

## Otomatik doğrulama

- [x] `ruff check src/ tests/` temiz
- [x] **907 test** geçiyor (turun başında 839)
- [x] `tests/test_i18n.py` — katalog bütünlüğü: iki dilde aynı anahtarlar, aynı yer
      tutucular, boş çeviri yok, kaynakta kullanılan her anahtar katalogda, katalogda
      ölü çeviri yok
- [x] `tests/test_qml.py` — **yeni kural**: QML'de kullanıcıya görünen çıplak metin yok.
      "Yuvarlatılmış köşe yok" testinin kardeşi; kural kendiliğinden korunmazsa bir
      sonraki eklemede karışık dile geri dönülür. Kasıtlı bir ihlal eklenip testin
      gerçekten yakaladığı doğrulandı
- [x] `tests/conftest.py` — `default_language` autouse fixture'ı: testler geliştiricinin
      kendi dil ayarına bağlı değil
- [x] Şema 5 → 6 göçü: mevcut yapılandırma "kurulu" sayılıyor, yeni yapılandırma değil
- [x] `provisioned=False` iken `api.start()` PipeWire'a hiç dokunmuyor
- [x] Dil değişimi golden `graph.conf`'u değiştirmiyor (cihaz adları yapılandırmadan)

## Elle ölçüm

- [x] Kullanıcının yapılandırması bir kenara alınıp **sıfırdan kurulum** denendi:
      daemon başladı → 0 sonar node → karşılama ekranı → "kur" → 1.13 sn, 40 node → mikser
- [x] `sonar-cli uninstall` → 0 node, varsayılan çıkış geri verildi, ayarlar yerinde
- [x] `sonar-cli install` → 40 node
- [x] Kullanıcının yapılandırması geri kondu, `diff` ile doğrulandı
- [x] Arayüz iki dilde offscreen açıldı, ekran görüntüsü alındı; QML uyarısı yok
- [x] `sonar-cli status` / `doctor` iki dilde ölçüldü

## Dokümantasyon

- [x] `README.md` — "İlk açılış" bölümü (tanıtım + kur düğmesi), "Dil" bölümü,
      "Sonar'ı bırakırken" kaldırıcıya göre yeniden yazıldı
- [x] `docs/TROUBLESHOOTING.md` — üç yeni başlık: "Kanallar hiç görünmüyor, karşılama
      ekranı açılıyor", "Kaldırdım ama sanal cihazlar hâlâ duruyor", "Arayüz yarı Türkçe
      yarı İngilizce"
- [x] `ARCHITECTURE.md` — "Kurulum durumu ve dil" bölümü: `provisioned` ne yapıyor, kim
      hangi dili nereden okuyor, adların neden çevrilmediği, QML tazeleme tuzağı
- [x] D-Bus metot tablosu 57 metoda güncellendi; `SetChatMixInvert` ve `StreamSetup`
      (Faz 33/35'ten beri belgesizdi) eklendi
- [x] `.plan/00-overview.md` durum tablosu ve kararlar
- [x] `.plan/11-packaging.md` — D-Bus servis dosyasının kurulumu ve katalogun pakete
      girmesi eklendi

---

## Kullanıcının bakması gerekenler (test turu 6)

Ölçemediklerim:

- [ ] Karşılama akışı gerçek ekranda: dil seçimi, sayfalar arası gezinme, "kur"
      düğmesinin hissi
- [ ] Kaldırıcı: kanallar gerçekten gitti mi, ses eski hâline döndü mü
- [ ] Dil değiştirince arayüzde Türkçe/İngilizce karışık kalan bir yer var mı
- [ ] Arayüzden "Servisi başlat" (daemon kapalıyken) çalışıyor mu
- [ ] **ChatMix tekerinin yönü** — hâlâ bekliyor. Ters geliyorsa artık Ayarlar'dan
      kutucukla düzeltilebiliyor (CLI şart değil)
- [ ] **Mikrofon zinciri** (DeepFilterNet, gate, sidetone) hâlâ hiç ölçülmedi
