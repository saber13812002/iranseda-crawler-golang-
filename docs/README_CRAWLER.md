# 🕷️ Crawler - خزش و ثبت برنامه‌ها

## 📋 نمای کلی

اسکریپت Python که صفحات برنامه‌های رادیو ایران‌صدا را خزش می‌کند و اطلاعات برنامه‌ها را در دیتابیس ثبت می‌کند.

## 📁 فایل‌ها

- **`crawler/crawler.py`** - اسکریپت اصلی خزش
- **`crawler/crawl_links.txt`** - لیست لینک‌های صفحات برنامه‌ها (ورودی)
- **`scripts/backfill_program_times.py`** - بک‌فیل و به‌روزرسانی زمان‌بندی برنامه‌ها

## 🎯 عملکرد

### 1. خواندن لینک‌ها
از فایل `crawl_links.txt` لینک‌های صفحات برنامه‌ها خوانده می‌شود.

### 2. استخراج اطلاعات
برای هر صفحه:
- **نام برنامه** (`h1.prog-name`)
- **زمان پخش** (`h2.guide-prog`)
- **توضیحات** (`div.col-plus-md-9 p`)
- **نام رادیو** (`div.BaseName strong a`)
- **شناسه رادیو** (از query parameter `ch`)

### 3. استخراج لینک‌های آرشیو
تمام لینک‌های `Program/?VALID=TRUE` از صفحه استخراج می‌شوند.

### 4. مدیریت Legacy Programs
- اگر URL جدید باشد → رکورد جدید ایجاد می‌شود
- اگر زمان/ساعت/رادیو تغییر کند → رکورد قدیمی `is_legacy=1` شده و رکورد جدید ایجاد می‌شود
- اگر فقط فیلدی خالی باشد → همان رکورد تکمیل می‌شود

## 🔧 نصب و راه‌اندازی

### پیش‌نیازها

```bash
cd crawler
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### وابستگی‌ها

- `requests` - درخواست‌های HTTP
- `beautifulsoup4` - پارس HTML
- `pymysql` - اتصال به MySQL
- `python-dotenv` - مدیریت متغیرهای محیطی

## 🚀 اجرا

### اجرای دستی

```bash
cd crawler
source venv/bin/activate
python crawler.py
```

### اجرا از طریق n8n

Workflow: `n8n_workflows/crawl_go_copy.json`
- **زمان‌بندی**: هر 45 دقیقه
- **دستور**: `cd crawler && source venv/bin/activate && python crawler.py`

## ⚙️ تنظیمات

### فایل `.env`

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=n8nuser
DB_PASS=StrongPassword123!
DB_NAME=radio
```

### فایل `crawl_links.txt`

هر خط یک لینک کامل به صفحه برنامه:
```
https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&e=123456
https://radio.iranseda.ir/Program/?VALID=TRUE&ch=55&e=789012
```

## 📊 خروجی

### جدول `radio_programs`

| ستون | توضیح |
|------|-------|
| `id` | شناسه یکتا |
| `name` | نام برنامه |
| `url` | لینک آرشیو برنامه |
| `time` | مدت زمان (HH:MM:SS) |
| `start` | ساعت شروع (HH:MM:SS) |
| `time_description` | توضیح کامل زمان پخش |
| `description` | توضیحات برنامه |
| `radio` | نام رادیو |
| `radio_id` | شناسه رادیو |
| `is_legacy` | آیا نسخه قدیمی است (0/1) |
| `legacy_expires_at` | زمان deprecate شدن |

## 🔍 اسکریپت Backfill

`scripts/backfill_program_times.py` برای:
- پر کردن فیلدهای خالی `time` و `start`
- تشخیص تغییرات زمان‌بندی
- علامت‌گذاری برنامه‌های legacy

### اجرا

```bash
python scripts/backfill_program_times.py
```

## 🐛 عیب‌یابی

### خطا: "Error loading .env file"
- مطمئن شوید فایل `.env` در ریشه پروژه وجود دارد
- مسیر نسبی در `crawler.py` را بررسی کنید

### خطا: "Connection refused"
- اتصال به دیتابیس را بررسی کنید
- فایروال و تنظیمات MySQL را چک کنید

### برنامه‌ها ثبت نمی‌شوند
- ساختار HTML صفحه را بررسی کنید (ممکن است تغییر کرده باشد)
- لاگ‌های خروجی را بررسی کنید

## 📝 یادداشت‌ها

- این اسکریپت **idempotent** است - می‌توانید چندین بار اجرا کنید بدون ایجاد رکورد تکراری
- برای افزودن برنامه جدید، فقط لینک را به `crawl_links.txt` اضافه کنید
- تغییرات زمان‌بندی به صورت خودکار مدیریت می‌شوند

## 🔗 لینک‌های مرتبط

- [مستندات مرحله 1](workflows/01_scan_and_ingest.md)
- [مستندات به‌روزرسانی زمان‌بندی](workflows/00_program_schedule_refresh.md)

