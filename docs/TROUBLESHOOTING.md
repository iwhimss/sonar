# Sorun giderme

## Seçtiğim çıkış cihazı yok sayılıyor

**En sık sebep: EasyEffects (veya JamesDSP) sistem geneli çalışıyor.**

EasyEffects "service mode"da her oynatma akışını kendi sink'ine çeker — Sonar açıkça bir
cihaz istese bile. Ölçüldü: `pactl move-sink-input` hatasız döner, bağlantı anında
`easyeffects_sink`'e geri alınır. Hiçbir hata mesajı görünmez, ses "yanlış yerden" gelir.

Sonar zaten EasyEffects'in yaptığı işi (LSP eklentileriyle EQ, gate, kompresör, limiter)
kanal başına yapıyor. İkisini birlikte çalıştırmanın bir faydası yok.

```bash
# EasyEffects'i tamamen durdur
systemctl --user stop easyeffects        # varsa
pkill easyeffects
# otomatik başlamasını engelle: EasyEffects → Ayarlar → "Oturum açılışında başlat" kapalı
```

Alternatif: EasyEffects'in **dışlama listesine** Sonar'ın çıkışlarını ekleyin
(`sonar_personal_out`, `sonar_stream_out`).

Sonar bu durumu açılışta tespit eder ve `sonar-cli status` çıktısının sonunda uyarı basar.

## Hiç ses yok

1. Graf ayakta mı?
   ```bash
   sonar-cli status          # en altta "Graf henüz hazır değil" yazmamalı
   pw-dump | grep sonar_game
   ```
2. Uygulama doğru kanala mı düşmüş? `sonar-cli status` çıktısındaki "ÇALAN UYGULAMALAR"
   bölümüne bakın; değilse `sonar-cli move <id> <kanal>`.
3. Fader kapalı olabilir: `sonar-cli volume game personal 100`.
4. Mute açık olabilir: `sonar-cli mute game personal off`.

## Çift ses / yankı

Aynı uygulama hem bir Sonar kanalına hem doğrudan fiziksel cihaza bağlıysa olur.
`sonar-cli status` ile hedefini kontrol edin; gerekirse `sonar-cli move` ile taşıyın.

Mikrofon yankısı için: yan ton (monitor) açık olabilir. Kapatmak için
`SetMicMonitor` metodunu `false` ile çağırın.

## "Eklenti bulunamadı" / bazı efektler yok

Sonar LSP LV2 eklentilerini ve isteğe bağlı DeepFilterNet'i kullanır. Kurulu değilse o
aşama zincirden **sessizce düşer** (graf yine kurulur, o efekt görünmez).

```bash
pacman -S lsp-plugins-lv2          # Arch / CachyOS
# AI gürültü engelleme için (isteğe bağlı):
paru -S deepfilter-ladspa
```

Kurulu olanları görmek için:
```bash
python -c "from sonar.core.dsp.registry import available_plugins; print(available_plugins())"
```

## Yüksek CPU

Boştaki graf ~%6-7 CPU (tek çekirdeğin) harcar. Bundan belirgin fazlaysa:

* Kanal sayısını azaltın — her kanal kendi DSP zincirini taşır.
* Kullanmadığınız kanalları silin: `RemoveChannel`.

Not: LSP ekolayzerinin FFT analizörleri Sonar tarafından kapatılıyor; açık olsalardı CPU
üç katına çıkardı.

## Daemon başlamıyor

```bash
systemctl --user status sonar-daemon
journalctl --user -u sonar-daemon -n 50
SONAR_LOG=debug sonar-daemon        # elle, ayrıntılı log ile
```

"başka bir Sonar daemon'ı zaten çalışıyor" mesajı hata değildir — ikinci örnek temiz çıkar.

## Ayarlarım kayboldu

Yapılandırma `~/.config/sonar/config.toml`, profiller `~/.config/sonar/profiles/`.
Bozuk bir `config.toml` otomatik olarak `config.toml.corrupt-<zaman>` adıyla yedeklenir ve
varsayılana dönülür — yedeğe bakıp elle kurtarabilirsiniz.

Elle düzenleme yaptıysanız daemon'a haber verin:
```bash
sonar-cli reload
```

## PipeWire yeniden başladıktan sonra ses gitti

Daemon grafı kendi yeniden kurar (`PartOf=pipewire.service`). Olmazsa:
```bash
systemctl --user restart sonar-daemon
```
