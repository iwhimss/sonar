# Faz 36 — Doğrulama, dokümantasyon, temizlik

- [x] `ruff check src/ tests/` ve `pytest -q` yeşil
- [x] Yeni testler: `decode_chatmix`, değer alanı ayrıştırma, `api.stream_setup()`,
      mikrofon gönderi anahtarının `sonar_mic_to_stream` mute'una dönüşmesi
- [x] GUI sıfır QML uyarısıyla açılıyor
- [x] `README.md` / `ARCHITECTURE.md` yayın düzeni bölümü (mikrofon varsayılan yayında)
- [x] `docs/TROUBLESHOOTING.md`: "OBS'te ses iki kez duyuluyor", "OBS'te mikrofon yok"
- [x] **Rapor dosyaları depodan çıkarılsın**: `görsel-bug/`, `spatial audio/`,
      `chatmix.txt`, `script-gui.txt`, `tekerlek.txt` → `git rm --cached` + `.gitignore`
- [x] `.plan/00-overview.md` güncellensin
- [x] Commit + `iwhimss/sonar` `main` push
