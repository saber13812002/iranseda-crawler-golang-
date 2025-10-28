# راهنمای تنظیم نوتیفیکیشن تلگرام و بله / Telegram & Bale Notification Setup Guide

این فایل شامل راهنمای کامل تنظیم نوتیفیکیشن برای تلگرام و بله و نصب در n8n است.

---

## 📋 فهرست مطالب / Table of Contents

1. [نصب و تنظیم اولیه](#1-نصب-و-تنظیم-اولیه)
2. [دریافت توکن و Chat ID](#2-دریافت-توکن-و-chat-id)
3. [تنظیم فایل Environment](#3-تنظیم-فایل-environment)
4. [استفاده در n8n](#4-استفاده-در-n8n)
5. [تست دستی](#5-تست-دستی)
6. [مثال‌های استفاده](#6-مثالههای-استفاده)

---

## 1. نصب و تنظیم اولیه / Initial Setup

### 1.1 نصب کتابخانه‌های مورد نیاز

```bash
# در محیط مجازی پروژه
cd /path/to/iranseda-crawler-golang-
source venv/bin/activate  # یا myenv/bin/activate
pip install requests
```

### 1.2 ساختار فایل‌ها

فایل‌های اسکریپت در مسیر `scripts/` قرار دارند:

- `notify_messenger.py` - ارسال پیام به تلگرام یا بله
- `notify_telegram.py` - ارسال نوتیفیکیشن‌های خودکار از دیتابیس
- `telegram_get_chat_id.py` - دریافت Chat ID

---

## 2. دریافت توکن و Chat ID / Getting Tokens and Chat IDs

### 2.1 ساخت ربات تلگرام / Telegram Bot

1. به ربات [@BotFather](https://t.me/BotFather) پیام بدهید
2. دستور `/newbot` را ارسال کنید
3. نام و username ربات را مشخص کنید
4. توکن (TOKEN) را کپی کنید

### 2.2 ساخت ربات بله / Bale Bot

1. به ربات [@balebotfa](https://eitaa.com/balebotfa) پیام بدهید
2. دستور `/newbot` را ارسال کنید
3. نام و username ربات را مشخص کنید
4. توکن (TOKEN) را کپی کنید

### 2.3 دریافت Chat ID / Getting Chat ID

**روش 1: استفاده از اسکریپت**

```bash
# تلگرام
export TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
python3 scripts/telegram_get_chat_id.py
```

**روش 2: استفاده از Bot API مستقیماً**

برای تلگرام:
```bash
curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
```

برای بله:
```bash
curl https://tapi.bale.ai/bot<YOUR_BOT_TOKEN>/getUpdates
```

**روش 3: افزودن ربات به گروه/کانال**

1. ربات را به گروه یا کانال اضافه کنید
2. پیامی ارسال کنید
3. دستور بالا را اجرا کنید تا Chat ID را ببینید

**توجه**: برای دریافت Chat ID کانال/گروه:
- Chat ID عددی است (مثلاً: `-1001234567890`)
- می‌توانید چند Chat ID را با کاما جدا کنید

---

## 3. تنظیم فایل Environment / Environment Setup

### 3.1 اضافه کردن متغیرهای نوتیفیکیشن به .env

فایل `.env` (یا `.env.production` یا `.env.server`) خود را باز کنید و این متغیرها را اضافه کنید:

```bash
# ============================================
# Messaging Configuration (Telegram/Bale)
# ============================================

# نوع پیام‌رسان: "telegram" یا "bale"
MESSENGER_TYPE=telegram

# توکن ربات (Bot Token)
# تلگرام: از @BotFather دریافت کنید
# بله: از @balebotfa دریافت کنید
MESSENGER_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# شناسه چت (میتوانید چند عدد با کاما جدا کنید)
# برای کاربر: عدد مثبت
# برای گروه/کانال: عدد منفی یا مثبت
MESSENGER_CHAT_ID=123456789,987654321,-1001234567890

# ============================================
# تنظیمات قبلی پروژه
# ============================================

# Database Configuration
ENVIRONMENT=server
DB_HOST=192.168.2.160
DB_PORT=3306
DB_USER=n8nuser
DB_PASS=StrongPassword123!
DB_NAME=radio

# GitHub Configuration
GITHUB_USER=saber13812002
GITHUB_REPO=iranseda-crawler-golang-
GITHUB_BRANCH=download-db

# Paths
DOWNLOADS_PATH=/mnt/data/saberprojects/iranseda-crawler-golang-/downloads
DOCS_PATH=/mnt/data/saberprojects/iranseda-crawler-golang-/docs
PROGRAMS_PATH=/mnt/data/saberprojects/iranseda-crawler-golang-/docs/programs
```

### 3.2 مثال‌های تنظیمات مختلف

**فقط تلگرام:**
```bash
MESSENGER_TYPE=telegram
MESSENGER_BOT_TOKEN=1234567890:ABCdefGHI...
MESSENGER_CHAT_ID=123456789
```

**فقط بله:**
```bash
MESSENGER_TYPE=bale
MESSENGER_BOT_TOKEN=1234567890:ABCdefGHI...
MESSENGER_CHAT_ID=123456789
```

**ارسال به چند چت همزمان:**
```bash
MESSENGER_TYPE=telegram
MESSENGER_BOT_TOKEN=1234567890:ABCdefGHI...
MESSENGER_CHAT_ID=123456789,987654321,-1001234567890
```

---

## 4. استفاده در n8n / Using in n8n

### 4.1 ساخت Workflow در n8n

1. وارد n8n شوید
2. گزینه "New Workflow" را انتخاب کنید
3. Workflow را به نام "IranSeda Notifications" ذخیره کنید

### 4.2 اضافه کردن نودهای مورد نیاز

#### نود 1: Trigger (شروع خودکار)
- **Type**: Schedule Trigger
- **Settings**: 
  - Interval: هر 1 ساعت
  - یا هر زمان دلخواه

#### نود 2: Execute Command
- **Type**: Execute Command
- **Settings**:
  ```
  Command: python3
  Arguments: 
    scripts/notify_messenger.py
  Working Directory: /mnt/data/saberprojects/iranseda-crawler-golang-
  ```

#### نود 3: Set Environment Variables
- **Type**: Set
- **Settings**:
  - Name: `MESSENGER_TYPE`
  - Value: `telegram`
  - Name: `MESSENGER_BOT_TOKEN`
  - Value: `YOUR_BOT_TOKEN`
  - Name: `MESSENGER_CHAT_ID`
  - Value: `YOUR_CHAT_ID`

#### یا استفاده از Code Node (پیشنهادی)

**نود Code در n8n:**
```javascript
// مسیر اسکریپت
const scriptPath = '/mnt/data/saberprojects/iranseda-crawler-golang-/scripts/notify_messenger.py';

// خواندن متغیرهای محیطی از .env
const fs = require('fs');
const envContent = fs.readFileSync('/mnt/data/saberprojects/iranseda-crawler-golang-/.env', 'utf8');

// استخراج متغیرها
const messengerType = envContent.match(/MESSENGER_TYPE=(.+)/)?.[1]?.trim() || 'telegram';
const botToken = envContent.match(/MESSENGER_BOT_TOKEN=(.+)/)?.[1]?.trim() || '';
const chatId = envContent.match(/MESSENGER_CHAT_ID=(.+)/)?.[1]?.trim() || '';

// ارسال دستورات
return {
  json: {
    messengerType,
    botToken,
    chatId,
    message: 'برنامه‌های جدید آماده دانلود هستند! / New programs ready for download!'
  }
};
```

**نود Execute Command در n8n:**
```bash
# Set environment variables
export MESSENGER_TYPE=telegram
export MESSENGER_BOT_TOKEN="YOUR_BOT_TOKEN"
export MESSENGER_CHAT_ID="YOUR_CHAT_ID"
export ENVIRONMENT=server
export DB_HOST=192.168.2.160
export DB_PORT=3306
export DB_USER=n8nuser
export DB_PASS="StrongPassword123!"
export DB_NAME=radio

# Execute script
cd /mnt/data/saberprojects/iranseda-crawler-golang-
source venv/bin/activate
python3 scripts/notify_messenger.py "🎉 برنامه‌های جدید آماده هستند!"
```

### 4.3 Workflow پیشنهادی برای n8n

```
┌─────────────────┐
│ Schedule Trigger│  ← هر 1 ساعت
└────────┬────────┘
         │
         v
┌─────────────────┐
│ Execute Command │  ← اجرای اسکریپت
└────────┬────────┘
         │
         v
┌─────────────────┐
│  Send Notify    │  ← ارسال نوتیفیکیشن
└─────────────────┘
```

### 4.4 اضافه کردن Webhook برای دریافت نوتیفیکیشن از اسکریپت‌ها

برای اینکه سایر اسکریپت‌ها بتوانند نوتیفیکیشن ارسال کنند:

1. در n8n یک Workflow جدید بسازید
2. نود Webhook را اضافه کنید
3. URL را کپی کنید
4. در محیط Deployment، Webhook URL را تنظیم کنید:

```bash
export N8N_WEBHOOK_URL="http://your-n8n-instance:5678/webhook/iranseda-notify"
```

---

## 5. تست دستی / Manual Testing

### 5.1 تست اسکریپت نوتیفیکیشن عمومی

```bash
# تلگرام
export MESSENGER_TYPE=telegram
export MESSENGER_BOT_TOKEN="YOUR_BOT_TOKEN"
export MESSENGER_CHAT_ID="YOUR_CHAT_ID"
python3 scripts/notify_messenger.py "سلام! این یک پیام تست است."

# بله
export MESSENGER_TYPE=bale
export MESSENGER_BOT_TOKEN="YOUR_BOT_TOKEN"
export MESSENGER_CHAT_ID="YOUR_CHAT_ID"
python3 scripts/notify_messenger.py "سلام! این یک پیام تست است."
```

### 5.2 تست با فایل .env

```bash
# اگر متغیرهای محیطی را در .env قرار داده‌اید
source .env  # بارگذاری متغیرهای محیطی
python3 scripts/notify_messenger.py "پیام تست"

# یا
export $(cat .env | grep -v '^#' | xargs)
python3 scripts/notify_messenger.py "پیام تست"
```

### 5.3 تست اسکریپت نوتیفیکیشن خودکار

```bash
# ارسال نوتیفیکیشن برنامه‌های جدید در 24 ساعت گذشته
export TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
export TELEGRAM_CHAT_ID="YOUR_CHAT_ID"
export ENVIRONMENT=server
python3 scripts/notify_telegram.py
```

### 5.4 ارسال به چند چت همزمان

```bash
export MESSENGER_TYPE=telegram
export MESSENGER_BOT_TOKEN="YOUR_BOT_TOKEN"
export MESSENGER_CHAT_ID="123456789,987654321,-1001234567890"
python3 scripts/notify_messenger.py "پیام به چندین چت"
```

---

## 6. مثال‌های استفاده / Usage Examples

### 6.1 ارسال پیام ساده

```bash
python3 scripts/notify_messenger.py "🎉 برنامه‌های جدید!"
```

### 6.2 ارسال پیام با فرمت HTML

```bash
python3 scripts/notify_messenger.py "<b>عنوان</b>\n<i>توضیحات</i>"
```

### 6.3 ارسال پیام از فایل

```bash
echo "متن پیام" | python3 scripts/notify_messenger.py
```

### 6.4 استفاده در Cron Job

افزودن به crontab:
```bash
crontab -e

# ارسال نوتیفیکیشن هر ساعت
0 * * * * cd /mnt/data/saberprojects/iranseda-crawler-golang- && source venv/bin/activate && python3 scripts/notify_telegram.py >> /var/log/iranseda-notify.log 2>&1
```

### 6.5 استفاده در Python Script دیگر

```python
import subprocess
import os

os.environ['MESSENGER_TYPE'] = 'telegram'
os.environ['MESSENGER_BOT_TOKEN'] = 'YOUR_BOT_TOKEN'
os.environ['MESSENGER_CHAT_ID'] = 'YOUR_CHAT_ID'

subprocess.run([
    'python3', 
    'scripts/notify_messenger.py',
    'پیام شما'
])
```

---

## 7. راهنمای رفع مشکل / Troubleshooting

### 7.1 خطای "Bot token is incorrect"

- بررسی کنید توکن را صحیح وارد کرده‌اید
- برای تلگرام: توکن باید با @BotFather دریافت شود
- برای بله: توکن باید با @balebotfa دریافت شود

### 7.2 خطای "Chat not found"

- ربات را به گروه/کانال اضافه کرده‌اید؟
- Chat ID را صحیح وارد کرده‌اید؟
- برای گروه/کانال: باید Administrator باشد

### 7.3 خطای "Message is too long"

- تلگرام: حداکثر 4096 کاراکتر
- بله: حداکثر 4096 کاراکتر
- پیام خود را کوتاه‌تر کنید یا به چند بخش تقسیم کنید

### 7.4 خطای اتصال

- بررسی کنید اینترنت سرور شما متصل است
- بررسی کنید IP سرور شما از Bot API Telegram/Bale بلاک نشده باشد
- بررسی کنید فایروال شما مانع نمی‌شود

---

## 8. نکات امنیتی / Security Notes

1. **هرگز توکن ربات را در Git commit نکنید**
2. فایل `.env` را در `.gitignore` قرار دهید
3. فقط به افراد قابل اعتماد دسترسی به توکن بدهید
4. از ویرایشگرهایی استفاده کنید که توکن را هشدار می‌دهند

---

## 9. پشتیبانی / Support

برای سوالات و مشکلات:
- GitHub Issues: [لینک مخزن]
- Email: [ایمیل شما]

---

**نوشته شده در**: 2024
**نسخه**: 1.0
**نویسنده**: IranSeda Crawler Team

