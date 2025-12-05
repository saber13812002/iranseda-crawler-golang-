# 🔄 Git Sync - همگام‌سازی با GitHub

## 📋 نمای کلی

همگام‌سازی خودکار تغییرات پروژه با مخزن GitHub برای:
- بکاپ فایل‌های دانلود شده
- انتشار صفحات وب در GitHub Pages
- نگه‌داری تاریخچه تغییرات

## 🎯 عملکرد

### 1. Hard Reset
شاخه محلی با `origin/download-db` همگام می‌شود:
```bash
git fetch origin download-db
git reset --hard origin/download-db
```

### 2. Staging
تمام فایل‌های تغییر یافته stage می‌شوند:
```bash
git add .
```

### 3. Commit (شرطی)
اگر تغییری وجود داشته باشد:
```bash
git commit -m "auto update from n8n"
```

### 4. Push
تغییرات به GitHub ارسال می‌شوند:
```bash
git push origin download-db
```

## 🔧 تنظیمات n8n

### Workflow

- **`git_push.json`** - همگام‌سازی Git

### دستور کامل

```bash
set -e
cd /mnt/data/saberprojects/iranseda-crawler-golang-/
git fetch origin download-db
git reset --hard origin/download-db
git add .
git commit -m "auto update from n8n" || echo "No changes to commit"
git push origin download-db
```

## ⏰ زمان‌بندی

- **زمان‌بندی**: هر 90 دقیقه
- **وابستگی**: باید بعد از تمام مراحل (1-6) اجرا شود

## 🔐 احراز هویت

### SSH Key

کاربر سرور باید SSH key معتبر برای GitHub داشته باشد:
```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
# اضافه کردن به GitHub: Settings > SSH and GPG keys
```

### Personal Access Token (جایگزین)

در صورت استفاده از HTTPS:
```bash
git remote set-url origin https://TOKEN@github.com/USERNAME/REPO.git
```

## ⚠️ نکات مهم

### Hard Reset

این فرآیند **destructive** است:
- تمام تغییرات محلی که commit نشده‌اند حذف می‌شوند
- اگر تغییر دستی دارید، قبل از اجرا commit کنید

### فایل‌های حجیم

- فایل‌های MP3 ممکن است مخزن را بزرگ کنند
- در صورت نیاز، از Git LFS استفاده کنید:
  ```bash
  git lfs track "*.mp3"
  ```

### شاخه

- شاخه پیش‌فرض: `download-db`
- برای تغییر شاخه، دستورات `git fetch` و `git push` را به‌روزرسانی کنید

## 🐛 عیب‌یابی

### خطا: "Permission denied"
- SSH key را بررسی کنید
- دسترسی کاربر به مخزن را چک کنید

### خطا: "No changes to commit"
- این یک خطا نیست - فقط پیام اطلاع‌رسانی است
- اگر تغییری وجود نداشته باشد، commit انجام نمی‌شود

### خطا: "Failed to push"
- اتصال اینترنت را بررسی کنید
- دسترسی push به مخزن را چک کنید
- ممکن است نیاز به pull قبل از push باشد

## 📝 یادداشت‌ها

- این workflow **idempotent** است
- اگر تغییری نباشد، commit انجام نمی‌شود
- تمام فایل‌ها (شامل `downloads/` و `docs/`) به Git اضافه می‌شوند

## 🔗 لینک‌های مرتبط

- [مستندات مرحله 5](workflows/05_git_sync.md)
- [GitHub Pages Documentation](https://docs.github.com/en/pages)

