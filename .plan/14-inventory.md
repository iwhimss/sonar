# Faz 14 — Envanter doğruluğu

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 5
**Çıktı:** `src/sonar/engine/pwstate.py`, `src/sonar/engine/router.py`,
`src/sonar/gui/bridge.py`, `src/sonar/gui/qml/ChannelStrip.qml`,
`tests/test_pwstate.py`

---

## Amaç

> Açtığım bir uygulamayı kapattığımda hâlâ görünmeye devam ediyor. Mesela Brave'i
> açtım, kapattıktan sonra görünmeye devam ediyordu.

Kök neden ölçüldü (tahmin değil).

---

## Ölçülen kök neden

`pw-dump -m` bir node silindiğinde şunu yayar:

```json
[ { "id": 391, "info": null } ]
```

**`type` alanı yok.** `pwstate.GraphState.apply()` ise şöyle eliyor:

```python
if obj.get("type") != "PipeWire:Interface:Node":
    continue
```

Yani **silme olayları hiç işlenmiyor**; `_apply_node()` ve dolayısıyla `_remove()`
hiç çağrılmıyor. Sonuç:

- Kapanan uygulamalar akış listesinde kalıyor
- Çıkarılan USB cihazlar cihaz listesinde kalıyor
- `nodes` haritası ölü node id'leriyle büyüyor — canlı parametre yazımı ölü id'ye
  gidebilir

Bu, Faz 5'ten beri var olan sessiz bir hata. `_remove()` yazılmış ve test edilmiş
ama gerçek olay akışında hiç tetiklenmiyor.

**Doğrulama komutu** (2026-09-01, bu makinede çalıştırıldı):

```bash
pw-dump -m > dump.jsonl &
pw-cat --record --format f32 --rate 8000 --channels 1 /dev/null   # kısa bir akış
# → dump.jsonl içinde: {"id": 391, "info": null}
```

---

## Yaklaşım

`apply()` iki olay biçimini de tanır:

```python
if obj.get("info") is None:          # silme — type alanı gelmiyor
    changed |= self._remove(obj["id"])
    continue
if obj.get("type") != "PipeWire:Interface:Node":
    continue
```

Silme olayı node dışındaki nesneler (port, link, device) için de gelir; `_remove()`
bilmediği id'de zaten hiçbir şey yapmaz, o yüzden ayrım gerekmez.

Ek temizlik: silinen akışın `router.decided` ve `state.stream_seen` kayıtları da
düşer — yoksa uzun oturumda sözlükler sınırsız büyür.

### Apps kutusu taşması

`ChannelStrip.qml`'deki Apps kutusu sabit 120 px, `clip` yok, `Column` + `Repeater`
kullanıyor ve görünmeyen satırlar için `height: 0` numarası yapıyor. Çok uygulama
açıkken taşıyor. Yerine:

- Şeritte kalan alanı dolduran, `clip: true` bir `ListView`
- Kanal filtrelemesi **model tarafında** (köprüde `streamsFor(channelId)` benzeri bir
  filtre modeli) — görünmez satır üretilmez
- Kaydırma çubuğu, sürükle-bırak korunur

---

## Görevler

- [ ] `pwstate.apply()` silme olaylarını tanır
- [ ] Regresyon testi: `{"id": N, "info": null}` → `streams`/`nodes`/`devices` düşer
      ve `STREAMS` değişikliği bildirilir
- [ ] `router.decided` ve `stream_seen` silinen akışlar için temizlenir + testi
- [ ] Apps kutusu: kaydırmalı, kırpılmış `ListView`
- [ ] Akış taşınınca hedef kanalın profilinden geçtiği ölçümle doğrulanır

---

## Ölçüm

Faz bitince buraya yazılacak:

- Brave açılır/kapatılır → listeden kaç ms içinde düşüyor
- 20 akış açıkken Apps kutusunun görüntüsü (taşma yok, kaydırma çalışıyor)
- Akış Media → Game'e taşınır; Game'de 1 kHz'de -20 dB'lik dar bir çentik açılır;
  taşınan akışın çentikten geçtiği kayıtla doğrulanır

---

## Yol boyunca yakalananlar

_(faz sırasında doldurulacak)_
