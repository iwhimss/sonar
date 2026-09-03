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

**İlk komut:**

```bash
sonar-cli doctor
```

Beklenen ve gerçek gönderi bağlantılarını karşılaştırır, doğmamış node'ları,
yönlendirilmemiş akışları ve çakışan ses işleyicilerini tek çıktıda listeler. Çıkış
kodu 0 = sorun yok.

Temiz çıkıyorsa sırayla:

1. Uygulama doğru kanalda mı? `sonar-cli status` → "ÇALAN UYGULAMALAR".
   Değilse `sonar-cli move <id> <kanal>`.
2. Kanal hangi çıkışa gidiyor? `sonar-cli output list` — Game'i yanlışlıkla başka bir
   cihaza göndermiş olabilirsiniz. `sonar-cli send game personal` geri alır.
3. Fader kapalı olabilir: `sonar-cli volume game output 100`.
4. Mute açık olabilir: `sonar-cli mute game output off`.
5. Çıkış bus'ının cihazı doğru mu? `sonar-cli status` alt kısmında her bus'ın hedefi
   yazıyor; `(sistem varsayılanı)` diyorsa WirePlumber seçiyor demektir.

### "X kanalı çıkışa bağlanamadı" uyarısı

Kanal çıkışları bus'lara `pw-link` ile bağlanıyor ve daemon bunu sürekli uzlaştırıyor:
grafta node değiştikçe ve iki saniyede bir sağlık yoklamasında. Üst üste üç tur
onaramazsa bu uyarı çıkar. Ölçüldü: elle koparılan bir bağlantı 3 saniye içinde geri
kuruluyor, yani uyarıyı görüyorsanız gerçekten kalıcı bir sorun var.

```bash
sonar-cli doctor          # hangi bağlantı eksik
sonar-cli reload          # grafı baştan kur
```

Not: eski sürümlerde bu bağlantı tek seferlik kuruluyordu ve tutmazsa kanal **sessizce**
susuyordu — hiçbir uyarı yoktu.

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

## Cihaz değiştirince müzik duruyor

Artık durmamalı. Çıkış cihazı ve mikrofon kaynağı conf'a yazılmıyor; hedef
`pw-metadata target.object` ile canlı veriliyor, yani graf yeniden kurulmuyor.

Hâlâ duruyorsa `sonar-cli doctor` çalıştırın: `sonar_<bus>_out` node'u grafta yoksa
yeniden inşa gerçekten olmuştur ve başka bir sebep vardır.

Yeniden inşa gerektiren işlemler yalnızca şunlar: kanal/çıkış ekleme-silme, band sayısı,
kanal başına OBS kaynağı ve Spatial Audio.

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

## Discord mikrofonu Sonar'ı kullanmıyor

Uygulamalar hem çıkış hem giriş şeridinde görünür; ikisi ayrı ayrı yönlendirilir.

```bash
sonar-cli status                            # "MİKROFON KULLANANLAR" bölümü
sonar-cli move <id> mic                     # o akışı Sonar mikrofonuna taşı
sonar-cli route Discord mic --direction in  # bundan sonra hep oraya gitsin
```

`--direction in` şart: yönsüz bir kural uygulamanın **sesini** yönlendirir, mikrofonunu
değil. `sonar-cli rules` çıktısında `→ SES` ve `← MİK` sütunu hangisi olduğunu söyler.

Masaüstü sesini yakalayan uygulamalar (cava, OBS'in "Masaüstü Sesi" kaynağı) bu listede
görünmez ve yönlendirilmez — mikrofon kullanıcısı değiller.

## Spatial Audio açınca CPU fırladı

Beklenen. Bir HRTF konvolveri ses akan bir kanalda tek çekirdeğin ~%17'sini yiyor.
Kapalıyken node grafta hiç bulunmadığı için maliyeti **sıfır** — bu yüzden açıp kapatmak
grafı yeniden kuruyor (~200 ms sessizlik), diğer efektlerin aksine.

Birden çok kanalda birden açmayın; genelde yalnızca oyun kanalında anlamlı.

## Kulaklığın ChatMix tekeri çalışmıyor

`/dev/hidraw*` düğümleri varsayılan olarak `root`'a kapalı; Sonar cihazdan tek rapor bile
okuyamıyor. Erişim için tek seferlik:

```bash
sudo cp packaging/99-sonar-headset.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

Kural `uaccess` etiketi kullanır: erişimi o an oturum açmış kullanıcıya verir, sabit bir
gruba yazmaktan daha dardır.

Kural kurulduktan sonra rapor biçiminin çözülmesi gerekiyor (cihaza özel):

```bash
./scripts/sonar-hid-capture     # tekeri yavaşça uçtan uca çevir, Ctrl+C
```

Teker okunmaya başlayınca mikserdeki slider salt okunur olur ve başlığı "kulaklık tekeri
yönetiyor" der. Elle sürmeye devam etmek isterseniz `config.toml` içinde
`settings.chatmix_source = "software"`.

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
