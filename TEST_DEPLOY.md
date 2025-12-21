# 🧪 راهنمای تست Deploy خودکار

این راهنما نحوه تست و بررسی وضعیت deploy خودکار را توضیح می‌دهد.

## 📋 فایل‌های تست

- `check_deploy_status.sh` - بررسی وضعیت فعلی deploy
- `test_deploy_quick.sh` - تست سریع یک باره
- `test_deploy.sh` - تست با interval 1 دقیقه (3 بار)
- `deploy_loop_test.sh` - تست while loop با interval 1 دقیقه (5 بار)

## 🔍 مرحله 1: بررسی وضعیت فعلی

ابتدا ببینید چه چیزی فعال است:

```bash
chmod +x check_deploy_status.sh
./check_deploy_status.sh
```

این اسکریپت نشان می‌دهد:
- آیا systemd timer فعال است؟
- آیا cron job تنظیم شده؟
- آیا while loop در حال اجرا است؟
- وضعیت لاگ‌ها

## 🧪 مرحله 2: تست سریع (یک باره)

برای تست سریع که فقط یک بار اجرا می‌شود:

```bash
chmod +x test_deploy_quick.sh
./test_deploy_quick.sh
```

این تست:
- یک بار `deploy.sh` را اجرا می‌کند
- نتیجه را نشان می‌دهد
- برای اطمینان از کارکرد اسکریپت مفید است

## 🧪 مرحله 3: تست با Interval کوتاه

برای تست که چند بار با فاصله کوتاه اجرا می‌شود:

```bash
chmod +x test_deploy.sh
./test_deploy.sh
```

این تست:
- 3 بار با فاصله 1 دقیقه اجرا می‌شود
- برای اطمینان از کارکرد خودکار مفید است
- می‌توانید ببینید که آیا واقعاً هر X دقیقه اجرا می‌شود

## 🔄 مرحله 4: تست While Loop

برای تست while loop با interval کوتاه:

```bash
chmod +x deploy_loop_test.sh
./deploy_loop_test.sh
```

این تست:
- 5 بار با فاصله 1 دقیقه اجرا می‌شود
- شبیه‌سازی `deploy_loop.sh` است اما با interval کوتاه‌تر
- برای اطمینان از کارکرد while loop مفید است

## 🚀 راه‌اندازی و تست کامل

### گام 1: راه‌اندازی

```bash
# راه‌اندازی خودکار (بهترین روش را انتخاب می‌کند)
sudo ./setup_auto_deploy.sh
```

### گام 2: بررسی وضعیت

```bash
./check_deploy_status.sh
```

### گام 3: تست سریع

```bash
./test_deploy_quick.sh
```

### گام 4: تست با interval کوتاه (اختیاری)

اگر می‌خواهید مطمئن شوید که واقعاً هر X ساعت اجرا می‌شود، می‌توانید:

**روش 1: تغییر موقت interval در while loop**

```bash
# ویرایش deploy_loop.sh و تغییر INTERVAL_HOURS به 0.05 (3 دقیقه)
# سپس اجرا:
./deploy_loop_test.sh
```

**روش 2: استفاده از systemd timer با interval کوتاه**

```bash
# ایجاد یک timer تستی
sudo cp iranseda-deploy.timer /etc/systemd/system/iranseda-deploy-test.timer
sudo nano /etc/systemd/system/iranseda-deploy-test.timer
# تغییر OnUnitActiveSec=3h به OnUnitActiveSec=1m
sudo systemctl daemon-reload
sudo systemctl start iranseda-deploy-test.timer
sudo systemctl status iranseda-deploy-test.timer
```

## 📊 بررسی لاگ‌ها

### Systemd
```bash
# مشاهده لاگ‌های systemd
sudo journalctl -u iranseda-deploy.service -f

# مشاهده آخرین 50 خط
sudo journalctl -u iranseda-deploy.service -n 50
```

### While Loop
```bash
# مشاهده لاگ while loop
tail -f logs/deploy-loop.log

# مشاهده آخرین 50 خط
tail -50 logs/deploy-loop.log
```

### Cron
```bash
# مشاهده لاگ cron
tail -f logs/deploy.log

# یا لاگ سیستم
grep CRON /var/log/syslog | tail -20
```

## ✅ چک‌لیست تست

- [ ] `check_deploy_status.sh` اجرا شد و وضعیت را نشان داد
- [ ] `test_deploy_quick.sh` با موفقیت اجرا شد
- [ ] `test_deploy.sh` چند بار با موفقیت اجرا شد
- [ ] لاگ‌ها درست نوشته می‌شوند
- [ ] Git commit و push کار می‌کند
- [ ] `generate_site.py` با موفقیت اجرا می‌شود

## 🐛 عیب‌یابی

### مشکل: اسکریپت‌ها اجرا نمی‌شوند
```bash
chmod +x *.sh
ls -la *.sh
```

### مشکل: خطای git
```bash
git status
git remote -v
git fetch
```

### مشکل: خطای Python
```bash
source venv/bin/activate
python3 --version
python3 generate_site.py
```

### مشکل: خطای دیتابیس
```bash
# تست اتصال
mysql -h 192.168.2.160 -P 3306 -u n8nuser -p radio -e "SELECT 1;"
```

## 📝 نکات مهم

1. **تست با interval کوتاه**: برای تست، می‌توانید interval را موقتاً کوتاه کنید (مثلاً 1 دقیقه)
2. **بازگشت به حالت اصلی**: بعد از تست، حتماً interval را به 3 ساعت برگردانید
3. **بررسی لاگ‌ها**: همیشه لاگ‌ها را بررسی کنید تا مطمئن شوید همه چیز درست کار می‌کند
4. **تست در ساعات مختلف**: بهتر است در ساعات مختلف روز تست کنید

---

**آخرین به‌روزرسانی**: 2025-01-XX

