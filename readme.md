# 📻 IranSeda Crawler & Archive System

سیستم خودکار خزش، دانلود، تولید زیرنویس و انتشار برنامه‌های رادیو ایران‌صدا

**🌐 [مشاهده وب‌سایت زنده / View Live Website](https://saber13812002.github.io/iranseda-crawler-golang-/index.html)**

---

## 📋 فهرست مطالب / Table of Contents

- [نمای کلی پروژه](#نمای-کلی-پروژه)
- [معماری و گردش کار](#معماری-و-گردش-کار)
- [نصب و راه‌اندازی](#نصب-و-راه‌اندازی)
- [مستندات جزئیات](#مستندات-جزئیات)
- [ساختار پروژه](#ساختار-پروژه)
- [تکنولوژی‌ها](#تکنولوژی‌ها)
- [نکات مهم](#نکات-مهم)

---

## 🎯 نمای کلی پروژه

این پروژه یک سیستم خودکار کامل برای:
1. **خزش برنامه‌ها**: شناسایی و ثبت برنامه‌های رادیو ایران‌صدا از روی فایل متنی
2. **مدیریت زمان‌بندی**: تشخیص تغییرات زمان پخش و deprecate کردن نسخه‌های قدیمی
3. **دانلود فایل‌ها**: دریافت خودکار فایل‌های صوتی MP3
4. **تولید زیرنویس**: ساخت خودکار فایل‌های SRT با استفاده از ASR
5. **پاک‌سازی متن**: تبدیل زیرنویس‌ها به متن کامل و تمیز
6. **همگام‌سازی Git**: پوش خودکار تغییرات به GitHub
7. **تولید وب‌سایت**: ساخت صفحات HTML برای نمایش در GitHub Pages

**⏰ اجرای خودکار**: تمام مراحل از طریق n8n هر 2 ساعت اجرا می‌شوند و بیش از 6 ماه است که به صورت پایدار کار می‌کنند.

---

## 🔄 معماری و گردش کار

```
┌─────────────────────────────────────────────────────────────┐
│  مرحله 0: به‌روزرسانی زمان‌بندی برنامه‌ها                  │
│  📝 crawler/crawler.py + scripts/backfill_program_times.py  │
│  ⏰ هر 45 دقیقه                                              │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  مرحله 1: اسکن و ثبت برنامه‌ها                              │
│  🐍 crawler/crawler.py (Python)                             │
│  🔍 scan.go (Go)                                             │
│  ⏰ هر 2 ساعت                                                │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  مرحله 2: دانلود فایل‌های صوتی                             │
│  🐹 download_db.go                                          │
│  ⏰ هر 2 ساعت                                                │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  مرحله 3: تولید زیرنویس (SRT)                              │
│  🔧 ابزار خارجی: Subtitle-Generator                        │
│  ⏰ هر 5-6 ساعت                                              │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  مرحله 4: پاک‌سازی و تبدیل به متن کامل                     │
│  🧹 srt_cleaner + convert_srt_to_txt.py                     │
│  ⏰ هر 2 ساعت                                                │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  مرحله 5: همگام‌سازی Git                                    │
│  🔄 git_push.json (n8n)                                      │
│  ⏰ هر 90 دقیقه                                               │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  مرحله 6: تولید صفحات وب                                    │
│  🐍 generate_site.py                                         │
│  ⏰ هر 2 ساعت                                                │
└─────────────────────────────────────────────────────────────┘
```

### 📊 جریان داده

1. **ورودی**: فایل `crawler/crawl_links.txt` شامل لینک‌های صفحات برنامه‌ها
2. **دیتابیس**: MySQL/MariaDB با جداول `radio_programs` و `radio_program_sessions`
3. **فایل‌ها**: پوشه `downloads/` شامل MP3، SRT و TXT
4. **خروجی**: پوشه `docs/` شامل صفحات HTML برای GitHub Pages

---

## 🚀 نصب و راه‌اندازی

### پیش‌نیازها

- **Go** 1.23+ 
- **Python** 3.8+
- **MySQL/MariaDB** 5.7+
- **Git**
- **n8n** (برای اجرای خودکار)

### مراحل نصب

#### 1. کلون پروژه

```bash
git clone https://github.com/saber13812002/iranseda-crawler-golang-.git
cd iranseda-crawler-golang-
```

#### 2. نصب وابستگی‌های Go

```bash
go mod download
```

#### 3. نصب وابستگی‌های Python

```bash
# برای crawler
cd crawler
python3 -m venv venv
source venv/bin/activate  # در Windows: venv\Scripts\activate
pip install -r requirements.txt

# برای generate_site
cd ..
python3 -m venv venv
source venv/bin/activate
pip install pymysql python-dotenv
```

#### 4. تنظیم دیتابیس

```sql
CREATE DATABASE radio CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
CREATE USER 'n8nuser'@'%' IDENTIFIED BY 'StrongPassword123!';
GRANT ALL PRIVILEGES ON radio.* TO 'n8nuser'@'%';
FLUSH PRIVILEGES;
```

اجرای اسکریپت‌های SQL:
```bash
mysql -u n8nuser -p radio < radio.sql
mysql -u n8nuser -p radio < radio_programs.sql
```

#### 5. تنظیم فایل `.env`

کپی کردن یکی از فایل‌های نمونه:
```bash
cp env.local.example .env
```

ویرایش `.env`:
```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=n8nuser
DB_PASS=StrongPassword123!
DB_NAME=radio
MYSQL_CONN=n8nuser:StrongPassword123!@tcp(localhost:3306)/radio

GITHUB_USER=saber13812002
GITHUB_REPO=iranseda-crawler-golang-
GITHUB_BRANCH=download-db

ENVIRONMENT=local
```

#### 6. تنظیم n8n Workflows

وارد کردن workflowهای JSON از پوشه `n8n_workflows/` به n8n و تنظیم:
- مسیرهای اجرا
- زمان‌بندی‌ها
- متغیرهای محیطی

---

## 📚 مستندات جزئیات

برای جزئیات هر مرحله، به مستندات زیر مراجعه کنید:

### مستندات اصلی

- **[📋 مستندات گردش کار / Workflow Documentation](docs/workflows/)** - مستندات کامل هر مرحله
  - [مرحله 0: به‌روزرسانی زمان‌بندی](docs/workflows/00_program_schedule_refresh.md)
  - [مرحله 1: اسکن و ثبت](docs/workflows/01_scan_and_ingest.md)
  - [مرحله 2: دانلود](docs/workflows/02_download_pipeline.md)
  - [مرحله 3: تولید زیرنویس](docs/workflows/03_subtitle_generation.md)
  - [مرحله 4: پاک‌سازی متن](docs/workflows/04_full_text_cleanup.md)
  - [مرحله 5: همگام‌سازی Git](docs/workflows/05_git_sync.md)
  - [مرحله 6: تولید سایت](docs/workflows/06_site_generation.md)

### مستندات کامپوننت‌ها

- **[🕷️ Crawler (Python)](docs/README_CRAWLER.md)** - خزش و ثبت برنامه‌ها
- **[🔍 Scanner (Go)](docs/README_SCANNER.md)** - اسکن لینک‌های قسمت‌ها
- **[⬇️ Downloader (Go)](docs/README_DOWNLOADER.md)** - دانلود فایل‌های صوتی
- **[📝 Subtitle Generation](docs/README_SUBTITLES.md)** - تولید زیرنویس خودکار
- **[🧹 Full Text Cleanup](docs/README_CLEANUP.md)** - پاک‌سازی و تبدیل متن
- **[🔄 Git Sync](docs/README_GIT_SYNC.md)** - همگام‌سازی با GitHub
- **[🌐 Site Generator](docs/README_SITE_GENERATOR.md)** - تولید صفحات وب
- **[🛠️ Scripts & Utilities](docs/README_SCRIPTS.md)** - اسکریپت‌های کمکی

---

## 📁 ساختار پروژه

```
iranseda-crawler-golang-/
├── crawler/                    # خزش برنامه‌ها (Python)
│   ├── crawler.py             # اسکریپت اصلی خزش
│   ├── crawl_links.txt        # لیست لینک‌های برنامه‌ها
│   └── requirements.txt       # وابستگی‌های Python
│
├── downloads/                  # فایل‌های دانلود شده
│   ├── *.mp3                  # فایل‌های صوتی
│   ├── *.srt                  # زیرنویس‌های خام
│   ├── *.txt                  # متن‌های تبدیل شده
│   └── cleaned/               # فایل‌های پاک‌سازی شده
│
├── docs/                       # خروجی صفحات وب
│   ├── index.html             # صفحه اصلی
│   └── programs/              # صفحات برنامه‌ها
│
├── scripts/                    # اسکریپت‌های کمکی
│   ├── backfill_program_times.py
│   ├── notify_telegram.py
│   └── ...
│
├── n8n_workflows/              # فایل‌های workflow n8n
│   ├── crawl_go_copy.json
│   ├── scan_go_copy.json
│   ├── download_db_go.json
│   └── ...
│
├── web-viewer/                 # نمایشگر وب (Go)
│   ├── main.go
│   └── templates/
│
├── scan.go                     # اسکن لینک‌ها (Go)
├── download_db.go             # دانلود از دیتابیس (Go)
├── generate_site.py            # تولید صفحات وب (Python)
├── convert_srt_to_txt.py      # تبدیل SRT به TXT
├── config.py                   # مدیریت تنظیمات
├── run_generator.py            # اجرای generator با محیط‌های مختلف
│
├── radio.sql                   # اسکریپت ساخت دیتابیس
├── radio_programs.sql          # ساختار جدول برنامه‌ها
├── migrations/                 # مایگریشن‌های دیتابیس
│
└── docs/workflows/             # مستندات گردش کار
    ├── 00_program_schedule_refresh.md
    ├── 01_scan_and_ingest.md
    └── ...
```

---

## 🛠️ تکنولوژی‌ها

### Backend
- **Go 1.23+** - اسکن و دانلود
- **Python 3.8+** - خزش و تولید سایت
- **MySQL/MariaDB** - ذخیره‌سازی داده‌ها

### Tools & Libraries
- **BeautifulSoup4** - پارس HTML
- **goquery** - پارس HTML در Go
- **pymysql** - اتصال به MySQL
- **python-dotenv** - مدیریت متغیرهای محیطی

### Infrastructure
- **n8n** - خودکارسازی و زمان‌بندی
- **GitHub Pages** - میزبانی وب‌سایت
- **Git** - کنترل نسخه

### External Services
- **Subtitle-Generator** - تولید زیرنویس با ASR
- **srt_cleaner** - پاک‌سازی زیرنویس‌ها

---

## ⚠️ نکات مهم

### مدیریت Legacy Programs

هنگامی که زمان پخش یک برنامه تغییر می‌کند:
- رکورد قدیمی با `is_legacy=1` و `legacy_expires_at=NOW()` علامت‌گذاری می‌شود
- رکورد جدید با همان URL اما `is_legacy=0` ایجاد می‌شود
- هر دو رکورد در دیتابیس نگه‌داری می‌شوند برای تاریخچه

### فایل‌های Deprecated

- `download.go` - نسخه قدیمی دانلود (بدون دیتابیس)
- `seek.go` - اسکریپت تست/دیباگ
- `suball.json` - workflow قدیمی زیرنویس

### تغییرات مهم

- **2025-11-19**: اضافه شدن ستون‌های `is_legacy` و `legacy_expires_at` به `radio_programs`
- استفاده از `download_db.go` به جای `download.go` برای مدیریت بهتر وضعیت دانلود

### اجرای دستی

```bash
# خزش برنامه‌ها
cd crawler && python crawler.py

# اسکن لینک‌ها
go run scan.go

# دانلود فایل‌ها
go run download_db.go

# تولید سایت
python run_generator.py --env local
```

---

## 🌙 Boost — استفاده از ظرفیت خالی GPU (شب / تعطیلات)

یک کنترلر کوچک و امن درون‌پروسسی (بدون سرویس جدید) که تصمیم می‌گیرد چند ویرکر موازی `run-all` برای سوختن بک‌لاگ LLM (به‌طور پیش‌فرض `correct_subtitles`) روی GPUهای خالی در **شب** یا **روزهای تعطیل** بچرخاند — بدون اینکه ترافیک تعاملی مدل‌ها (کاربرهای زنده) یا کارهای هم‌قرار روی همان H100ها (embeddings / finetune / whisper) را گرسنه کند.

**سلسله‌مراتب ایمنی:** ترافیک تعاملی همیشه برنده است. کنترلر بار زنده را از Prometheus سرور 52 (متریک‌های vllm / sglang / DCGM) می‌خواند، سطح بار (LOW/MEDIUM/HIGH/CRITICAL) را حساب می‌کند و سقف ویرکرها را بسته به آن کم می‌کند:

| سطح | سقف ویرکرها |
|-----|-------------|
| LOW | `boost_workers` |
| MEDIUM | ۲ |
| HIGH | ۱ |
| CRITICAL | ۰ |

هر‌گاه عقب‌نشینی یا پرش رخ می‌دهد، **دلیل** آن لاگ می‌شود (`scripts/logs/boost.log`) و در داشبورد نمایش داده می‌شود. اگر بالای سقفِ کاربر تعاملی باشد، از مدل استفاده نمی‌کند؛ اگر token/queue/استفاده GPU بالا باشد، عقب می‌نشیند.

**حالت‌ها:**
- `NORMAL` — `normal_workers` ویرکر، ۲۴/۷ (سوزاندن پایه‌ی بک‌لاگ)
- `BOOST` — تا `boost_workers` ویرکر، فقط داخل پنجره‌ی شب/تعطیل و با تروگل خودکار
- `PAUSED` — ۰ ویرکر (kill switch). همه‌چیزِ دیگر دست‌نخورده می‌ماند.

> **پیش‌فرض `PAUSED` است** — تا زمانی که صریحاً شروع نشود، GPU کار بک‌لاگ نمی‌کند.

**CLI (روی سرور 53):**
```bash
scripts/iranseda-boost status                 # حالت / ویرکر / بار / دلیل
scripts/iranseda-boost start                  # -> NORMAL (شروع)
scripts/iranseda-boost normal                 # -> NORMAL
scripts/iranseda-boost pause                  # -> PAUSED (قابل بازگشت)
scripts/iranseda-boost emergency_stop         # PAUSE + کشتن ویرکرها همین حالا
scripts/iranseda-boost set JOB=correct_subtitles MODEL=qwen38-nothinking \
    NORMAL_WORKERS=2 BOOST_WORKERS=4 START=22:00 END=08:00 \
    WEEKEND_DAYS=THURSDAY,FRIDAY
```

**Kill switch فوری:**
```bash
./scripts/stop-background.sh              # pause boost + کشتن ویرکرهای run-all
./scripts/stop-background.sh --procs      # فقط کشتن ویرکرها (بدون آپی)
```
این اسکریپت **فقط** ویرکرهای `llm_jobs.py run-all` را می‌کشد؛ سرورهای مدل (qwen38/sglang)، whisper، LiteLLM و خود داشبورد دست‌نخورده می‌مانند.

**تنظیمات:** از داشبورد (بخش «🌙 Boost») یا CLI یا متغیرهای محیطی:
`IRANSEDA_BOOST_ENABLED`, `IRANSEDA_BOOST_START`, `IRANSEDA_BOOST_END`, `IRANSEDA_NORMAL_WORKERS`, `IRANSEDA_BOOST_WORKERS`, `IRANSEDA_HOLIDAY_BOOST`, `IRANSEDA_WEEKEND_DAYS`.
State در `dashboard_state.json["boost"]` است (منبع واحد حقیقت).

**مدل انتخاب‌شده:** `qwen38-nothinking` — در مقایسه‌ی کیفیت، `qwen38` (thinking) در max_tokens پایین فقط reasoning برمی‌گرداند و `qwen38-sglang` کلوگسته است؛ `qwen38-nothinking` فارسیِ تمیز و سریع (~۶ ثانیه) می‌دهد. (جزئیات: `docs/prompts/005-holiday-night-boost.md`)

**مراقبت (Grafana):** تابلوی `iranseda-pipeline` پنل‌های `iranseda_boost_*` را نشان می‌دهد (حالت، ویرکرهای فعال/هدف، سطح بار، تروگل/سکپ، بک‌لاگ، درخواست‌های مدل در حال اجرا/در انتظار، استفاده GPU، token sglang).

**متغیرهای محافظ (guard):** `user_request_cap` (سقف درخواست تعاملی)، `sglang_token_cap`، `vllm_waiting_cap`، `queue_cap`، `dcgm_util_cap` — همه از داشبورد/CLI قابل تنظیم‌اند.

---

## 🧩 مراحل خط لوله / برش زمانی / پذیرش برنامه / پرکردن ماهانه

چهار قابلیت مدیریتی که خط لولای LLM را **پویا** می‌کنند — همه از صفحه‌ی ادمین (داشبورد :8990) و بدون تغییر کد:

### 📋 مرحله‌های خط لوله (Registry — پویا)
فازهای پردازش دیگر یک ثابتِ ۴تایی در کد نیستند؛ همه از یک جدول `pipeline_steps` خوانده می‌شوند. هر مرحله = یک ردیف `(slug، input_ref، model، پرامپت، output_suffix، output_kind)` و `job_type` در جدول `llm_output` همان `slug` است. بنابراین **تعریف یک فازِ تازه** (فایل ورودی + مدل + پرامپتِ مادر → یک **فیلدِ تازه** به‌ازای هر فایل) فقط یک ردیف است و از سر تا پا کار می‌کند: منوی داشبورد → پرامپت → اجرا → فیلدِ تازه → ردیف `llm_output` → لینک در سایت → ستون تازه در جدول Dataset — **بدون هیچ خط کد**. `known_step_slugs()` فالبکِ ایستا دارد؛ اگر ردیفی گم باشد، شاردِ در حال اجرا نمی‌ریزد.

### 🎞️ برش بلاک زمانی (Time-block crop)
یک اسلوت پخش ~۳۰ دقیقه‌ای است اما برنامه (مثلاً) ۲۰ دقیقه است و ممکن است در **آغاز/میانه/پایان** اسلوت پخش شده باشد. برای هر برنامه: `crop_offset` (شروع داخلِ اسلوت) + `time` (مدت) + `crop_enabled` روی `radio_programs`. `crop_program` فقط بلاک‌هایی را نگه می‌دارد که **نیم‌مرکز** زمانشان در `[offset, offset+dur]` باشد، شماره را ۱-مبنا می‌کند، **زمانِ اصلی را حفظ** می‌کند، و یک **فیلدِ تازه** می‌سازد: `cleaned/<stem>.program.srt` + `.program.txt` — SRT اصلی دست‌نخورده می‌ماند. مراحلِ پایین‌دست (خلاصه / تصحیح متن / تصحیح SRT) از برش می‌خوانند و اگر برش خاموش باشد، **بازگشت به متن کامل**. کاملاً **قابلِ اجرا مجدد** است (تغییر offset/dur در اجرا بعد اعمال می‌شود).

### 📊 Dataset
`GET /api/dataset` خروجی‌های `llm_output` را به‌ازای هر session می‌چیند (ستون‌ها = مرحله‌ها، سلول‌ها = مدلی که ساخته) و به برنامه + session اصلی برمی‌گردد. مرحله‌های تازه **خودکار** ستون‌های تازه می‌شوند. (محدود: جدیدترین N session که اصلاً خروجیِ مرحله‌ای دارند.)

### 🚀 پذیرش و تست برنامه (Onboarding / verify)
فهرست `radio_programs` + ویرایشگرِ برشِ هر برنامه (offset/مدت/فعال) + **تست ۱۰تایی** (`program_block` → `summary` → `correct_text` روی تا ۱۰ session، با برآورد فایل/مرحله + handle برای پیگیری). این همان‌جایی است که برشِ هر برنامه تنظیم می‌شود و برنامه «ثابت» می‌شود.

### 📥 پرکردن ماهانه (Backfill)
`dashboard/backfill.py` یک اتوپایلوت ۶۰-ثانیه‌ای درون‌پروسسی (بدون سرویس جدید). فقط وقتی صفِ دانلود+زیرنویس **آزما** باشد، یک دسته‌ی **محدود** (پیش‌فرض ۵) از sessionهایِ هنوز-پرداز‌نشده‌ی یک برنامه را به `pending_download` برمی‌گرداند تا cronِ دانلود Go + whisper کار واقعی را انجام دهند. محدود، **قابل‌توقف** (توگل)، هرگز حلقه نمی‌زند (هر پیشنهاد حداکثر یک‌بار ترفیع می‌یابد)، لینک‌های مرده (failed_permanent) رد می‌شوند. State در `dashboard_state.json["backfill"]`.

> **ایمنی:** همه‌ی نوشت‌های DB از مسیر pymysqlِ موجود می‌روند؛ برش **اضافی** است (SRT اصلی حفظ می‌شود)؛ backfill محدود و قابل‌توقف است؛ سرویس جدیدی اضافه نشده.
> **CLI (روی 53):** `cd dashboard && set -a && . ./dashboard.env && set +a && ./venv/bin/python llm_jobs.py run --job program_block --ids <sid> --all` (برش، بدون مدل) — و `--program-id <pid>` / `--all` برای اجرای مجددِ محدود به یک برنامه.
> **جزئیات کامل:** `docs/prompts/006-pipeline-steps-crop-onboarding-backfill.md`.

---

## 🚦 Crop Pilot & Backfill Gate (STEP 7) — 2026-10-10

This STEP's goal was narrow and safe: enable crop on **one** real program, prove
it on **10 samples**, and only then decide on backfill — **no broad rollout**.
The spec's own guard applies: *if the in-slot offset cannot be determined from
real evidence, STOP and report that the program needs a human-provided value.*
That is exactly what happened.

### Current Status
**STOP at the offset gate.** After a real-evidence sweep of every pilot
candidate, **no program has a stable, derivable in-slot `crop_offset`**, so crop
was **NOT** enabled on any production program and backfill was **kept OFF**.
This is the intended STOP branch (not a bug, not a partial rollout). No LLM model
calls were made; the pipeline is untouched and stable.

### Completed Work (this STEP)
- Recorded pre-change state (DB + dashboard + git) — all clean.
- Selected the best pilot candidate (**program 28**, "حکایت آزادگی").
- Determined the offset with **real evidence**: located the program's own
  intro/outro markers ("شروع برنامه … حکایت آزادگی" / "پایان برنامه … حکایت
  آزادگی") inside the actual SRT transcripts.
- **3-file dry-run** of the crop engine: original SRT **MD5 identical
  before/after**; crop output written to a temp file only.
- Evaluated the **backfill gate from real queue state → KEEP OFF**.
- Documented rollback + kill switch + next-agent checkpoint.
- Saved the master prompt (`docs/prompts/007-…`) and linked it from `006`.

### Production Crop Status
**DISABLED everywhere.** `crop_enabled = 0` for all 55 programs (verified
before and after). No crop was turned on.

### Crop-enabled Programs
**None.** (List is intentionally empty — the gate did not advance to enabling.)

### Crop Offsets
No offset was persisted as authoritative. Program 28 keeps its Phase-3 reference
row (`crop_offset` NULL, `time` 00:20:00, `crop_enabled` 0).

| Program | ID | Name | Duration | Crop offset | Crop enabled | 10-item QA | Date enabled |
|---|---|---|---|---|---|---|---|
| (pilot, NOT enabled) | 28 | حکایت آزادگی (Hokayat-e Azadegi) | 00:20:00 (real episodes ~21.6m) | **not derivable** (floats per episode) | **0 (disabled)** | n/a — stopped at offset gate | — |

**Why the offset isn't derivable:** the ~30-min archive slot starts with
variable-length neighbor content (a news bulletin / previous program's tail), so
the program's own start lands at a different in-slot time on each episode.
Program 28's end-marker was found at 04:11, 06:31, 07:17, 07:30 **and** 27:04
across 12 files, and the clean intro at 05:26 in only one file. A single fixed
offset — the only thing the crop engine supports — cannot be right for all of
them (it would cut the real beginning/ending or keep a neighbor's content).

### Quality Test Results
**Not run** (no valid offset to test against; running with a guess would just
reproduce the wrong crop). Dry-run (3 files): **3/3 PASS on the
"original SRT unchanged" (MD5) condition**; original SRT **not modified**.

### Backfill Status
**OFF** (not tested, not enabled). Reason from the real queue:
`pending_download = 181` (not low), whisper busy but steady, GPU/LLM busy
(burning the `correct_subtitles` backlog via the night boost). Gate rule:
*queue high → KEEP BACKFILL OFF.*

### Known Issues
- **GitLab `git.ai.ismc.ir` remote — BLOCKED (auth).** 53 and the local checkout
  have **no GitLab credential**; `git push` to it returns
  `Permission denied (publickey)`. The mandatory primary repo cannot be reached
  until the user provisions a credential. All STEP-7 changes are committed +
  pushed to GitHub `origin/download-db`.
- The in-slot offset genuinely varies per episode (news-length dependent) — an
  inherent property of this archive, not a data error.

### Remaining Work
- **Unblock crop** (needs the user / a human): for one program, supply the real
  in-slot `crop_offset` (watch one episode, note where the program starts
  *into* the file), **or** build a per-episode auto-detect that finds the
  "شروع برنامه / بسم‌الله" intro phrase in each SRT (out of scope this STEP).
- Once an offset is known for one program: set it, flip `crop_enabled=1`, run
  the 10-item test (≥9/10 PASS), then propose a per-program rollout table and
  re-check the backfill gate.

### Operational Commands (on 53)
```bash
# state
docker exec iranseda-mysql mysql -un8nuser -p"StrongPassword123!" radio \
  -e "SELECT id,name,time,crop_offset,crop_enabled FROM radio_programs WHERE crop_enabled=1;"
# set a program's crop once a real offset is known (keep-both, re-runnable)
docker exec iranseda-mysql mysql -un8nuser -p"StrongPassword123!" radio \
  -e "UPDATE radio_programs SET crop_offset='00:MM:SS', crop_enabled=1 WHERE id=<pid>;"
# re-run the program's steps (crop → summary → correct_text)
cd dashboard && set -a && . ./dashboard.env && set +a \
  && ./venv/bin/python llm_jobs.py run --job summary --program-id <pid> --all
```

### Rollback
```sql
-- turn crop OFF for a program, KEEPING offset + duration (fallback = full
-- transcript; nothing deleted):
UPDATE radio_programs SET crop_enabled = 0 WHERE id = <pid>;
```
(or 🚀 Programs → program → uncheck "crop enabled" → save; or
`POST /api/programs/crop` `{"id":<pid>,"crop_enabled":false}`). Kill switch
(unchanged): `./scripts/stop-background.sh` stops ONLY iranseda background LLM
work — never the model/whisper/LiteLLM/dashboard. Since no program was enabled,
**no rollback was needed**.

### NEXT_CHAT_CHECKPOINT
State 2026-10-10: STEP 7 **STOPPED at the offset gate** — crop NOT enabled on
any production program, backfill OFF. All Phase-3 features still built/deployed/
live on 53. The one unblock is a human-supplied `crop_offset` (or a per-episode
auto-detect feature). Full detail + evidence:
`docs/prompts/007-production-crop-and-backfill-gate.md` (§2 evidence, §5
dry-run, §11 unblock).

---

## 🚦 Per-Episode Crop Auto-Detection (STEP 8) — 2026-10-10

STEP 7 proved a fixed `crop_offset` is structurally unreliable (the in-slot start
drifts per episode). The user rejected a one-off human offset and chose
**option (b): detect the boundary independently for each file, rule-based, no
LLM, with per-episode confidence.** That is what was built.

### Current Status
**STOP at STEP 8.6.** Per-episode auto-crop is built, deterministic, and live for
the **pilot (program 28) only**: **2 HIGH-confidence episodes cropped**, the
other 20 program-28 episodes are **NEEDS_REVIEW** (full-transcript fallback,
reason + markers stored). Only **2 HIGH < the 10** needed for the 10-item QA, so
**no QA was run and no LLM model was called** (the STOP fires *before* any LLM
spend). **No production rollout beyond the pilot; backfill kept OFF.** Original
SRTs were never modified (MD5 verified).

### Detection Rules (rule-based, no LLM, deterministic)
| side | marker (regex on normalized text) |
|---|---|
| start | `شروع برامه\|شروع برنامه\|شروع برامه‌\|شروع برنامه‌` |
| end   | `پایان برامه\|پایان برنامه\|به پایان\|خاتمه برامه\|خاتمه برنامه` |

Confidence (`detect_boundary` in `dashboard/llm_jobs.py`):
- **HIGH** = start **and** end each marker-anchored in *this* file, and window
  length within `[0.7×dur, min(1.2×dur, slot)]` → **cropped**.
- **MEDIUM** = one side anchored, the other derived (e.g. `start = end − dur`),
  and the derived position in-slot → **no crop** (needs_review).
- **LOW / NEEDS_REVIEW** = no usable markers or implausible/out-of-slot window →
  **no crop**, reason + markers stored. **When in doubt → NEEDS_REVIEW.**

Storage: a `crop_detection` table (session_id UNIQUE, confidence, status,
evidence JSON) + a `crop_auto` flag on `radio_programs`. Re-detected every run
(no stale cache); the fixed-offset path is untouched.

### 20-Episode Dry-Run (read-only, no crops)
`llm_jobs.py detect --program 28 --limit 20 --extra 14,12 --dry-run`:
**HIGH=1 / MEDIUM=5 / NEEDS_REVIEW=14.** Real anchor-anchored window **21:32**
(1.08× the 20-min duration) — window length is *stable* while the start *floats*
(detected starts 05:34 → 27:46, spread 22:11). **MD5: all 20 originals unchanged.**

### Crop (pilot program 28)
`crop_auto=1` (pilot only). **2 HIGH cropped:**
| session | file | window |
|---|---|---|
| 5267 | radio-maaref-04-09-03-22-00 | 05:35–27:07 (21:32) |
| 4561 | radio-maaref-04-07-22-22-00 | 04:47–23:53 (19:06) |

**20 NEEDS_REVIEW** (10 LOW — no start anchor; 10 MEDIUM — one side anchored,
derived start out-of-slot). Both crop files open on the intro line and close on
the outro — no neighbor content, no cut real ending. **MD5: all 12 pilot
originals unchanged.**

### 10-Item QA
**STOP (2 HIGH < 10).** QA not run, **no LLM model called**. Valid STEP 8
outcome per spec. To reach 10 HIGH: add garbled start-marker variants to
`_START_PAT` (from a manual read of the NEEDS_REVIEW intros), or confirm the
~10 MEDIUM end-anchored episodes; then run the QA (≥9/10).

### Dataset / Site
**Dataset OK, Site OK.** The 2 crops show as 🎯 Program Block links on the
program-28 page (`docs/programs/55.html`); NEEDS_REVIEW episodes fall back to
the full transcript. Committed + pushed via the `refresh_site.sh` cron.

### Backfill Status
**OFF.** Re-checked at run time: 2 `correct_subtitles` boost workers actively
burning the backlog (~5586 subtitled in the pipeline). Queue not idle →
*KEEP BACKFILL OFF.*

### Known Issues
- **GitLab `git.ai.ismc.ir` remote — BLOCKED (auth).** No credential on 53/local;
  `git push` returns `Permission denied (publickey,password)`. All STEP-8 changes
  are committed + pushed to GitHub `origin/download-db`.
- HIGH rate on the pilot is low (~2/22) because Persian whisper ASR garbles the
  intro on most episodes. Expansion needs **per-program** marker vocabularies
  (program 28's intro format does not transfer to other programs).
- `generate_site.py` in `server` mode defaults to a **different** path
  (`…/iranseda/`, no trailing dash) than the live repo (`…/iranseda-crawler-golang-`);
  use `refresh_site.sh` (or set `DOWNLOADS_PATH`/`DOCS_PATH`/`PROGRAMS_PATH`).

### Rollback
```sql
UPDATE radio_programs SET crop_auto = 0 WHERE id = 28;   -- back to full transcript
-- optionally: DELETE FROM crop_detection WHERE program_id = 28;
```
(or 🚀 Programs → program 28 → uncheck "crop auto"). Kill switch (unchanged):
`./scripts/stop-background.sh` stops ONLY iranseda background LLM work.

### NEXT_CHAT_CHECKPOINT
State 2026-10-10: STEP 8 **STOPPED at 8.6** — 2 HIGH < 10, so no QA, no LLM
spend. Auto-crop live for the pilot only (2 cropped, 20 NEEDS_REVIEW). Backfill
OFF. GitLab BLOCKED. **Unblock:** raise pilot HIGH to ≥10 (add garbled
start-marker variants, or confirm the MEDIUM end-anchored episodes) → run the
10-item QA (≥9/10) → then consider expanding + re-check backfill. Full detail +
evidence: `docs/prompts/008-per-episode-boundary-detection.md`.

---

## 📝 لایسنس

این پروژه تحت مجوز MIT منتشر شده است.

---

## 🤝 مشارکت

برای گزارش باگ یا پیشنهاد فیچر جدید، لطفاً یک Issue ایجاد کنید.

---

**آخرین به‌روزرسانی**: 2026-10-10 (STEP 8 — per-episode crop auto-detection; STOP at 8.6)  
**وضعیت**: ✅ در حال اجرا و پایدار (6+ ماه)
