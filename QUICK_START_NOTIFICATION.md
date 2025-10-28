# ⚡ راهنمای سریع نصب نوتیفیکیشن / Quick Start Notification Guide

## 1️⃣ دریافت Bot Token

### تلگرام / Telegram:
```
1. به @BotFather در تلگرام پیام بدهید
2. دستور /newbot را ارسال کنید
3. نام و username ربات را مشخص کنید
4. TOKEN را کپی کنید
```

### بله / Bale:
```
1. به @balebotfa در بله پیام بدهید
2. دستور /newbot را ارسال کنید
3. نام و username ربات را مشخص کنید
4. TOKEN را کپی کنید
```

---

## 2️⃣ دریافت Chat ID

```bash
# بارگذاری TOKEN در محیط
export MESSENGER_BOT_TOKEN="YOUR_BOT_TOKEN"

# اجرای اسکریپت
cd /mnt/data/saberprojects/iranseda-crawler-golang-
python3 scripts/telegram_get_chat_id.py

# سپس یک پیام به ربات بفرستید و دوباره اجرا کنید
```

Chat ID را یادداشت کنید.

---

## 3️⃣ تنظیم فایل .env

فایل `.env` (یا `.env.server`) را باز کنید و این خطوط را اضافه کنید:

```bash
# نوتیفیکیشن
MESSENGER_TYPE=telegram
MESSENGER_BOT_TOKEN=YOUR_TOKEN_HERE
MESSENGER_CHAT_ID=YOUR_CHAT_ID_HERE

# یا برای بله:
# MESSENGER_TYPE=bale
```

---

## 4️⃣ تست

```bash
# تنظیم متغیرهای محیطی
export MESSENGER_TYPE=telegram
export MESSENGER_BOT_TOKEN="YOUR_TOKEN"
export MESSENGER_CHAT_ID="YOUR_CHAT_ID"

# ارسال پیام تست
python3 scripts/notify_messenger.py "سلام! این یک تست است."
```

اگر پیام دریافت کردید، ✅ همه چیز درست است!

---

## 5️⃣ راه‌اندازی در n8n

### روش 1: استفاده از Execute Command Node

```
1. Workflow جدید در n8n ایجاد کنید
2. Schedule Trigger اضافه کنید (هر 1 ساعت)
3. Execute Command Node اضافه کنید
4. Command را تنظیم کنید:
```

```bash
cd /mnt/data/saberprojects/iranseda-crawler-golang-
source venv/bin/activate
export ENVIRONMENT=server
export DB_HOST=192.168.2.160
export DB_USER=n8nuser
export DB_PASS="StrongPassword123!"
export DB_NAME=radio
export TELEGRAM_BOT_TOKEN="YOUR_TOKEN"
export TELEGRAM_CHAT_ID="YOUR_CHAT_ID"
python3 scripts/notify_telegram.py
```

### روش 2: وارد کردن Workflow آماده

```bash
# Import Workflow از فایل JSON
# فایل: n8n_workflows/telegram_notification.json
```

---

## 6️⃣ استفاده‌های رایج

### ارسال پیام دستی:
```bash
python3 scripts/notify_messenger.py "پیام شما"
```

### نوتیفیکیشن خودکار برنامه‌های جدید:
```bash
python3 scripts/notify_telegram.py
```

### ارسال به چند چت:
```bash
export MESSENGER_CHAT_ID="123,456,789"
python3 scripts/notify_messenger.py "پیام به همه"
```

---

## ❓ رفع مشکلات متداول

### خطا: "Bot token is incorrect"
→ بررسی کنید TOKEN را صحیح وارد کرده‌اید

### خطا: "Chat not found"
→ ربات را به گروه/کانال اضافه کنید
→ Chat ID را دوباره بررسی کنید

### پیام ارسال نمی‌شود:
→ اینترنت سرور را بررسی کنید
→ فایروال را بررسی کنید

---

**موفق باشید! / Good Luck!** 🎉

