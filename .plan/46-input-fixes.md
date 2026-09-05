# Faz 46 — Bağlama ve giriş onarımı

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 45
**Çıktı:** `SonarComboBox` ve `SonarNumberField` onarıldı, iki yeni QML kuralı

---

## Ölçüm: `SonarComboBox` bağladığı özelliğe yazıyordu

```qml
function pick(index) {
    root.currentValue = option.value      // ← bağlamayı kalıcı olarak koparıyor
    root.activated(option.value)
}
```

QML'de bağlı bir özelliğe yazmak bağlamayı **kalıcı** olarak koparır. Yedi çağrı yerinin
hepsi `currentValue`'yu bir ifadeye bağlıyor, yani hepsi kırıktı. Kullanıcının iki
şikâyeti buradan:

* *"favorilerden cs2 seçince dropdown değişmiyor"*,
* *"band 1 için tepe/üst raf seçince 2. bandda da o gözüküyor"*.

İzole ölçüm (`tests/test_qml.py`):

```
pick(1) → activated="b", kutu hâlâ "a" gösteriyor   (sahibinin değeri)
sahibi "c" yapıyor → kutu "c"                        (bağlama sağlam)
```

## Ölçüm: `SonarNumberField` Enter'da odağı bırakmıyordu

Alan yazma kipinde kalıyordu; odak alandayken metin tazelenmediği için başka bir banda
geçince eski bandın değeri ekranda kalıyordu ve sonraki odak kaybı o metni **yeni** banda
yazıyordu. "Hz 7000 yazıyor ama grafik doğru", "geri gelince Hz 0 oluyor" bundandı.

İki eksik daha: doğrulayıcı yoktu (harf yazılabiliyordu) ve düzenleme kipinde
**yuvarlanmış** değer gösteriliyordu — Q alanı iki ondalıklıydı, yani kutuya girip
Enter'a basmak 0.707'yi gerçekten 0.71 yapıyordu.

Onarım sonrası ölçüm:

```
METİN     ['0.707', '1.414', '7000.000']   değer aynı turda izleniyor
DÜZENLEME '0.707'                          yuvarlanmamış
KOMİT     []                               değer değişmediyse yazım yok
YAZILAN   '12.5'                           "12ab.5" yazıldı, harfler girmedi
```

---

## Görevler

- [x] `SonarComboBox.pick()` artık `currentValue`'ya yazmıyor
- [x] `SonarNumberField`: Enter odağı bırakıyor, gönderim tek noktadan (odak kaybı)
- [x] Değer değişmediyse gönderim yok
- [x] Düzenleme kipinde tam değer; `RegularExpressionValidator` ile yalnızca sayı
- [x] Virgül ondalık ayracı kabul ediliyor (Türkçe klavye)
- [x] `committable`: seçili band yokken alan yazmıyor
- [x] EQ'da Q üç ondalık
- [x] `tests/test_qml.py` — **yeni kural**: `ui/` bileşenleri kendi API özelliklerine
      yazamaz. "Yuvarlatılmış köşe yok" ve "`x: x` yok" kurallarının kardeşi; bu tuzağa
      üç kez düşüldü
- [x] İki yeni davranış testi: sayı alanı ve açılır liste
