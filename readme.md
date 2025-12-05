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

## 📝 لایسنس

این پروژه تحت مجوز MIT منتشر شده است.

---

## 🤝 مشارکت

برای گزارش باگ یا پیشنهاد فیچر جدید، لطفاً یک Issue ایجاد کنید.

---

**آخرین به‌روزرسانی**: 2025-01-XX  
**وضعیت**: ✅ در حال اجرا و پایدار (6+ ماه)
