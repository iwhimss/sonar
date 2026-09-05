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

## Kanallar hiç görünmüyor, karşılama ekranı açılıyor

Sanal kanallar henüz **kurulmadı**. Sonar ilk açılışta PipeWire'a hiçbir şey yazmaz;
kurulum kullanıcının onayına bağlıdır.

Karşılama akışının son sayfasındaki **Sanal kanalları kur** düğmesine basın. Terminalden:

```bash
sonar-cli install
```

Kurulu olup olmadığını `sonar-cli status` da söyler: kurulu değilse çıktının ilk satırı
bunu yazar.

Bu ekran daha önce kurmuş olmanıza rağmen çıkıyorsa yapılandırma silinmiş olabilir
(`~/.config/sonar/config.toml`). Kurmak zarar vermez; kanallar varsayılan ayarlarla
yeniden oluşur.

---

## Kaldırdım ama sanal cihazlar hâlâ duruyor

`sonar-cli uninstall` (veya **Ayarlar → Sonar'ı kaldır**) graf sürecini durdurur.
Cihazlar hâlâ görünüyorsa:

```bash
pw-dump | grep '"node.name": "sonar_'     # gerçekten kaldı mı
pgrep -af 'pipewire -c'                    # graf süreci ayakta mı
```

Süreç ayakta kalmışsa daemon'ı da durdurun (`systemctl --user stop sonar-daemon` veya
`./scripts/sonar-dev stop`). İnatçı bir kalıntı için son çare:

```bash
systemctl --user restart pipewire
```

Kaldırma **ayarları silmez**; `~/.config/sonar/` yerinde durur ve yeniden kurmak tek
tıktır. Onları da silmek için kaldırma penceresindeki kutucuğu işaretleyin veya
`sonar-cli uninstall --purge` kullanın.

udev kuralı, systemd unit'i ve paketin kendisi root'a veya paket yöneticisine ait; Sonar
onlara dokunmaz, kaldırma sonrası komutlarını yazar.

---

## Arayüz yarı Türkçe yarı İngilizce

Bu bir hata; **Ayarlar → Dil**'den seçtiğiniz dil arayüzün tamamını kapsamalı. Kalan bir
metin varsa hangi ekranda olduğunu bildirin.

Kanal ve cihaz adları bilinçli olarak dilden bağımsızdır: `Sonar Stream Mix` her dilde
aynı kalır ki OBS'te seçili aygıt kaybolmasın. Arayüzdeki "Oyun / Sohbet / Medya"
yalnızca **gösterilen** addır. Kanalı kendiniz adlandırdıysanız sizin adınız her dilde
geçerli olur.

Ham anahtar metni görüyorsanız (`mixer.chatmix` gibi) çeviri eksik demektir; bildirin.

---

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
sudo cp packaging/60-sonar-headset.rules /etc/udev/rules.d/
sudo rm -f /etc/udev/rules.d/99-sonar-headset.rules   # varsa eski kopya
sudo udevadm control --reload && sudo udevadm trigger
```

**Dosya adındaki `60` önemli.** `uaccess` etiketini gören ACL'i systemd'nin
`73-seat-late.rules` dosyası uyguluyor ve udev kuralları ad sırasına göre çalışıyor;
etiketi 73'ten sonra eklemek hiçbir işe yaramıyor. Kural bir dönem `99-` adıyla
dağıtılıyordu ve kurulmasına rağmen `/dev/hidraw*` erişilemez kalıyordu.

Kural `uaccess` etiketi kullanır: erişimi o an oturum açmış kullanıcıya verir, sabit bir
gruba yazmaktan daha dardır. Kurduktan sonra kulaklığı çıkarıp takmak gerekebilir —
ACL cihaz eklendiğinde uygulanıyor.

Teker okunmaya başlayınca mikserdeki slider salt okunur olur ve başlığı "kulaklık tekeri
yönetiyor" der. Elle sürmeye devam etmek isterseniz `config.toml` içinde
`settings.chatmix_source = "software"`.

**Teker ters yönde çalışıyor.** Rapor iki kazanç veriyor ama hangi ucun Game olduğu
raporda yazmıyor. Tek komutla çevirin:

```bash
sonar-cli chatmix --invert on
```

**Kulaklık listede ama teker hiçbir şey yapmıyor.** Kulaklığınız `KNOWN_HEADSETS`
listesinde olmayabilir ya da rapor biçimi farklı olabilir. Raporları kaydedip
(`./scripts/sonar-hid-capture`, tekeri yavaşça uçtan uca çevirin, Ctrl+C) bir issue
açın; biçimi çözmek küçük bir iş.

## OBS'te her şey iki kez duyuluyor

Yayın miksini iki farklı yoldan alıyorsunuz: OBS'in **Masaüstü Sesi** ayarı
`Sonar Stream Mix`'i dinlerken bir yandan da "Ses Girişi Yakalama" kaynağıyla
`Sonar Stream Mix (alternatif giriş)` eklenmiş. İkisi aynı miks.

```bash
sonar-cli doctor        # "Yayın miksi" satırı kimin, hangi yoldan dinlediğini yazar
```

Birini kaldırın. Resmî yol Masaüstü Sesi; bkz. [`OBS.md`](OBS.md).

## OBS'te mikrofonum duyulmuyor

Mikrofon varsayılan olarak yayın miksinin içinde. Kapalıysa yayında sesiniz duyulmaz ve
mikrofon şeridindeki fader yayına hiçbir şey yapmaz — şeritte "yayında değil" yazar.

```bash
sonar-cli mic mic stream on
```

Arayüzden: Master şeridi → dişli → **Yayın kurulumu…** → mikrofonun yanındaki düğme.

Tersi de olur: gönderi açıkken OBS'e ayrı bir mikrofon kaynağı da eklerseniz sesiniz iki
kez gider. O durumda gönderiyi kapatın.

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

## Eklemek istediğim efekt listede yok

"＋ Efekt ekle" penceresi yalnızca **bu makinede kurulu** eklentileri gösteriyor.
Kurulu olmayan bir efekti listelemek, eklendiğinde zinciri düşürürdü.

```bash
sudo pacman -S lsp-plugins-lv2 calf zam-plugins
```

Bazı efektler hedefe göre de eleniyor: AI Gürültü Engelleme yalnızca mikrofon
zincirinde, Uzamsal Ses yalnızca oynatma kanallarında görünür. Ekolayzer zaten
zincirdeyse ikincisi listelenmez — band modeli ve eğri profilde tek.

Hiç eklenmemiş efektler de var (Convolver, çok bandlı kompresör/gate, Auto Gain);
nedenleri `ARCHITECTURE.md`'nin "DSP zinciri" bölümünde.

---

## Profil değiştirince ses kısa süre kesiliyor

Efekt listesi **farklı** iki profil arasında geçiyorsunuz demektir. Zincirin topolojisi
değiştiği için ses grafı yeniden kuruluyor — yaklaşık 200 ms.

Efekt listesi aynı olan profiller arasında geçiş kesintisizdir: EQ eğrisi, filtre
ayarları ve fader'lar canlı yazılıyor. Kesinti istemiyorsanız iki profilde de aynı
efektleri bulundurup birini kapalı bırakın; kapalı bir efekt zincirde durur ve
**bit-şeffaftır** (ölçüldü).

---

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
