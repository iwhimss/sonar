# Faz 36 — Doğrulama, dokümantasyon, temizlik

- [ ] `ruff check src/ tests/` ve `pytest -q` yeşil
- [ ] Yeni testler: `decode_chatmix`, değer alanı ayrıştırma, `api.stream_setup()`,
      mikrofon gönderi anahtarının `sonar_mic_to_stream` mute'una dönüşmesi
- [ ] GUI sıfır QML uyarısıyla açılıyor
- [ ] `README.md` / `ARCHITECTURE.md` yayın düzeni bölümü (mikrofon varsayılan yayında)
- [ ] `docs/TROUBLESHOOTING.md`: "OBS'te ses iki kez duyuluyor", "OBS'te mikrofon yok"
- [ ] **Rapor dosyaları depodan çıkarılsın**: `görsel-bug/`, `spatial audio/`,
      `chatmix.txt`, `script-gui.txt`, `tekerlek.txt` → `git rm --cached` + `.gitignore`
- [ ] `.plan/00-overview.md` güncellensin
- [ ] Commit + `iwhimss/sonar` `main` push
