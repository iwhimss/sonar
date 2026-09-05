# Faz 42 — Efekt zinciri dinamikleşiyor

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 41
**Çıktı:** şema 7, `EffectSlot`, `add/remove/move_effect`, `sonar-cli effect`

---

## Amaç

Kullanıcının isteği: *"Profil ayarlarına girince sadece ekolayzer ayarı gözüksün. Diğer
ayarları tıpkı EasyEffects programındaki gibi kullanıcı kendisi eklesin. Ekledikçe
gözüksün."*

Bugünkü zincir **sabit topolojiliydi**: `CHAIN_ORDER`'daki yedi aşama her profilde
duruyordu, "kapalı" olanlar bypass'ta bekliyordu ve arayüzde yine de görünüyorlardı. Node
adları da aşama adının kendisiydi (`eq:g_3`), yani aynı efektten ikinci bir örnek mümkün
değildi.

Yeni efektleri eklemeden **önce** taşıyıcıyı değiştirmek gerekiyordu; bu faz onu yapıyor,
efekt kataloğu Faz 43'te geliyor.

---

## Görevler

### Model (şema 7)
- [x] `EffectSlot(kind, slot, enabled, params)` — `slot` graf node adı ve profil içinde
      benzersiz (`comp`, `comp2`)
- [x] `Profile.filters` sözlüğü → `Profile.effects` **sıralı listesi**
- [x] `Profile.state(slot)` — `core.dsp.params`'ın beklediği `FilterState` görünümü;
      EQ'nun bayrağı `profile.eq`'ten okunuyor (eğri ve içe/dışa aktarma orayı kullanıyor)
- [x] `Profile.next_slot_id(kind)` — çakışmayan node adı
- [x] `default_profile()` yalnızca ekolayzerle geliyor
- [x] `config.migrate_profile(raw)`: şema 6 → 7. EQ başta, sonra `CHAIN_ORDER` sırasıyla
      **açık** aşamalar. Kapalılar düşüyor — parametreleri varsayılandaydı, bilgi kaybı yok
- [x] `_normalise_filters` slot kimliklerinin benzersizliğini de onarıyor: elle
      düzenlenmiş bir dosyadaki çakışma `pipewire -c`'nin zinciri hiç kuramaması demekti

### Graf
- [x] `plan_chain(slots)` — sıra artık `CHAIN_ORDER` değil **kullanıcının dizdiği sıra**
- [x] `stage_block` → `effect_block`; node adları slot kimliğinden
- [x] Çok node'lu bloklar (Spatial, Boost) da slottan türüyor: `comp2_l`, `spatial2_mix_l`
- [x] `params.profile_to_params(profile, slots=...)`, `param_key(slot, port)`
- [x] `confgen.generate(cfg, load_profile)` — conf artık **aktif profilin** efekt
      listesini de taşıyor
- [x] `confgen.effect_slots()` hedefe uymayanları süzüyor (mikrofonda Uzamsal Ses,
      oynatmada DeepFilterNet)

### API / arayüzler
- [x] `add_effect`, `remove_effect`, `move_effect`, `list_effects`, `list_effect_kinds`
- [x] `set_filter_enabled` / `set_filter_param` artık **slot kimliği** alıyor; ikisi de
      canlı (bypass yazımı), yalnızca ekle/sil/sırala yapısal
- [x] D-Bus: `AddEffect`, `RemoveEffect`, `MoveEffect`, `ListEffects`, `ListEffectKinds`
      → 62 metot
- [x] `sonar-cli effect list|add|remove|move`
- [x] Köprü: `effectsOf`, `effectKinds`, `addEffect`, `removeEffect`, `moveEffect`;
      `filterOf` slot kimliğiyle çalışıyor ve olmayan slot **uydurulmuyor**

### Yeniden kurulum kararı
- [x] Yeni bir mekanizma **gerekmedi**: `supervisor.reconcile` zaten "üretilen conf metni
      değişti mi" diye bakıyor. Efekt ekle/sil/sırala metni değiştiriyor → yeniden kurulum;
      parametre yazımı değiştirmiyor → canlı. Efekt listesi **aynı** olan iki profil
      arasında geçiş de kesintisiz kalıyor

---

## Ölçüm

Altın `graph.conf` yenilendi. Zincirin tamamını içeren bir profil sağlayıcısıyla üretilen
conf, şema 6'nınkiyle **iki fark dışında birebir aynı**: mikrofon zincirlerinden crossfeed
node'ları düştü. Şema 6'da `_graph` yalnızca DeepFilterNet'i süzüyordu; `PLAYBACK_ONLY_STAGES`
tanımlıydı ama kullanılmıyordu, yani mikrofon zincirlerinde sekiz ölü node duruyordu.

Canlı grafta (kullanıcının gerçek yapılandırması):

```
effect list game            → 0  eq
effect add game comp        → graf yeniden kuruldu, conf'ta name = "comp"
effect add game spatial     → +8 node
effect move game spatial 0  → sıra: spatial, eq, comp
effect remove …             → başlangıç durumuna döndü, doctor temiz
```

Kullanıcının diskteki 15 profili şema 6'da duruyor ve okununca doğru göç ediyor:
`game/cs2 → [('eq', True)]`, `game/Arc Raiders → [('eq', False)]`.
