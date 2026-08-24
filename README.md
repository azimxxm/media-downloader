<div align="center">

<img src="assets/icon.png" width="128" alt="Media Downloader">

# Media Downloader

**YouTube va Instagram'dan video, musiqa va rasm yuklab oluvchi macOS ilovasi.**

Internetsiz joyda — mashinada, samolyotda, metroda — ko'rish va tinglash uchun.

[Yuklab olish](#-ornatish) · [Imkoniyatlar](#-imkoniyatlar) · [Arxitektura](#-arxitektura) · [Ishlab chiqish](#-ishlab-chiqish)

</div>

---

## ✨ Imkoniyatlar

| | |
|---|---|
| **YouTube** | Video (4K gacha), Shorts, playlist, MP3 audio, subtitrlar |
| **Instagram** | Post, reel, story · video, audio, rasm, thumbnail |
| **Sifat tanlash** | Har bir rezolyutsiya uchun aniq fayl hajmi ko'rsatiladi |
| **Playlist** | Videolarni belgilab, parallel yuklash (1–8 ta bir vaqtda) |
| **Offline uchun** | MP3'ga avtomatik nom, ijrochi va cover art yoziladi — mashina magnitolasida chiroyli ko'rinadi |
| **QuickTime-mos** | H.264 + AAC, qayta kodlashsiz — Mac va iPhone'da to'g'ridan-to'g'ri ochiladi |

Interfeys o'zbek tilida. Yuklamalar jonli progress, tezlik va qolgan vaqt bilan ko'rsatiladi; istalgan paytda to'xtatib bo'ladi.

---

## 📦 O'rnatish

### Tayyor ilova (tavsiya etiladi)

1. [Releases](../../releases/latest) sahifasidan `MediaDownloader-*-macos-arm64.dmg` ni yuklab oling
2. `.dmg` ni oching va ilovani **Applications** papkasiga sudrab tashlang
3. Birinchi marta ochishda macOS ogohlantiradi (ilova Apple tomonidan notarize qilinmagan):

   **System Settings ▸ Privacy & Security** ▸ pastga tushing ▸ **"Open Anyway"**

   Yoki terminalda bitta buyruq:
   ```bash
   xattr -dr com.apple.quarantine "/Applications/Media Downloader.app"
   ```

### FFmpeg

Video va audioni birlashtirish uchun FFmpeg kerak. Ilova uni topa olmasa, ekranda ko'rsatma chiqadi:

```bash
brew install ffmpeg
```

> Apple Silicon (M1–M4) uchun mo'ljallangan. Intel Mac uchun manbadan yig'ish kerak — [Ishlab chiqish](#-ishlab-chiqish) bo'limiga qarang.

---

## 🏗 Arxitektura

Ilova to'rt qatlamdan iborat. Har biri o'zining bitta vazifasini bajaradi va yuqoridagi qatlam haqida hech narsa bilmaydi.

```
┌──────────────────────────────────────────────────────┐
│  web/          HTML + CSS + vanilla JS               │
│                build step yo'q, npm yo'q, bundler yo'q│
└───────────────────────┬──────────────────────────────┘
                        │  transport.js
        ┌───────────────┴───────────────┐
        │                               │
┌───────▼────────────┐        ┌─────────▼──────────────┐
│ server/bridge.py   │        │ server/http_server.py  │
│ pywebview js_api   │        │ stdlib HTTP + SSE      │
│ → paketlangan .app │        │ → brauzer / dev rejim  │
└───────┬────────────┘        └─────────┬──────────────┘
        └───────────────┬───────────────┘
                        │  server/routes.py  (bitta API shartnomasi)
┌───────────────────────▼──────────────────────────────┐
│  core/         Sof Python — UI framework import       │
│                qilmaydi. yt-dlp, FFmpeg, job queue.   │
└──────────────────────────────────────────────────────┘
```

**Nega shunday?**

- **`core/` UI'dan mustaqil** — HTTP server orqali ham, native bridge orqali ham, testdan ham bir xil ishlatiladi. 102 ta unit test tarmoqqa chiqmasdan o'tadi.
- **Ikkita transport, bitta shartnoma** — `server/routes.py` yagona manba. UI kodi qaysi transport ostida ishlayotganini bilmaydi.
- **Paketlangan ilovada socket yo'q** — `Bridge` pywebview'ning `js_api` kanalidan foydalanadi. macOS 15+ har qanday tinglovchi portga *"find devices on your local network"* ruxsatini so'raydi; socket bo'lmasa — so'rov ham bo'lmaydi.
- **Faqat stdlib HTTP** — FastAPI/uvicorn/websockets o'rniga `http.server` + SSE. PyInstaller'da yashirin import muammolari yo'q.

### Nega Flet emas

Oldingi versiya [Flet](https://flet.dev) da yozilgan edi. Flet ichida to'liq Flutter engine bor, va `flet pack` bilan macOS `.app` yig'ish barqaror ishlamasdi.

| | Flet | Hozirgi |
|---|---|---|
| `.app` hajmi | ~200 MB | **32 MB** |
| `.dmg` hajmi | — | **18 MB** |
| Runtime dependency | Flutter engine + Flet client binary | tizimning WKWebView'i |
| UI qatlami | Python'da Flutter widget'lari | HTML + CSS |

---

## 💽 Disk yozuvi haqida

Video va audio alohida yuklanib, so'ng FFmpeg bilan birlashtiriladi — bu yakuniy fayl hajmining **2 barobari** diskka yoziladi degani (masalan 88 MB video uchun 176 MB).

Buni 1x ga tushirish mumkin (`external_downloader: ffmpeg` — ffmpeg ikkala oqimni to'g'ridan-to'g'ri mux qiladi), lekin o'lchov shuni ko'rsatdi:

| Usul | Diskka yozuv | Vaqt |
|---|---|---|
| Hozirgi (alohida + merge) | 176 MB (2.0x) | **5.4 s** |
| `external_downloader: ffmpeg` | 87 MB (1.0x) | **212 s** |

ffmpeg'ning HTTP reader'i YouTube'ning parallel-fragment optimizatsiyasini bilmaydi va throttle'ga tushadi. 88 MB yozuv NVMe SSD'da ~0.06 s turadi — 3.5 daqiqa kutishga arzimaydi. Shuning uchun 2x default bo'lib qoldi.

---

## 🛠 Ishlab chiqish

```bash
git clone https://github.com/azimxxm/media-downloader.git
cd media-downloader

python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
brew install ffmpeg
```

### Ishga tushirish

```bash
.venv/bin/python app.py             # native oyna (WKWebView)
.venv/bin/python app.py --browser   # brauzerda — UI'ni tahrirlab reload qilish oson
.venv/bin/python app.py --hidden    # oynasiz (test uchun)
```

`web/` ichidagi fayllar oddiy HTML/CSS/JS — build qadami yo'q, saqlab reload qilsangiz bo'ldi.

### Testlar

```bash
.venv/bin/python -m pytest tests/ -q          # 102 ta unit test, tarmoqsiz, ~0.5 s
.venv/bin/python packaging/ui_smoke.py        # UI end-to-end (yashirin oynada)
```

`ui_smoke.py` haqiqiy pywebview oynasini shipping ilovasidagi bridge orqali boshqaradi: bootstrap → tahlil → yuklash → job tugashi, plus 560/780/1100px da responsive tekshiruv. `--visible` bilan oynani ko'rsatish mumkin.

### Yig'ish

```bash
./packaging/build_macos.sh                    # .app → ad-hoc imzo → .dmg
./packaging/build_macos.sh --with-ffmpeg      # FFmpeg'ni bundle ichiga qo'shib

SIGN_IDENTITY="Developer ID Application: Ism (TEAMID)" \
  ./packaging/build_macos.sh                  # notarize qilinadigan imzo bilan
```

Natija `dist/` ichida. Skript imzoni tekshiradi va `.dmg` yasashdan oldin bundle'ni haqiqatan ishga tushirib ko'radi.

Ikonani qayta yasash: `.venv/bin/python packaging/make_icon.py`

### Loyiha tuzilishi

```
app.py                    kirish nuqtasi — native yoki brauzer rejimini tanlaydi
core/                     sof Python (UI framework import qilmaydi)
  ├── media.py            metadata tahlili, sifat va subtitr variantlari
  ├── downloader.py       yt-dlp opsiyalari, progress, fayl yo'lini aniqlash
  ├── jobs.py             job navbati, parallel limit, bekor qilish
  ├── ffmpeg.py           FFmpeg'ni topish (bundle → PATH → Homebrew)
  ├── events.py           event bus
  └── settings.py         sozlamalarni saqlash
server/
  ├── api.py              so'rov handlerlari
  ├── routes.py           yagona API shartnomasi
  ├── bridge.py           native transport (pywebview js_api)
  └── http_server.py      stdlib HTTP + SSE transport
web/                      index.html · styles.css · app.js · transport.js
packaging/                PyInstaller spec, build skripti, ikona, UI smoke test
tests/                    pytest
```

---

## 🔒 Xavfsizlik

- Brauzer rejimidagi HTTP server faqat `127.0.0.1` ga bog'lanadi va tasodifiy tokenni talab qiladi; `Host` sarlavhasi DNS rebinding'ga qarshi tekshiriladi.
- Yuklash uchun ishlatiladigan metadata **serverdagi keshdan** olinadi, sahifa yuborgan ma'lumotdan emas.
- Barcha media matni `textContent` bilan chiziladi — `innerHTML` bilan emas.
- Hech qanday telemetriya, hisob, tarmoq chaqiruvi yo'q — faqat siz so'ragan yuklash.

---

## 📄 Litsenziya

MIT. Yuklab olingan kontentga bo'lgan mualliflik huquqlari o'z egalariga tegishli — ilovadan faqat siz huquqiga ega bo'lgan yoki shaxsiy offline foydalanish uchun ruxsat etilgan kontent bilan foydalaning.

Ichida ishlatilgan: [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense) · [pywebview](https://pywebview.flowrl.com) (BSD) · [FFmpeg](https://ffmpeg.org) (LGPL/GPL, alohida o'rnatiladi).
