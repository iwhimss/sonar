# Faz 44 — FX sayfası yeniden

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 43
**Çıktı:** dikey efekt listesi, "Efekt ekle" penceresi, sürükleyerek sıralama

---

## Amaç

Kullanıcının isteği: *"Profil ayarlarına girince sadece ekolayzer ayarı gözüksün. Diğer
ayarları tıpkı EasyEffects programındaki gibi kullanıcı kendisi eklesin. Ekledikçe
gözüksün. Listelenirken de efektlerin ayarları hep alt alta listelensin."*

---

## Görevler

- [x] `Flow` (yan yana sarmalayan paneller) → **tek sütun**, sinyal sırasıyla alt alta
- [x] Panel listesi `bridge.effectsOf(target)`'tan; parametre satırları
      `core/dsp/effects.py`'nin meta verisinden **genel** olarak çiziliyor
- [x] `SonarFilterPanel`'e sürükleme tutamağı ve sil düğmesi
- [x] Sürükleyerek sıralama — favori şeridindeki `DropArea` deseninin aynısı
- [x] "＋ Efekt ekle": kategorilere ayrılmış pencere (Dinamikler, Tını, Uzam, Yardımcı)
- [x] Kurulu olmayan ve hedefe uymayan efektler listede yok; zincirde ekolayzer varsa
      ikincisi de gösterilmiyor ("tıkladım, hata verdi" olmasın)
- [x] Boş zincir hâli: tek cümlelik açıklama
- [x] Ekolayzer zincirin **bir üyesi**: eğri editörü listenin içinde, kendi tutamağı ve
      sil düğmesiyle

## Ölçümle bulunan iki hata

1. **Ekolayzer iki kez görünüyordu** — biri büyük eğri paneli, biri zincir listesindeki
   boş kutu. Sıra artık kullanıcının kararı olduğu için EQ'nun listedeki yeri anlamlı;
   eğri paneli listenin içine alındı.
2. **Parametre satırları boş çiziliyordu.** `effectsOf` serileştirilmiş profili okuyordu
   ve orada yalnızca **değerler** var — aralık, birim ve etiket yok. Meta veri efekt
   türüne bağlı ve değişmiyor, bu yüzden köprüde bir kez alınıp saklanıyor; değerler
   yine bellekteki profilden geliyor ki iyimser güncelleme çalışsın.

## Ekran

Medya kanalında dört efektli zincir: Ekolayzer (eğriyle) → Yankı → Kompresör → Stereo
Araçları. Her panelde tutamak, aç/kapa, sil; parametreler kendi aralıkları ve
birimleriyle. "Efekt ekle" penceresi on beş efekti dört kategoride listeliyor
(oynatma kanalında AI Gürültü Engelleme yok — orada anlamsız).
