# 📱 خلاصه راه‌اندازی نوتیفیکیشن تلگرام و بله / Telegram & Bale Notification Summary

## 📁 فایل‌های ایجاد شده

### 1. اسکریپت‌های Python

- **`scripts/notify_messenger.py`** - اسکریپت ارسال پیام به تلگرام یا بله
  - پشتیبانی از تلگرام و بله
  - ارسال به چند چت همزمان
  - قابل استفاده در n8n

- **`scripts/notify_telegram.py`** - اسکریپت نوتیفیکیشن خودکار از دیتابیس
  - پیدا کردن برنامه‌های جدید
  - ارسال خودکار نوتیفیکیشن

- **`scripts/telegram_get_chat_id.py`** - دریافت Chat ID
  - استخراج Chat ID از به‌روزرسانی‌ها

### 2. فایل‌های راهنما

- **`NOTIFICATION_SETUP.md`** - راهنمای کامل تنظیمات
  - نصب و راه‌اندازی
  - نحوه دریافت توکن
  - تنظیم فایل .env
  - راهنمای n8n
  - مثال‌های استفاده
  - رفع مشکل

- **`QUICK_START_NOTIFICATION.md`** - راهنمای سریع
  - 6 مرحله ساده برای راه‌اندازی
  - دستورات فوری

- **`NOTIFICATION_SUMMARY.md`** - این فایل

### 3. فایل‌های Environment

- **`env.local.example`** - با تنظیمات نوتیفیکیشن به‌روز شد
- **`env.server.example`** - با تنظیمات نوتیفیکیشن به‌روز شد  
- **`env.production.example`** - با تنظیمات نوتیفیکیشن به‌روز شد

### 4. قالب n8n

- **`n8n_workflows/telegram_notification.json`** - Workflow آماده برای n8n

---

## ⚙️ متغیرهای Environment

### متغیرهای اصلی:

```bash
# نوع پیام‌رسان
MESSENGER_TYPE=telegram  # یا bale

# توکن ربات
MESSENGER_BOT_TOKEN=YOUR_BOT_TOKEN_HERE

# شناسه چت (میتوانید چند عدد با کاما جدا کنید)
MESSENGER_CHAT_ID=123456789
```

### متغیرهای اختیاری:

```bash
# برای اسکریپت notify_telegram.py
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
TELEGRAM_CHAT_ID=YOUR_CHAT_ID_HERE
NOTIFY_WINDOW_HOURS=24  # پنجره زمانی به‌روزرسانی‌ها
```

---

## 🚀 شروع سریع / Quick Start

### 1. دریافت توکن:
- تلگرام: به @BotFather پیام بدهید و `/newbot` بزنید
- بله: به @balebotfa پیام بدهید و `/newbot` بزنید

### 2. دریافت Chat ID:
```bash
export MESSENGER_BOT_TOKEN="YOUR_TOKEN"
python3 scripts/telegram_get_chat_id.py
```

### 3. افزودن به .env:
```bash
MESSENGER_TYPE=telegram
MESSENGER_BOT_TOKEN="YOUR_TOKEN"
MESSENGER_CHAT_ID="YOUR_CHAT_ID"
```

### 4. تست:
```bash
export $(cat .env | grep -v '^#' | xargs)
python3 scripts/notify_messenger.py "پیام تست"
```

---

## 📝 مثال‌های استفاده

### ارسال پیام ساده:
```bash
python3 scripts/notify_messenger.py "سلام!"
```

### استفاده در کد Python:
```python
import subprocess
import os

os.environ['MESSENGER_TYPE'] = 'telegram'
os.environ['MESSENGER_BOT_TOKEN'] = 'YOUR_TOKEN'
os.environ['MESSENGER_CHAT_ID'] = 'YOUR_CHAT_ID'

subprocess.run([
    'python3', 
    'scripts/notify_messenger.py',
    'پیام شما'
])
```

### استفاده در n8n:
```
1. Schedule Trigger (هر 1 ساعت)
2. Execute Command
   Command: python3
   Args: scripts/notify_telegram.py
   Working Dir: /mnt/data/saberprojects/iranseda-crawler-golang-
```

---

## 📚 مستندات کامل

برای راهنمای کامل، فایل‌های زیر را ببینید:

1. **`NOTIFICATION_SETUP.md`** - راهنمای کامل
2. **`QUICK_START_NOTIFICATION.md`** - راهنمای سریع

---

## ✅ چک‌لیست راه‌اندازی

- [ ] Bot Token دریافت شد (تلگرام یا بله)
- [ ] Chat ID دریافت شد
- [ ] متغیرهای محیطی به .env اضافه شد
- [ ] تست اولیه موفق بود
- [ ] n8n workflow ساخته شد (اختیاری)
- [ ] Cron job تنظیم شد (اختیاری)

---

**نوشته شده در**: 2024
**نسخه**: 1.0

