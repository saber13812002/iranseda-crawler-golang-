# 📝 Subtitle Generation - تولید زیرنویس خودکار

## 📋 نمای کلی

تولید خودکار فایل‌های زیرنویس (SRT) برای فایل‌های صوتی با استفاده از مدل‌های ASR (Automatic Speech Recognition).

## 🎯 عملکرد

این مرحله از یک ابزار خارجی استفاده می‌کند که در پروژه جداگانه‌ای قرار دارد:

**مسیر**: `/mnt/data/saberprojects/automated-multi-step-content-processing-and-seo-optimization-system/Subtitle-Generator`

### فرآیند

1. **اسکن پوشه دانلود**: تمام فایل‌های `.mp3` در پوشه `downloads/` پیدا می‌شوند
2. **بررسی وجود زیرنویس**: اگر فایل `.srt` هم‌نام وجود داشته باشد، skip می‌شود
3. **تولید زیرنویس**: مدل ASR برای هر فایل اجرا می‌شود
4. **ذخیره**: فایل `.srt` در همان پوشه کنار فایل صوتی ذخیره می‌شود

## 🔧 تنظیمات n8n

### Workflowها

- **`srt.json`** - تولید زیرنویس فارسی (`--language fa`)
- **`srt_farsi.json`** - نسخه دیگر برای فارسی
- **`srt_arabic.json`** - تولید زیرنویس عربی (`--language ar`)
- **`suball.json`** - نسخه قدیمی (deprecated)

### دستور اجرا

```bash
cd /mnt/data/saberprojects/automated-multi-step-content-processing-and-seo-optimization-system/Subtitle-Generator
source myenv/bin/activate
python3 subAlljob.py --language fa --directory /mnt/data/saberprojects/iranseda-crawler-golang-/downloads/
```

### پارامترها

- `--language`: زبان زیرنویس (`fa`, `ar`, `multi`)
- `--directory`: مسیر پوشه دانلود

## ⏰ زمان‌بندی

- **زمان‌بندی**: هر 5-6 ساعت
- **وابستگی**: باید بعد از مرحله دانلود (مرحله 2) اجرا شود

## 📊 ساختار فایل‌ها

```
downloads/
├── radio-maaref-03-11-28-15-00.mp3
└── radio-maaref-03-11-28-15-00.srt  ← خروجی این مرحله
```

## 🔍 بررسی خروجی

### فرمت SRT

```srt
1
00:00:00,000 --> 00:00:05,000
متن زیرنویس اول

2
00:00:05,000 --> 00:00:10,000
متن زیرنویس دوم
```

## 🐛 عیب‌یابی

### خطا: "Model not found"
- مطمئن شوید مدل‌های ASR نصب شده‌اند
- مسیر مدل‌ها را در تنظیمات بررسی کنید

### خطا: "GPU not available"
- اگر از GPU استفاده می‌کنید، دسترسی GPU را بررسی کنید
- ممکن است نیاز به CPU fallback باشد

### فایل‌های `.srt` تولید نمی‌شوند
- لاگ‌های n8n را بررسی کنید
- فایل صوتی را تست کنید (ممکن است خراب باشد)
- فضای دیسک را بررسی کنید

## 📝 یادداشت‌ها

- این مرحله **re-entrant** است - می‌تواند چندین بار اجرا شود بدون تولید تکراری
- فایل‌های `.srt` با همان نام فایل صوتی (با پسوند `.srt`) ذخیره می‌شوند
- کیفیت زیرنویس به کیفیت صدا و مدل ASR بستگی دارد

## 🔗 لینک‌های مرتبط

- [مستندات مرحله 3](workflows/03_subtitle_generation.md)
- [مستندات مرحله 4 - پاک‌سازی](workflows/04_full_text_cleanup.md)

