# 🚀 راهنمای اجرای خودکار Deploy

این راهنما نحوه راه‌اندازی اجرای خودکار اسکریپت `deploy.sh` را هر 3 ساعت توضیح می‌دهد.

## 📋 فایل‌های موجود

- `deploy.sh` - اسکریپت اصلی deploy (commit, push, generate site)
- `deploy_loop.sh` - اجرای خودکار با while loop
- `setup_auto_deploy.sh` - اسکریپت راه‌اندازی خودکار (انتخاب بهترین روش)
- `iranseda-deploy.service` - فایل systemd service
- `iranseda-deploy.timer` - فایل systemd timer

## 🎯 روش 1: استفاده از setup_auto_deploy.sh (پیشنهادی)

ساده‌ترین روش! این اسکریپت به صورت خودکار بهترین روش را انتخاب می‌کند:

```bash
chmod +x setup_auto_deploy.sh
sudo ./setup_auto_deploy.sh
```

این اسکریپت:
- اگر systemd موجود باشد، از systemd timer استفاده می‌کند
- اگر cron موجود باشد، از cron استفاده می‌کند
- در غیر این صورت، از while loop استفاده می‌کند

## 🔧 روش 2: Systemd Timer (برای سیستم‌های با systemd)

```bash
# 1. کپی فایل‌ها
sudo cp iranseda-deploy.service /etc/systemd/system/
sudo cp iranseda-deploy.timer /etc/systemd/system/

# 2. فعال‌سازی
sudo systemctl daemon-reload
sudo systemctl enable iranseda-deploy.timer
sudo systemctl start iranseda-deploy.timer

# 3. بررسی وضعیت
sudo systemctl status iranseda-deploy.timer

# 4. مشاهده لاگ‌ها
sudo journalctl -u iranseda-deploy.service -f
```

**دستورات مفید:**
```bash
# توقف
sudo systemctl stop iranseda-deploy.timer

# شروع مجدد
sudo systemctl start iranseda-deploy.timer

# غیرفعال کردن
sudo systemctl disable iranseda-deploy.timer

# حذف
sudo systemctl stop iranseda-deploy.timer
sudo systemctl disable iranseda-deploy.timer
sudo rm /etc/systemd/system/iranseda-deploy.{service,timer}
sudo systemctl daemon-reload
```

## ⏰ روش 3: Cron Job

```bash
# باز کردن crontab
crontab -e

# اضافه کردن این خط (هر 3 ساعت در دقیقه 0)
0 */3 * * * cd /mnt/data/saberprojects/iranseda-crawler-golang- && /bin/bash deploy.sh >> /mnt/data/saberprojects/iranseda-crawler-golang-/logs/deploy.log 2>&1

# ذخیره و خروج

# بررسی cron jobs
crontab -l
```

## 🔄 روش 4: While Loop (برای سیستم‌های بدون cron/systemd)

```bash
# اجرا در background
chmod +x deploy_loop.sh
nohup ./deploy_loop.sh > /dev/null 2>&1 &

# یا با screen (پیشنهادی)
screen -S deploy
./deploy_loop.sh
# سپس Ctrl+A سپس D برای detach

# مشاهده لاگ‌ها
tail -f logs/deploy-loop.log

# توقف
kill $(cat /tmp/deploy_loop.pid)
```

## 📊 بررسی وضعیت

### Systemd
```bash
sudo systemctl status iranseda-deploy.timer
sudo journalctl -u iranseda-deploy.service --since "1 hour ago"
```

### Cron
```bash
crontab -l
tail -f logs/deploy.log
```

### While Loop
```bash
ps aux | grep deploy_loop
tail -f logs/deploy-loop.log
```

## 🐛 عیب‌یابی

### مشکل: اسکریپت اجرا نمی‌شود
```bash
# بررسی دسترسی اجرا
chmod +x deploy.sh deploy_loop.sh setup_auto_deploy.sh

# تست دستی
./deploy.sh
```

### مشکل: خطای git
```bash
# بررسی تنظیمات git
git config --list
git remote -v

# تست اتصال
git fetch
```

### مشکل: خطای Python
```bash
# بررسی virtualenv
source venv/bin/activate
python3 --version
pip list | grep pymysql

# تست دستی
python3 generate_site.py
```

### مشکل: خطای دیتابیس
```bash
# بررسی اتصال
mysql -h 192.168.2.160 -P 3306 -u n8nuser -p radio
```

## 📝 لاگ‌ها

- Systemd: `sudo journalctl -u iranseda-deploy.service`
- Cron/While Loop: `logs/deploy.log` یا `logs/deploy-loop.log`

## ⚙️ تنظیمات

برای تغییر فاصله زمانی اجرا:

### Systemd Timer
ویرایش `iranseda-deploy.timer`:
```ini
OnUnitActiveSec=3h  # تغییر به زمان دلخواه (مثلاً 2h برای 2 ساعت)
```

### Cron
```bash
0 */3 * * *  # هر 3 ساعت
0 */2 * * *  # هر 2 ساعت
0 * * * *    # هر ساعت
```

### While Loop
ویرایش `deploy_loop.sh`:
```bash
INTERVAL_HOURS=3  # تغییر به عدد دلخواه
```

## ✅ تست

پس از راه‌اندازی، می‌توانید با دستور زیر تست کنید:

```bash
# Systemd
sudo systemctl start iranseda-deploy.service

# Cron (اجرای دستی)
./deploy.sh

# While Loop (اجرای دستی)
./deploy.sh
```

---

**آخرین به‌روزرسانی**: 2025-01-XX

