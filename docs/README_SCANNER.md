# 🔍 Scanner - اسکن لینک‌های قسمت‌ها

## 📋 نمای کلی

اسکریپت Go که برنامه‌های ثبت شده در دیتابیس را اسکن می‌کند و لینک‌های قسمت‌های جدید را پیدا و ثبت می‌کند.

## 📁 فایل

- **`scan.go`** - اسکریپت اصلی اسکن

## 🎯 عملکرد

### 1. خواندن برنامه‌ها از دیتابیس
از جدول `radio_programs` تمام برنامه‌های فعال (`is_legacy=0`) خوانده می‌شوند.

### 2. اسکن صفحات برنامه
برای هر برنامه:
- صفحه اصلی برنامه (`url`) باز می‌شود
- تمام لینک‌های `epgarchivePart` استخراج می‌شوند

### 3. ثبت لینک‌های جدید
- بررسی می‌شود آیا لینک قبلاً ثبت شده (`radio_program_sessions`)
- اگر جدید باشد، در جدول `radio_program_sessions` ثبت می‌شود

## 🔧 نصب و راه‌اندازی

### پیش‌نیازها

```bash
go mod download
```

### وابستگی‌ها (Go)

- `github.com/PuerkitoBio/goquery` - پارس HTML
- `github.com/go-sql-driver/mysql` - درایور MySQL
- `github.com/joho/godotenv` - مدیریت متغیرهای محیطی

## 🚀 اجرا

### اجرای دستی

```bash
go run scan.go
```

### اجرا از طریق n8n

Workflow: `n8n_workflows/scan_go_copy.json`
- **زمان‌بندی**: هر 2 ساعت
- **دستور**: `/usr/local/go/bin/go run scan.go`
- **مسیر کاری**: ریشه پروژه (برای دسترسی به `.env`)

## ⚙️ تنظیمات

### فایل `.env`

```env
MYSQL_CONN=n8nuser:StrongPassword123!@tcp(localhost:3306)/radio
```

یا به صورت جداگانه:
```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=n8nuser
DB_PASS=StrongPassword123!
DB_NAME=radio
```

## 📊 خروجی

### جدول `radio_program_sessions`

| ستون | توضیح |
|------|-------|
| `id` | شناسه یکتا |
| `program_id` | شناسه برنامه (FK به `radio_programs`) |
| `link` | لینک قسمت (مثل `../epgarchivePart/?VALID=TRUE&ch=14&e=123456`) |
| `filename` | نام فایل دانلود شده (بعد از دانلود پر می‌شود) |
| `is_downloaded` | وضعیت دانلود (0/1) |
| `created_at` | زمان ثبت |

## 🔍 منطق Deduplication

قبل از ثبت هر لینک، بررسی می‌شود:
```go
SELECT EXISTS(SELECT 1 FROM radio_program_sessions WHERE link=?)
```

اگر لینک وجود داشته باشد، ثبت نمی‌شود.

## 🐛 عیب‌یابی

### خطا: "MYSQL_CONN not found"
- فایل `.env` را بررسی کنید
- مطمئن شوید در مسیر کاری ریشه پروژه اجرا می‌شود

### خطا: "Failed to fetch program"
- اتصال اینترنت را بررسی کنید
- URL برنامه را در مرورگر تست کنید

### لینک‌های تکراری ثبت می‌شوند
- منطق `sessionExists` را بررسی کنید
- ممکن است لینک‌ها با کاراکترهای اضافی متفاوت باشند

## 📝 یادداشت‌ها

- این اسکریپت **idempotent** است
- فقط برنامه‌های فعال (`is_legacy=0`) اسکن می‌شوند
- لینک‌ها به صورت نسبی ذخیره می‌شوند (با `..` در ابتدا)

## 🔗 لینک‌های مرتبط

- [مستندات مرحله 1](workflows/01_scan_and_ingest.md)
- [مستندات مرحله 2 - دانلود](workflows/02_download_pipeline.md)

