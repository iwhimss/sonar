# Faz 47 — Hatalar görünür olsun

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 46
**Çıktı:** `ApiRejectedError`, reddedilen her çağrı bildirim şeridine düşüyor

---

## Ölçüm

`gui/dbus_client.py` `{"ok": false}` gelince yalnızca `log.warning` basıp `None`
döndürüyordu; `bridge._call` onu sessizce geçiyordu. Daemon'ın `Error` **sinyali**
yalnızca asenkron hatalar için — istemcinin **kendi** çağrısının reddi hiçbir yere
ulaşmıyordu.

Kullanıcının şikâyeti: *"Aynı isimde bir profil varsa eklemiyor. Ama eklemediği için de
uyarı yapmıyor."* Daemon zaten doğru davranıyordu (`api.new_profile` →
`duplicate_profile`, üzerine **yazmıyor**); eksik olan tek şey mesajın ekrana ulaşmasıydı.

Aynı sessizlik her reddi gizliyordu: dışa aktarmanın başarısız olup olmadığını,
kaldırılamayan son kanalı, geçersiz bir parametreyi.

---

## Görevler

- [x] `ApiRejectedError` — kod ve mesajı taşıyan istisna. Bağlantı kopmasından (
      `DaemonUnavailableError`) ayrı: biri kullanıcı hatası, diğeri altyapı
- [x] `bridge._call` reddi `errorRaised(code, message)` ile bildiriyor; bildirim şeridi
      zaten bağlıydı. Metin daemon'ın ürettiği metin, yani kullanıcının dilinde
- [x] Bağlantı kopması **bildirim üretmiyor**, yalnızca `connected` düşüyor — arayüz
      zaten kendi ekranını gösteriyor
- [x] `bridge.newProfile` başarıyı döndürüyor; "Yeni profil" penceresi ad reddedilirse
      açık kalıp alanı seçiyor
- [x] Testler: reddedilen çağrı `errorRaised` yayıyor; bağlantı kopması yaymıyor
