# Faz 35 — ChatMix tekeri: protokol çözüldü

Faz 23'ten beri bekleyen tek iş. Kullanıcı `tekerlek.txt` ile ham kayıtları getirdi.

## Çözülen protokol

`/dev/hidraw2`, 64 baytlık raporlar; yalnızca ilk üç bayt anlamlı:

```
45 64 01   bayt0 = 0x45 rapor kimliği, bayt1 = 100, bayt2 = 1     (bir uç)
45 64 64   orta:  bayt1 = 100, bayt2 = 100
45 00 64   öbür uç: bayt1 = 0, bayt2 = 100
```

İki bağımsız 0–100 kazancı; biri 100'de sabitken diğeri iniyor, sonra rol değişiyor.

```
chatmix = 50 + (bayt2 - bayt1) / 2
```

Hangi ucun Game olduğu kayıttan çıkmıyor — yön ayarla ters çevrilebilir.

## Görevler

- [x] `engine/headset.py``decode_chatmix()` yazılsın; tanımadığı rapora `None`
      (batarya/durum raporları da aynı düğümden geliyor)
- [x] `tests/data/arctis7plus-wheel.txt` — `tekerlek.txt`'ten süzülmüş raporlar
- [x] Test: uçtan uca çevrim 0 → 50 → 100 ve monotonik
- [x] `settings.chatmix_invert` (varsayılan `False`) + `sonar-cli chatmix --invert`
- [x] `ChatMixReader.epsilon` 1.0 → 2.0; yazımlar 40 ms toplu pencerede birleşsin
- [x] `KNOWN_HEADSETS` kaydı doğrulanıp yorumlansın (`0x1038:0x220E`)

## Ölçüm
- Teker çevrilirken mikserdeki slider takip ediyor, kanal kazançları `pw-dump`'ta değişiyor
- Yön yanlışsa `--invert` düzeltiyor
