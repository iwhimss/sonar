# Faz 41 — Bildirilen yedi hata

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 40
**Çıktı:** üç hata tek satırdan, dördü ölçümle bulundu

---

## Ölçüm: üç hatanın tek kök nedeni

`Main.qml`'de iki yeni diyalog `bridge: bridge` yazıyordu. QML'de sağdaki `bridge`
**nesnenin kendi** (tanımsız) özelliğine çözülüyor, context property'ye değil. Kullanıcının
gönderdiği `terminal.txt` bunu birebir gösteriyor:

```
SettingsDialog.qml:37:  TypeError: Cannot call method 'setLanguage' of undefined
SettingsDialog.qml:61:  TypeError: Cannot call method 'setTakeOverDefaultSink' of undefined
SettingsDialog.qml:68:  TypeError: Cannot call method 'setChatMixInvert' of undefined
UninstallDialog.qml:71: TypeError: Cannot call method 'deprovision' of undefined
```

Yani "dil değişmiyor", "kutucuklar tıklanmıyor" ve "kaldır bir şey yapmıyor" aynı satırdı.
Mikser ve FX sayfası doğru yazılmıştı (`window.bridgeRef()`); iki yeni diyalogda desen
atlanmış.

## Ölçüm: yüzde metni bir adım geride

`SonarValueField` izole edilip sürüldü:

```
value 0.5  → "50%"    ✓
value 1.0  → "50%"    ✗
value 0.25 → "100%"   ✗
```

`onValueChanged: field.text = root.display` — `display` ayrı bir binding ve handler
çalıştığında henüz tazelenmemiş. Fader `value`'ya doğrudan bağlı olduğu için doğru yere
gidiyordu; kullanıcının gördüğü "slider sıfırlanıyor, metin sıfırlanmıyor" tam olarak bu.

## Ölçüm: mikser zaten kayıyordu

900 px pencerede `contentWidth = 1002`, `width = 852`. Kaydırma çalışıyor ama
`AsNeeded` politikası duran ekranda hiçbir işaret bırakmıyor ve tekerlek fader tarafından
yeniyor. Eksik olan kaydırma değil, **tutamağıydı**.

## Ölçüm: mute düğmesi neden kayık

Fader sütununun genişliğini `SonarValueField` (58 px) belirliyor; fader+metre satırı
30 px ve sola yaslı. `horizontalCenter` mute'u 29'a, fader'ın merkezi ise 11'e düşüyordu.

---

## Görevler

- [x] `Main.qml` — `bridge: bridge` → `window.bridgeRef()` (iki yer)
- [x] `tests/test_qml.py` — kendine referans veren `x: x` atamasını yakalayan kural
- [x] `UninstallDialog` başarısızlığı yutmuyor: köprü `deprovisionFinished` yayıyor,
      pencere yalnızca gerçekten kaldırıldıysa "kalan işler" paneline geçiyor
- [x] `SonarValueField` — metin handler içinde yerinde hesaplanıyor + regresyon testi
- [x] Mute düğmesi fader'ın tam altında (fader + mute ortak sütunda, metre yanlarında)
- [x] Mikserde yatay kaydırma çubuğu içerik taştığında her zaman görünüyor;
      `Shift`+tekerlek yatay kaydırıyor
- [x] `Welcome.qml` gözden geçirme kipinde başlık "Şu an kurulu olanlar"
- [x] `terminal.txt` `.gitignore`'da
