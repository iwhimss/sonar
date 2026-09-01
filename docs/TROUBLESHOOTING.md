# Sorun giderme

## Seçtiğim çıkış cihazı yok sayılıyor

**En sık sebep: EasyEffects (veya JamesDSP) sistem geneli çalışıyor.**

EasyEffects "service mode"da her oynatma akışını kendi sink'ine çeker — Sonar açıkça bir
cihaz istese bile. Ölçüldü: taşıma komutu hatasız döner, bağlantı anında
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
5. Kanal gönderileri bağlı mı? Kanal çıkışları bus'lara `pw-link` ile bağlanıyor:
   ```bash
   pw-link -l | grep to_personal_capture
   ```
   Her kanal için iki satır (FL, FR) görmelisiniz. Yoksa daemon logunda
   "kanal gönderisi bağlanamadı" satırı vardır; `sonar-cli reload` yeniden dener.

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

Daemon bunu kendi fark edip grafı yeniden kurar; **ölçülen toparlanma süresi 6 saniye.**

PipeWire yeniden başlatıldığında bizim `pipewire -c graph.conf` istemcimiz ölmez, yalnızca
bağlantısını kaybeder — süreç canlı görünürken graf boş kalır. Gözcü bu yüzden süreç
ölümüne değil, "beklenen node'ların hiçbiri grafta yok" durumuna da bakar (2 sn aralıkla,
üst üste iki boş ölçüm).

6 saniyeden uzun sürerse:
```bash
systemctl --user restart sonar-daemon
```

## Sanal cihazları göremiyorum

Önce gerçekten var mı bakın:

```bash
pactl list short sinks   | grep sonar    # çıkış kanalları + bus'lar
pactl list short sources | grep sonar    # giriş kanalları + Stream Mix
```

Adlar yönü söyler: `Sonar Game — Virtual Output` bir çıkış, `Sonar Mic — Virtual Input`
bir giriştir.

**Kanallarım mikrofon listesinde görünüyor.** Bu, o kanalın "OBS kaynağı" anahtarı
açık demektir. Kapatın:

```bash
sonar-cli obs game off
```

Varsayılan kapalıdır; kapalıyken kanal yalnızca birleşik Stream Mix üzerinden yayına gider.

**`*.monitor` girdileri.** Her sink'in bir monitörü olur — fiziksel kartlarda da vardır,
Sonar'a özgü değildir ve kaldırılamaz.

## Uygulama yanlış kanalda

```bash
sonar-cli status          # hangi uygulama hangi kanalda
sonar-cli rules           # etkin kurallar
```

Taşımak ve kalıcılaştırmak:

```bash
sonar-cli move <akış-id> game --remember
```

Kural eklemek/kaldırmak:

```bash
sonar-cli route cs2_linux64 game
sonar-cli rules --remove binary=cs2_linux64
```

**Not:** her akış yalnızca **bir kez** yönlendirilir. Bir uygulamayı pavucontrol'den elle
taşırsanız Sonar geri almaz; kural yalnızca yeni açılan akışlara uygulanır.

## Ayarlarım kaydedilmiyor

Daemon şu uyarıyı veriyorsa disk dolu veya dizin yazılamıyordur:

```
yapılandırma diske yazılamadı: [Errno 28] ...
```

Ayarlar bellekte çalışmaya devam eder ama yeniden başlatınca kaybolur. Kontrol:

```bash
df -h ~/.config
ls -ld ~/.config/sonar
```

## Preset'i düzenleyemiyorum

Gömülü presetler (`Flat`, `FPS Footsteps`, `Broadcast`…) salt okunurdur. Düzenlemeye
başladığınızda otomatik olarak `"<ad> (özel)"` adıyla bir kopya oluşturulup ona geçilir —
liste `sonar-cli presets <kanal>` çıktısında 🔒 ile işaretlidir. Arayüz bunu bir bildirim
şeridiyle söyler.

## Profillerde "kaydet" düğmesi yok

Kasıtlı. Her değişiklik aktif profile yazılır ve yarım saniye içinde diske geçer. Yeni bir
varyant için **＋ Yeni profil** (veya `sonar-cli new <kanal> <ad>`): isim sorar, sıfırdan
düz bir profil açar, mevcut profile dokunmaz.

Favoriler `config.toml` içinde hedef başına sıralı bir liste; sayı sınırı yok:

```bash
sonar-cli favorite add game "CS2"
sonar-cli favorite list game
```

## Her şeyi sıfırlamak

Tek bir kanalın profilini düzleştirmek:

```bash
sonar-cli reset game
```

Tüm yapılandırmayı silmek (daemon durdurulmuş hâldeyken):

```bash
systemctl --user stop sonar-daemon
rm -rf ~/.config/sonar ~/.local/state/sonar
systemctl --user start sonar-daemon
```

## Log toplamak

```bash
journalctl --user -u sonar-daemon -n 200 --no-pager
SONAR_LOG=debug sonar-daemon          # elle, ayrıntılı
```

Sorun bildirirken şunları ekleyin:

```bash
pipewire --version
sonar-cli --json status > durum.json
python -c "from sonar.core.dsp.registry import available_plugins; print(available_plugins())"
```
