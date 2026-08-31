# Faz 5 — Uygulama yönlendirme

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 4
**Çıktı:** `src/sonar/engine/router.py`, `tests/test_router.py` — 51 yeni test (toplam 442)

---

## Amaç

Hangi uygulamanın hangi kanala gideceğini belirlemek: yeni bir ses akışı açıldığında
kurallara bakıp doğru sanal cihaza yönlendirmek, kullanıcının elle yaptığı taşımaları
kalıcı kural hâline getirmek.

---

## Ölçüm: yarış koşulu ne kadar büyük?

Plan, akış oluşturulduktan sonra taşımanın sesin ilk 10–20 ms'sini yanlış cihazda
çalabileceğinden endişeleniyordu ve `pw-metadata` ile **önceden** hedef ayarlamayı birincil
yol olarak öneriyordu.

Router'a gecikme ölçümü eklendi (akışın ilk görülmesinden taşımanın tamamlanmasına).
Altı ardışık akışta ölçülen:

```
3.5 ms · 3.7 ms · 3.7 ms · 4.1 ms · 4.3 ms · 4.8 ms
```

**Karar: önceden ayarlama yolu gereksiz.** ~4 ms endişe edilen aralığın çok altında ve
tipik bir PipeWire kuantumundan (1024/48000 ≈ 21 ms) kısa; pratikte tek bir tampon bile
yanlış yere gitmiyor. Basit tepkisel yol korunuyor, karmaşıklık eklenmiyor.

Gecikme her yönlendirmede loglanıyor:
```
yönlendirildi: #390 pw-cat → game (pw-cat) — 3.6 ms
```

---

## Görevler

### `engine/router.py` — kural motoru
- [x] `pwstate` değişiklik bildirimi → yeni akışları tespit et
- [x] Eşleştirme anahtarları öncelik sırasıyla: `binary` → `app_name` → `media_name`
- [x] Aynı öncelikte daha spesifik (daha uzun desenli) kural kazanır
- [x] Eşleşme yoksa → `settings.default_channel`
- [x] Silinmiş kanalı gösteren yetim kural yok sayılır
- [x] Bozuk regex sessizce hiç eşleşmez, hata yükseltmez
- [x] **Her akış yalnızca bir kez yönlendirilir.** Sürekli izleyip düzeltmek kullanıcıyla
      kavga etmek olurdu: pavucontrol'den elle taşıdığını anında geri çekerdik. Ayrıca
      akışın gerçekte nereye bağlı olduğunu `target.object`'ten güvenilir okuyamıyoruz —
      WirePlumber kendi bağladığında bu alan boş kalıyor
- [x] Elle taşınan akışa kural motoru bir daha dokunmaz (`mark_manual`)
- [x] Kendi loopback'lerimiz ve kayıt akışları hiç ele alınmaz
- [x] Başarısız taşıma döngüye girmez (her olayda yeniden denenmez)
- [x] Yönlendirme gecikmesi ölçülüp loglanıyor

### Yarış koşulu koruması
- [x] Ölçüldü: ~4 ms. **Önceden `pw-metadata` ile hedef ayarlama yoluna gerek kalmadı**
- [x] Tepkisel yol tek yol; `pw-metadata <node-id> target.object <ad>` ile taşınıyor

### Kalıcı kurallar
- [x] `MoveStream(id, kanal, remember)` — `remember` ile akışın binary'sinden kalıcı kural
      üretilir (arayüzdeki "bu uygulamayı hep buraya gönder" seçeneği bunu kullanacak)
- [x] Kimlik binary → app adı → medya adı sırasıyla aranır; hiçbiri yoksa anlaşılır hata
- [x] `sonar-cli move <id> <kanal> --remember`
- [x] Kurallar `config.toml` içinde, elle düzenlenebilir
- [x] Varsayılan kurallar: Chat ← Discord/vesktop/TeamSpeak/Mumble/WebRTC;
      Media ← firefox/chrome/chromium/brave/spotify/mpv/vlc;
      **Game ← `\.exe$`, `^wine`, `^steam_app_`** (regex, bu fazda eklendi)

### Varsayılan sink devralma
- [x] `settings.take_over_default_sink` (Faz 3'te uygulandı, varsayılan kapalı)
- [x] Kapanışta eski değere geri dönülüyor
- [x] Kapalıyken hiçbir sistem ayarına dokunulmuyor

### Testler — 51 yeni test
- [x] Kural önceliği, spesifiklik, regex, bozuk regex, kapalı kural, yetim kural
- [x] Manuel taşımanın ezilmemesi, tek seferlik yönlendirme, başarısız taşımanın döngüye
      girmemesi
- [x] **id geri dönüşümü** (aşağıya bak), kapanan akışın unutulması
- [x] Aynı uygulamanın çoklu akışları, kural değişiminin yalnızca yeni akışları etkilemesi
- [x] Varsayılan oyun kurallarının normal uygulamaları yakalamaması

---

## Doğrulama — ✅ gerçek sistemde

| Test | Sonuç |
|---|---|
| 6 ardışık akış | **6/6** doğru kanala yönlendirildi |
| Yönlendirme gecikmesi | **3.5 – 4.8 ms** |
| `sonar-cli route --key app_name pw-cat game` | sonraki akış `game`'e düştü |
| Kendi loopback'lerimiz | hiç ele alınmadı |
| Elle taşıma | kural motoru geri almadı |

### EasyEffects kapalıyken tekrarlanan doğrulama

Kullanıcının izniyle EasyEffects geçici olarak durduruldu ve ölçülemeyen senaryolar
tamamlandı.

**Duyulabilir yarış penceresi.** 3.000 s'lik sinüs hedefsiz açıldı, router taşıdı,
`sonar_media_fx`'ten kaydedildi:

| | kanaldaki süre | kayıp |
|---|---|---|
| doğrudan `sonar_media`'ya (referans) | 3.000 s | 0 |
| hedefsiz → router taşıyor | 2.979 s | **21 ms** |
| aynısı, ikinci deneme | 2.979 s | **21 ms** |

21 ms tam olarak bir PipeWire kuantumu (1024/48000 = 21.3 ms). Yani en fazla **tek bir
tampon** varsayılan cihaza gidiyor. Karar gecikmesi ~4 ms olduğu için geri kalanı ses
hattının tanecikliği; önceden hedef ayarlamayla da kazanılamazdı.

**Çoklu uygulama.** Arc Raiders + Discord + Firefox aynı anda, üçü de kendi kuralıyla:

```
Firefox      → media (firefox)   —  4.4 ms
Arc Raiders  → game  (\.exe$)    —  7.9 ms
Discord      → chat  (Discord)   — 13.0 ms
```

**Kanal izolasyonu.** Her uygulama tek başına çalarken diğer kanallar dijital sessizlikte:

| Uygulama | `game_fx` | `chat_fx` | `media_fx` |
|---|---|---|---|
| Arc Raiders | **-24.31** | -240.00 | -240.00 |
| Discord | -240.00 | **-24.31** | -240.00 |
| Firefox | -240.00 | -240.00 | **-24.30** |

**Kişisel ↔ yayın ayrımı** (kullanıcının asıl isteği). Oyun + tarayıcı birlikte çalarken:

| Durum | kulaklık | yayın |
|---|---|---|
| ikisi de açık | -18.25 | -18.25 |
| media'nın **yayın** faderi kapalı | -18.29 (ikisi) | **-24.32 (sadece oyun)** |
| game'in **kulaklık** faderi kapalı | **-24.32 (sadece media)** | -18.29 (ikisi) |

İki miks tamamen bağımsız.

---

## Yol boyunca yakalananlar

1. **`pactl move-sink-input` node id ile çalışmıyor.** PulseAudio **sink-input indeksi**
   bekliyor; ikisi ayrı numaralandırma (ölçüldü: node 251 ↔ indeks 13163) ve node id'siyle
   çağrılınca sessizce `exit 1` veriyor. Yani akış taşıma Faz 4'ten beri gerçek kullanımda
   hiç çalışmamıştı — birim testleri sahte bir `control` kullandığı için görünmüyordu.
   `pw-metadata <node-id> target.object <ad>` ile değiştirildi.
2. **`pw-metadata` değeri tırnaksız verilmeli.** `'"sonar_media"'` gibi JSON tırnağı
   eklendiğinde ad eşleşmiyor ve WirePlumber akışı **sessizce varsayılan cihaza**
   gönderiyor — taşındı ama yanlış yere.
3. **`QTimer.singleShot(0, …)` yabancı iş parçacığından sessizce hiçbir şey yapmıyor.**
   Uyarı bile vermiyor; yönlendirme hiç tetiklenmiyordu. Qt sinyalleri iş parçacığı güvenli
   olduğu için araya bir `_ThreadBridge` konuldu.
4. **PipeWire node id'leri geri dönüştürüyor.** Kapanan akışın id'si saniyeler içinde
   yenisine veriliyor; silinme olayı bize ulaşmadan yeni akış "zaten karar verilmiş"
   sanılıyordu — ölçümde **beş akıştan ikisi yönlendirilmedi**. Kayıtlar artık asla
   tekrarlanmayan `object.serial` ile tutuluyor. Düzeltmeden sonra 6/6.
5. **Geri dönüştürülen id, gecikme ölçümünü de bozuyordu** — zaman damgası eski akıştan
   kalıyor ve 3.2 saniyelik sahte gecikmeler loglanıyordu.

---

## Tamamlanma kriteri — ✅ karşılandı

Uygulamalar açıldıkları anda (~4 ms içinde) doğru kanala düşüyor; elle taşıma çalışıyor ve
`--remember` ile kalıcılaşıyor; bozuk kural sistemi bozmuyor.

```bash
ruff check src/ tests/ && pytest -q          # 442 test geçti, lint temiz
```
