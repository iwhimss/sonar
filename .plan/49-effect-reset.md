# Faz 49 — Filtre başına sıfırlama

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 48

---

## Amaç

Kullanıcının isteği: *"Tüm filtre ayarlarına sıfırlama ayarı eklenmeli filtre başına.
Tıklayınca varsayılan haline gelmeli."*

---

## Görevler

- [x] `api.reset_effect(target, slot)` — slotun parametreleri `DEFAULT_FILTER_PARAMS`'a
      döner. **Canlı**: zincir değişmiyor, ses kesintisi yok
- [x] Efektin açık/kapalı durumu değişmiyor — "sıfırla" ayarları geri almak demek,
      kapatmak değil
- [x] Ekolayzerde: kazançlar 0 dB, tipler tepe, Q band sayısına göre, ön kazanç 0 dB.
      **Band sayısı korunuyor** (kullanıcı kararı) — eğriye sağ tıkla eklenen noktalar
      silinmiyor
- [x] D-Bus `ResetEffect` → 63 metot; `sonar-cli effect reset <hedef> <slot>`
- [x] Panel başlığına ↺ (`SonarFilterPanel` ve `EqPanel`), mikserdeki fader
      sıfırlamasıyla aynı ikon
- [x] `SonarIconButton.tooltip` bir süredir bildirilip **hiç çizilmiyordu**; başlıkta üç
      küçük düğme yan yana gelince gerektiği için artık çiziliyor

## Ölçüm

Canlı grafta, medya kanalındaki Yankı efekti:

```
başlangıç          reverb:decay_time = 1.5
decay_s = 9.0      reverb:decay_time = 9.0
ResetEffect        reverb:decay_time = 1.5
sonar node sayısı  28 → 28   (graf yeniden kurulmadı)
```
