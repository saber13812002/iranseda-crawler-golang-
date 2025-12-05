# 📋 وضعیت فایل‌ها - File Status

این سند وضعیت فایل‌های پروژه را مشخص می‌کند: فعال، deprecated، یا تست.

## ✅ فایل‌های فعال (Active)

### Python Scripts

| فایل | توضیح | استفاده |
|------|-------|---------|
| `crawler/crawler.py` | خزش و ثبت برنامه‌ها | ✅ فعال - هر 45 دقیقه |
| `generate_site.py` | تولید صفحات وب | ✅ فعال - هر 2 ساعت |
| `convert_srt_to_txt.py` | تبدیل SRT به TXT | ✅ فعال - دستی/خودکار |
| `config.py` | مدیریت تنظیمات | ✅ فعال - استفاده در generate_site |
| `run_generator.py` | اجرای generator | ✅ فعال - wrapper برای generate_site |

### Go Scripts

| فایل | توضیح | استفاده |
|------|-------|---------|
| `scan.go` | اسکن لینک‌های قسمت‌ها | ✅ فعال - هر 2 ساعت |
| `download_db.go` | دانلود از دیتابیس | ✅ فعال - هر 2 ساعت |

### Scripts

| فایل | توضیح | استفاده |
|------|-------|---------|
| `scripts/backfill_program_times.py` | بک‌فیل زمان‌بندی | ✅ فعال - دستی/دوره‌ای |
| `scripts/notify_telegram.py` | اطلاع‌رسانی تلگرام | ✅ فعال - در صورت نیاز |
| `scripts/notify_messenger.py` | اطلاع‌رسانی Messenger | ✅ فعال - در صورت نیاز |
| `scripts/telegram_get_chat_id.py` | دریافت Chat ID | ✅ فعال - ابزار کمکی |
| `scripts/process_failed_ffmpeg.py` | پردازش فایل‌های failed | ✅ فعال - در صورت نیاز |

### Configuration

| فایل | توضیح | استفاده |
|------|-------|---------|
| `config.py` | مدیریت تنظیمات | ✅ فعال |
| `.env` | متغیرهای محیطی | ✅ فعال |
| `env.local.example` | نمونه تنظیمات local | ✅ فعال |
| `env.server.example` | نمونه تنظیمات server | ✅ فعال |
| `env.production.example` | نمونه تنظیمات production | ✅ فعال |

### Database

| فایل | توضیح | استفاده |
|------|-------|---------|
| `radio.sql` | ساختار دیتابیس | ✅ فعال |
| `radio_programs.sql` | ساختار جدول برنامه‌ها | ✅ فعال |
| `migrations/2025-11-19_program_legacy_columns.sql` | مایگریشن legacy | ✅ فعال |

### Documentation

| فایل | توضیح | استفاده |
|------|-------|---------|
| `readme.md` | README اصلی | ✅ فعال - به‌روزرسانی شده |
| `docs/workflows/*.md` | مستندات گردش کار | ✅ فعال |
| `docs/README_*.md` | مستندات کامپوننت‌ها | ✅ فعال - جدید |

### n8n Workflows

| فایل | توضیح | استفاده |
|------|-------|---------|
| `n8n_workflows/crawl_go_copy.json` | خزش برنامه‌ها | ✅ فعال |
| `n8n_workflows/scan_go_copy.json` | اسکن لینک‌ها | ✅ فعال |
| `n8n_workflows/download_db_go.json` | دانلود فایل‌ها | ✅ فعال |
| `n8n_workflows/srt.json` | تولید زیرنویس فارسی | ✅ فعال |
| `n8n_workflows/srt_farsi.json` | تولید زیرنویس فارسی (نسخه 2) | ✅ فعال |
| `n8n_workflows/srt_arabic.json` | تولید زیرنویس عربی | ✅ فعال |
| `n8n_workflows/srt_clean.json` | پاک‌سازی زیرنویس | ✅ فعال |
| `n8n_workflows/git_push.json` | همگام‌سازی Git | ✅ فعال |
| `n8n_workflows/generate_site_go.json` | تولید سایت | ✅ فعال |
| `n8n_workflows/telegram_notification.json` | اطلاع‌رسانی تلگرام | ✅ فعال |

---

## ⚠️ فایل‌های Deprecated

| فایل | توضیح | جایگزین | وضعیت |
|------|-------|----------|-------|
| `download.go` | دانلود بدون دیتابیس | `download_db.go` | ⚠️ Deprecated |
| `seek.go` | اسکریپت تست/دیباگ | - | ⚠️ Deprecated |
| `n8n_workflows/suball.json` | workflow قدیمی زیرنویس | `srt.json` | ⚠️ Deprecated |

### توضیحات

- **`download.go`**: نسخه قدیمی که بدون استفاده از دیتابیس کار می‌کرد. جایگزین شده با `download_db.go` که مدیریت بهتری از وضعیت دانلود دارد.

- **`seek.go`**: اسکریپت تست برای استخراج لینک MP3 از یک صفحه خاص. دیگر استفاده نمی‌شود.

- **`n8n_workflows/suball.json`**: workflow قدیمی برای تولید زیرنویس. جایگزین شده با `srt.json` و `srt_farsi.json`.

---

## 🧪 فایل‌های تست/دیباگ

| فایل | توضیح | استفاده |
|------|-------|---------|
| `test_n8n.py` | تست اتصال n8n | 🧪 تست |
| `web-viewer/` | نمایشگر وب (Go) | 🧪 تست/در حال توسعه |

---

## 📝 فایل‌های مستندات

| فایل | توضیح | وضعیت |
|------|-------|-------|
| `ENVIRONMENT_SETUP.md` | راه‌اندازی محیط | ✅ فعال |
| `NOTIFICATION_SETUP.md` | راه‌اندازی اطلاع‌رسانی | ✅ فعال |
| `NOTIFICATION_SUMMARY.md` | خلاصه اطلاع‌رسانی | ✅ فعال |
| `QUICK_START_NOTIFICATION.md` | راه‌اندازی سریع | ✅ فعال |

---

## 🔄 تغییرات اخیر

### 2025-11-19
- ✅ اضافه شدن ستون‌های `is_legacy` و `legacy_expires_at` به `radio_programs`
- ✅ ایجاد `migrations/2025-11-19_program_legacy_columns.sql`
- ✅ به‌روزرسانی `crawler/crawler.py` برای پشتیبانی از legacy
- ✅ ایجاد `scripts/backfill_program_times.py`

### 2025-01-XX (به‌روزرسانی مستندات)
- ✅ به‌روزرسانی `readme.md` با ساختار جدید
- ✅ ایجاد مستندات کامپوننت‌ها در `docs/README_*.md`
- ✅ ایجاد `docs/FILE_STATUS.md` (این فایل)

---

## 📌 نکات مهم

1. **فایل‌های deprecated**: می‌توانند حذف شوند اما برای تاریخچه نگه‌داری شده‌اند
2. **فایل‌های تست**: قبل از استفاده در production تست شوند
3. **مستندات**: همیشه بعد از تغییر کد به‌روزرسانی شوند

---

## 🔗 لینک‌های مرتبط

- [README اصلی](../readme.md)
- [مستندات گردش کار](workflows/)
- [مستندات کامپوننت‌ها](README_*.md)

