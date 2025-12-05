# 🛠️ Scripts & Utilities - اسکریپت‌های کمکی

## 📋 نمای کلی

مجموعه اسکریپت‌های کمکی برای نگهداری، بک‌فیل و اطلاع‌رسانی.

## 📁 فایل‌ها

### 1. `scripts/backfill_program_times.py`

بک‌فیل و به‌روزرسانی زمان‌بندی برنامه‌ها.

#### عملکرد
- پر کردن فیلدهای خالی `time` و `start`
- تشخیص تغییرات زمان‌بندی
- علامت‌گذاری برنامه‌های legacy

#### اجرا
```bash
python scripts/backfill_program_times.py
```

#### خروجی
- برنامه‌هایی که فیلدهای خالی دارند → تکمیل می‌شوند
- برنامه‌هایی که زمان تغییر کرده → legacy شده و رکورد جدید ایجاد می‌شود

---

### 2. `scripts/notify_telegram.py`

ارسال اعلان به تلگرام.

#### عملکرد
- ارسال پیام به کانال/گروه تلگرام
- استفاده از Bot API

#### تنظیمات
```python
TELEGRAM_BOT_TOKEN = "your_bot_token"
TELEGRAM_CHAT_ID = "your_chat_id"
```

#### اجرا
```bash
python scripts/notify_telegram.py "پیام تست"
```

---

### 3. `scripts/notify_messenger.py`

ارسال اعلان به Messenger (Facebook).

#### عملکرد
- ارسال پیام به Messenger
- استفاده از Graph API

#### تنظیمات
```python
MESSENGER_ACCESS_TOKEN = "your_access_token"
MESSENGER_PAGE_ID = "your_page_id"
```

---

### 4. `scripts/telegram_get_chat_id.py`

دریافت Chat ID تلگرام.

#### عملکرد
- کمک برای پیدا کردن Chat ID
- برای استفاده در `notify_telegram.py`

#### اجرا
```bash
python scripts/telegram_get_chat_id.py
```

---

### 5. `scripts/process_failed_ffmpeg.py`

پردازش فایل‌های failed از ffmpeg.

#### عملکرد
- پیدا کردن فایل‌های `.ffmpeg.failed`
- لاگ خطاها
- امکان retry

#### اجرا
```bash
python scripts/process_failed_ffmpeg.py
```

---

## 🔧 نصب و راه‌اندازی

### پیش‌نیازها

```bash
cd scripts
python3 -m venv venv
source venv/bin/activate
pip install pymysql python-dotenv requests
```

### وابستگی‌های مشترک

- `pymysql` - اتصال به دیتابیس
- `python-dotenv` - مدیریت متغیرهای محیطی
- `requests` - درخواست‌های HTTP

## 📝 استفاده

### بک‌فیل زمان‌بندی

```bash
# از ریشه پروژه
python scripts/backfill_program_times.py
```

این اسکریپت:
1. تمام برنامه‌های فعال را می‌خواند
2. برای هر برنامه، صفحه را دوباره می‌خواند
3. فیلدهای خالی را پر می‌کند
4. تغییرات زمان‌بندی را تشخیص می‌دهد

### اطلاع‌رسانی

```bash
# تلگرام
python scripts/notify_telegram.py "پیام تست"

# Messenger
python scripts/notify_messenger.py "پیام تست"
```

### دریافت Chat ID

```bash
python scripts/telegram_get_chat_id.py
```

بعد از اجرا:
1. به ربات تلگرام پیام بفرستید
2. Chat ID در خروجی نمایش داده می‌شود

## ⚙️ تنظیمات

### فایل `.env`

```env
# Database (برای backfill)
DB_HOST=localhost
DB_PORT=3306
DB_USER=n8nuser
DB_PASS=StrongPassword123!
DB_NAME=radio

# Telegram (برای notify_telegram)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Messenger (برای notify_messenger)
MESSENGER_ACCESS_TOKEN=your_access_token
MESSENGER_PAGE_ID=your_page_id
```

## 🐛 عیب‌یابی

### خطا: "Module not found"
- virtualenv را فعال کنید
- وابستگی‌ها را نصب کنید

### خطا: "Database connection failed"
- تنظیمات دیتابیس را بررسی کنید
- اتصال به دیتابیس را تست کنید

### خطا: "Telegram API error"
- Bot Token را بررسی کنید
- Chat ID را بررسی کنید
- دسترسی ربات را چک کنید

## 📝 یادداشت‌ها

- اسکریپت‌های اطلاع‌رسانی می‌توانند در n8n workflowها استفاده شوند
- `backfill_program_times.py` می‌تواند به صورت دوره‌ای اجرا شود
- تمام اسکریپت‌ها از فایل `.env` در ریشه پروژه استفاده می‌کنند

## 🔗 لینک‌های مرتبط

- [مستندات مرحله 0 - به‌روزرسانی زمان‌بندی](workflows/00_program_schedule_refresh.md)
- [مستندات Crawler](../README_CRAWLER.md)

