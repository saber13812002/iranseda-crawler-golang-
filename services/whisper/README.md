# 🎧 IranSeda Whisper Service (GPU)

سرویس زیرنویس‌سازی روی سرور GPU (سرور 53) — دانلود، ترنسکریپت با Whisper و برگرداندن SRT به سرور 52.

## معماری

```
سرور 53 (GPU H100)                         سرور 52 (بدون GPU)
┌──────────────────────────┐               ┌──────────────────────────┐
│ whisper-api  (port 9500) │               │ MySQL radio (3308)       │
│   /v1/audio/transcriptions│   LAN ssh     │  radio_program_sessions  │
│   /queue /health         │──────────────▶│  status column (queue)   │
│ whisper-worker  (GPU)    │  scp SRT      │  downloads/*.srt         │
│   DB queue → download →  │               └──────────────────────────┘
│   faster-whisper → SRT   │
└──────────────────────────┘
```

- **صف = دیتابیس.** هر session یک ستون `status` داره:
  `pending_download → downloaded → pending_transcribe → transcribing → subtitled`
  (شکست: `failed` → بعد از `MAX_ATTEMPTS`: `failed_permanent`)
- **دانلود روی 53** انجام می‌شه (نه 52) — فقط SRT نهایی (چند ده کیلوبایت) برمی‌گرده، نه MP4.
- **GPU:** هر دو کانتینر (api + worker) روی یک GPU (`CUDA_VISIBLE_DEVICES`) قفل‌نصب‌نموده‌اند.

## فایل‌ها

| فایل | نقش |
|---|---|
| `common.py` | دانلود میدیا، ترنسکریپت faster-whisper، اتصال DB |
| `api.py` | FastAPI: `POST /v1/audio/transcriptions` (OpenAI-compatible، فایل یا `?url=`)، `GET /queue`، `POST /queue/result` |
| `worker.py` | حلقه‌ی صف: claim → دانلود → ترنسکریپت → scp SRT به 52 → آپدیت DB |
| `requirements.txt` | fastapi، uvicorn، faster-whisper، pymysql |
| `../../Dockerfile.whisper` | بیلد روی پایه‌ی CUDA 12.4 |
| `../../docker-compose.whisper.yml` | سرویس‌های api + worker |

## اجرا (روی سرور 53)

```bash
cd ~/saberprojects/iranseda-crawler-golang-
# GPU با VRAM آزاد را انتخاب کن (نمایه)؛ پیش‌فرض 1
WHISPER_GPU=1 docker compose -f docker-compose.whisper.yml up -d --build

docker compose -f docker-compose.whisper.yml logs -f whisper-api
docker compose -f docker-compose.whisper.yml logs -f whisper-worker
```

## تست

```bash
# health
curl http://<ip53>:9500/health

# ترنسکریپت یک فایل
curl -X POST "http://<ip53>:9500/v1/audio/transcriptions?url=<session_link>" \
  -H "Authorization: Bearer <apikey>"

# یا آپلود فایل محلی
curl -X POST "http://<ip53>:9500/v1/audio/transcriptions" \
  -F "file=@audio.mp4" -F "language=fa"
```

## متغیرهای محیطی (worker)

| env | پیش‌فرض | توضیح |
|---|---|---|
| `WHISPER_MODEL` | `large-v3-turbo` | مدل |
| `WHISPER_LANGUAGE` | `fa` | زبان |
| `BATCH_SIZE` | `1` | چند session در هر دور |
| `KEEP_MP4` | `0` | `1` = MP4 را هم به 52 بفرست (وگرنه حذف شود) |
| `MAX_ATTEMPTS` | `3` | تعداد تلاش قبل از پارک کردن |
| `SSH_TARGET` | `saber@172.20.1.52` | مقصد scp |
| `REMOTE_DOWNLOADS` | `.../iranseda/downloads` | پوشه‌ی سرتای SRT روی 52 |
| `SSH_KEY_PATH` | `/app/keys/id_ed25519` | کلید SSH داخل کانتینر |

## مقیاس‌پذیری آینده (چند سرور/GPU)

- **چند GPU روی یک سرور:** instance های worker را زیاد کن و هر کدام به GPU متفاوت بده:
  ```yaml
  whisper-worker-2:
    extends: whisper-worker   # یا کپی
    environment: { CUDA_VISIBLE_DEVICES: "0" }
  ```
- **چند سرور:** همه‌ی workerها از **همان DB** (52:3308) claim می‌کنند؛ ستون `status='transcribing'`
  نقش قفل را بازی می‌کند، پس دو worker هرگز یک session را دوبار نمی‌گیرند. کافی است هر سرور GPU
  کانتینر worker خودش را با `DB_HOST=172.20.1.52` بالا بیاورد و کلید SSH دسترسی به 52 داشته باشد.
- **سرعت:** `large-v3-turbo` روی H100 ≈ 5–10× realtime → هر فایل 30 دقیقه‌ای در ~3–6 دقیقه.
