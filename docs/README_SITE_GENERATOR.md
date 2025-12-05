# 🌐 Site Generator - تولید صفحات وب

## 📋 نمای کلی

تولید خودکار صفحات HTML استاتیک از داده‌های دیتابیس و فایل‌های دانلود شده برای نمایش در GitHub Pages.

## 📁 فایل‌ها

- **`generate_site.py`** - اسکریپت اصلی تولید سایت
- **`run_generator.py`** - اجرای generator با محیط‌های مختلف
- **`config.py`** - مدیریت تنظیمات محیطی

## 🎯 عملکرد

### 1. اتصال به دیتابیس
خواندن اطلاعات از جداول:
- `radio_programs` - اطلاعات برنامه‌ها
- `radio_program_sessions` - لیست قسمت‌ها
- `radio_program_session_files` - فایل‌های مرتبط

### 2. محاسبه آمار
برای هر برنامه:
- تعداد کل قسمت‌ها
- تعداد زیرنویس‌ها
- تعداد متن‌های کامل
- اولین و آخرین تاریخ

### 3. تولید صفحات

#### صفحه اصلی (`docs/index.html`)
- جدول تمام برنامه‌ها با آمار
- آمار زمانی تولید زیرنویس
- آخرین برنامه‌های دارای متن کامل
- جدول آخرین فایل‌های cleaned

#### صفحات برنامه (`docs/programs/<id>.html`)
- اطلاعات کامل برنامه
- لیست تمام قسمت‌ها
- لینک‌های دانلود MP3
- لینک‌های زیرنویس و متن کامل

### 4. لینک‌دهی فایل‌ها
- زیرنویس‌های خام: `downloads/<name>.srt`
- متن‌های کامل: `downloads/cleaned/<name>.srt` و `.txt`
- لینک‌های GitHub Raw برای دانلود مستقیم

## 🔧 نصب و راه‌اندازی

### پیش‌نیازها

```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install pymysql python-dotenv
```

### وابستگی‌ها

- `pymysql` - اتصال به MySQL
- `python-dotenv` - مدیریت متغیرهای محیطی

## 🚀 اجرا

### اجرای دستی

```bash
# با محیط local
python run_generator.py --env local

# با محیط server
python run_generator.py --env server

# با فایل env سفارشی
python run_generator.py --env-file path/to/custom.env
```

### اجرا از طریق n8n

Workflow: `n8n_workflows/generate_site_go.json`
- **زمان‌بندی**: هر 2 ساعت
- **دستور**: 
  ```bash
  source venv/bin/activate
  export ENVIRONMENT=server
  python generate_site.py
  ```

## ⚙️ تنظیمات

### فایل `.env` یا `env.*.example`

```env
# Database
DB_HOST=localhost
DB_PORT=3306
DB_USER=n8nuser
DB_PASS=StrongPassword123!
DB_NAME=radio

# GitHub
GITHUB_USER=saber13812002
GITHUB_REPO=iranseda-crawler-golang-
GITHUB_BRANCH=download-db

# Environment
ENVIRONMENT=local  # local, server, production

# Paths (برای production)
DOWNLOADS_PATH=/path/to/downloads
DOCS_PATH=/path/to/docs
PROGRAMS_PATH=/path/to/docs/programs
```

### کلاس Config

`config.py` به صورت خودکار بر اساس `ENVIRONMENT` تنظیمات را لود می‌کند:
- **local**: مسیرهای نسبی (`./downloads`, `./docs`)
- **server**: مسیرهای مطلق سرور
- **production**: از متغیرهای محیطی

## 📊 ساختار خروجی

```
docs/
├── index.html              ← صفحه اصلی
├── .nojekyll              ← غیرفعال کردن Jekyll
└── programs/
    ├── 1.html             ← صفحه برنامه 1
    ├── 2.html             ← صفحه برنامه 2
    └── ...
```

## 🎨 ویژگی‌های HTML

### صفحه اصلی

- **جدول قابل مرتب‌سازی**: کلیک روی هدر برای مرتب‌سازی
- **آمار زمانی**: امروز، دیروز، این هفته، این ماه، امسال
- **آخرین برنامه‌ها**: 3 برنامه با بیشترین متن کامل
- **آخرین فایل‌ها**: 10 فایل cleaned جدید

### صفحات برنامه

- **اطلاعات کامل**: نام، زمان، رادیو، توضیحات
- **لیست قسمت‌ها**: با وضعیت دانلود
- **لینک‌های مستقیم**: MP3، زیرنویس، متن کامل
- **بازگشت به فهرست**: لینک به صفحه اصلی

## 🔍 منطق پیدا کردن فایل‌ها

```python
def find_subtitles_for_session(filename: str):
    stem = pathlib.Path(filename).stem
    # زیرنویس خام
    candidate = DOWNLOADS_DIR / f"{stem}.srt"
    # متن کامل
    cleaned_candidate = DOWNLOADS_DIR / "cleaned" / f"{stem}.srt"
```

## 🐛 عیب‌یابی

### خطا: "Connection refused"
- اتصال به دیتابیس را بررسی کنید
- تنظیمات `DB_HOST` و `DB_PORT` را چک کنید

### خطا: "Table doesn't exist"
- اسکریپت‌های SQL را اجرا کنید
- ساختار دیتابیس را بررسی کنید

### فایل‌ها پیدا نمی‌شوند
- مسیر `downloads/` را بررسی کنید
- نام فایل‌ها باید با `filename` در دیتابیس مطابقت داشته باشد

### لینک‌های GitHub Raw کار نمی‌کنند
- `GITHUB_USER`, `GITHUB_REPO`, `GITHUB_BRANCH` را بررسی کنید
- مطمئن شوید فایل‌ها در Git commit شده‌اند

## 📝 یادداشت‌ها

- فایل `.nojekyll` برای غیرفعال کردن Jekyll در GitHub Pages ایجاد می‌شود
- لینک‌های GitHub Raw برای دانلود مستقیم فایل‌ها استفاده می‌شوند
- آمارها به صورت real-time از فایل‌ها محاسبه می‌شوند

## 🔗 لینک‌های مرتبط

- [مستندات مرحله 6](workflows/06_site_generation.md)
- [GitHub Pages Documentation](https://docs.github.com/en/pages)

