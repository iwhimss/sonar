# Faz 48 — Dosya pencereleri

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 47

---

## Ölçüm

`ChannelFx.qml`: `currentFile: "file://" + root.activeName + ".sonarprofile"`.
Bu geçerli bir URL değil — `file://Medya.sonarprofile` URL kurallarına göre bir **host**
adı, yol boş. Qt onu yok sayıyor ve pencere kendi varsayılan klasöründe açılıyor; içe
aktarma penceresi ise **kendi** varsayılanında. Kullanıcı belgelerine kaydedip ev
dizininde arıyordu.

Dosyanın nereye düştüğü de belirsizdi: bildirim yalnızca dosya **adını** yazıyordu.

---

## Görevler

- [x] `bridge.profileFolder` — iki pencerenin de açılacağı klasör. İlk açılışta Belgeler
      (`QStandardPaths.DocumentsLocation`), sonra son kullanılan
- [x] `bridge.rememberProfileFolder()` — klasör `ui.json`'da saklanıyor (pencere
      boyutunun durduğu yer)
- [x] Dışa aktarmada `currentFile` yalnızca **dosya adı**; klasörü `currentFolder` veriyor
- [x] Bildirim tam yolu yazıyor
- [x] İçe aktarmada `.sonarprofile` süzgeci ilk sırada
- [x] `docs/TROUBLESHOOTING.md`: "dışa aktardığım profil içe aktarmada görünmüyor"

**Ölçüm:** `bridge.profileFolder` → `file:///home/fatih/Belgeler`.
