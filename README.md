# YouTube Arşiv — Çalma Listesi Yedeği ve İndirici

Windows için, **yt-dlp** ve **ffmpeg** tabanlı, grafik arayüzlü (tkinter) taşınabilir
Python uygulaması. YouTube çalma listelerinizi MP3 olarak yedekler/senkronize eder;
tekil video/şarkıları ses, video veya birleşik (mux) olarak indirir.

---

## 1. Gereksinimler

| Bileşen | Gerekli mi? | Açıklama |
|---|---|---|
| Python 3.10+ | Betik olarak çalıştırmak için | python.org'dan indirilebilir |
| yt-dlp.exe | Evet | https://github.com/yt-dlp/yt-dlp/releases → `yt-dlp.exe` |
| ffmpeg.exe | Evet | MP3 dönüşümü + birleştirme için. https://www.gyan.dev/ffmpeg/builds/ → "ffmpeg-release-essentials.zip" içinden `bin\ffmpeg.exe` |

**En kullanışlı yerleşim** — her şeyi tek klasöre koyun:

```
youtube-arsiv\
├── main.py  (+ core\, ui\ …)     ya da youtube-arsiv.exe
├── yt-dlp.exe
├── ffmpeg.exe
└── config.json                   (ilk çalıştırmada oluşur)
```

Bu klasörü olduğu gibi başka bir bilgisayara/portföre kopyaladığınızda ayarlar
ve yollar korunur, uygulama çalışmaya devam eder.

---

## 2. İlk Kurulum

1. Uygulamayı başlatın:
   - **En kolay:** `baslat.bat` dosyasına çift tıklayın (Python kurulu makinelerde).
   - veya komut satırından: `python main.py`
   - veya (Smart App Control kapalı makinelerde): `dist\youtube-arsiv\youtube-arsiv.exe`
   - Betik: `python main.py`
2. İlk açılışta kurulum penceresi gelir:
   - **yt-dlp dosyası**: Gözat ile `yt-dlp.exe`'yi gösterin.
   - **ffmpeg dosyası**: Gözat ile `ffmpeg.exe`'yi gösterin.
   - (Dosyalar uygulama klasöründeyse otomatik algılanır.)
   - **İndirme klasörü**: Varsayılan Müzik klasörünüz (`C:\Users\<ad>\Music`).
3. **Doğrula** ile sürümleri kontrol edin, sonra **Kaydet ve Başla**.
   - Yollar `config.json`'a yazılır; **bir daha sorulmaz**.
   - Bir araç bulunamazsa Ayarlar sekmesinden güncelleyebilirsiniz.

## 3. Çalma Listesi Senkronizasyonu

**Çalma Listeleri** sekmesi:

- **＋ Çalma Listesi Ekle**: Listeyi yapıştırın (`https://www.youtube.com/playlist?list=…`,
  `watch?v=…&list=…` gibi — `list=` sonrası ID otomatik ayıklanır).
- **⟳ Tümünü Senkronize Et**: Kayıtlı tüm listeleri tek tıkla günceller.
- **－ Kaldır**: Listeyi kayıtlardan siler (indirilen dosyalara dokunmaz).

Davranış kuralları:

- Her liste, YouTube'daki **orijinal adıyla** `Müzik\<Liste Adı>\` klasörüne iner.
  Liste YouTube'da yeniden adlandırılırsa klasör de otomatik yeniden adlandırılır;
  takip her zaman **Playlist ID** üzerinden yürür.
- Her klasörde **`indirilenler.txt`** arşivi tutulur: indirilen video ID'leri.
  Senkronizasyonda bu videolar **kesinlikle tekrar indirilmez** (yalnızca yenileri iner).
- Ses standartı: **en iyi ham ses → MP3 320 kbps**, gömülü metadata + kapak resmi.
- Dosya adları: `01 - Şarkı Adı.mp3` (liste sırasına göre numaralı).
- Zaman damgaları korunur: dosyaların oluşturma/değiştirme tarihleri indirme
  sonrası sabitlenir, sonraki senkronlar bunları değiştirmez.

## 4. Tekil Video İndirme

**Tekil İndir** sekmesi (çalma listelerinden bağımsızdır):

1. Bağlantıyı yapıştırın → **Sorgula**. YouTube'un sunduğu **tüm ses ve video
   akışları** (çözünürlük, codec, bitrate, boyut) listelenir.
2. İndirme türünü seçin:
   - **Sadece Ses** — hedef format (MP3, AAC, M4A, FLAC, Opus, orijinal) ve kalite.
   - **Sadece Video** — seçilen çözünürlük/codec, sessiz, dönüştürmesiz.
   - **Ses + Video** — seçtiğiniz ham video + ham ses akışları ffmpeg ile
     **kayıpsız** (yeniden kodlama yok) birleştirilir.
     Kapsayıcı otomatik seçilir: H.264+AAC → MP4, VP9/AV1+Opus → WebM,
     uyumsuzsa MKV.
3. Kaynak akış seçmek **isteğe bağlı**: seçilmezse en iyi kalite kullanılır.
4. İndirilenler `Müzik\Tekil\` klasörüne gider ve oradaki `indirilenler.txt`
   arşivine yazılır → **aynı video ikinci kez indirilmez**.

> Not: YouTube gerçek (kayıpsız) FLAC sunmaz; FLAC seçeneği mevcut sesin
> transkodudur. Ayrıca 8K gibi akışlar video-only'dir; sesle birlikte istenirse
> "Ses + Video" modu kullanılmalıdır.

**Tekrar indirmek isterseniz:** `Müzik\Tekil\indirilenler.txt` içindeki ilgili
video satırını silin (ya da dosyanın tamamını).

## 5. Ayarlar

- yt-dlp / ffmpeg yolları ve indirme klasörü değiştirilebilir, doğrulanabilir.
- `config.json` uygulama klasöründe tutulur → klasör taşınınca ayarlar korunur.

## 6. Sorun Giderme

| Sorun | Çözüm |
|---|---|
| "yt-dlp bulunamadı" | Ayarlar sekmesinden yolu güncelleyin; dosyanın gerçekten var olduğundan emin olun |
| "ffmpeg bulunamadı" | MP3/birleştirme için zorunlu; yolu Ayarlar'dan gösterin |
| İndirme çok yavaş / hata | yt-dlp eski olabilir; yeni sürümle değiştirin |
| Video "indirilemedi" (üye/ölü) | `--ignore-errors` sayesinde diğer videolar etkilenmez; listeden silinmiş olabilir |
| Antivirüs şüphelendi | yt-dlp/ffmpeg resmi kaynaklardan indirildiğinden emin olun |

## 7. Teknik Özet (Geliştiriciler İçin)

```
main.py              giriş noktası
core/
  config.py          config.json + taşınabilir yol çözümleme
  parser.py          URL/ID ayıklama (urlparse + regex)
  runner.py          yt-dlp alt süreç sarmalayıcı + ilerleme parse + iptal
  formats.py         --dump-json format sorgulama
  sync.py            playlist senkronizasyon motoru
  single.py          tekil indirme (ses/video/mux) argüman üretimi
  timestamps.py      creation time sabitleme (ctypes SetFileTime)
ui/
  app.py, setup_dialog.py, sync_tab.py, single_tab.py, settings_tab.py, bridge.py
tests/
  test_parser.py     birim testler
```

Testler: `python -m unittest discover -s tests -v` (proje kökünden)

Tek .exe paketleme (isteğe bağlı):
```
pip install pyinstaller
pyinstaller --noconfirm --onedir --windowed --name youtube-arsiv main.py
```
Sonuç `dist\youtube-arsiv\` içine çıkar; `config.json`, `yt-dlp.exe`,
`ffmpeg.exe` yanına konarak taşınabilir klasör oluşturulur.
