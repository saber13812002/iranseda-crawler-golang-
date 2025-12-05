# ⬇️ Downloader - دانلود فایل‌های صوتی

## 📋 نمای کلی

اسکریپت Go که لینک‌های ثبت شده در دیتابیس را می‌خواند و فایل‌های صوتی MP3 را دانلود می‌کند.

## 📁 فایل

- **`download_db.go`** - اسکریپت اصلی دانلود (نسخه جدید با دیتابیس)
- **`download.go`** - نسخه قدیمی (deprecated - بدون دیتابیس)

## 🎯 عملکرد

### 1. خواندن صف دانلود
از جدول `radio_program_sessions` تمام رکوردهایی که `is_downloaded=0` هستند خوانده می‌شوند.

### 2. تبدیل لینک
لینک نسبی (مثل `../epgarchivePart/?VALID=TRUE&ch=14&e=123456`) به URL کامل تبدیل می‌شود:
```
https://radio.iranseda.ir/epgarchivePart/?VALID=TRUE&ch=14&e=123456
```

### 3. استخراج لینک دانلود
صفحه HTML پارس می‌شود و لینک دانلود واقعی از تگ `<a class="col-plus page-loding">` استخراج می‌شود.

### 4. دانلود فایل
- فایل با HTTP GET دانلود می‌شود
- نام فایل از هدر `Content-Disposition` استخراج می‌شود
- در پوشه `downloads/` ذخیره می‌شود

### 5. به‌روزرسانی دیتابیس
- `filename` در دیتابیس ثبت می‌شود
- `is_downloaded=1` تنظیم می‌شود

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
go run download_db.go
```

### اجرا از طریق n8n

Workflow: `n8n_workflows/download_db_go.json`
- **زمان‌بندی**: هر 2 ساعت
- **دستور**: `/usr/local/go/bin/go run download_db.go`
- **مسیر کاری**: ریشه پروژه

## ⚙️ تنظیمات

### فایل `.env`

```env
MYSQL_CONN=n8nuser:StrongPassword123!@tcp(localhost:3306)/radio
```

### پوشه دانلود

فایل‌ها در پوشه `./downloads/` ذخیره می‌شوند. اگر پوشه وجود نداشته باشد، به صورت خودکار ایجاد می‌شود.

## 📊 ساختار فایل‌ها

```
downloads/
├── radio-maaref-03-11-28-15-00.mp3
├── radio-maaref-03-11-28-15-00.srt  (بعد از مرحله 3)
├── radio-maaref-03-11-28-15-00.txt  (بعد از مرحله 4)
└── cleaned/
    ├── radio-maaref-03-11-28-15-00.srt
    └── radio-maaref-03-11-28-15-00.txt
```

## 🔍 منطق استخراج لینک

```go
doc.Find("a.col-plus.page-loding").Each(func(i int, s *goquery.Selection) {
    downloadURL, _ = s.Attr("href")
})
```

**⚠️ توجه**: اگر ساختار HTML سایت تغییر کند، این بخش باید به‌روزرسانی شود.

## 🐛 عیب‌یابی

### خطا: "Unable to extract download link"
- ساختار HTML صفحه را بررسی کنید
- ممکن است کلاس CSS تغییر کرده باشد
- صفحه را در مرورگر باز کنید و inspect کنید

### خطا: "Failed to download file"
- اتصال اینترنت را بررسی کنید
- ممکن است فایل حذف شده باشد
- Rate limiting سرور را بررسی کنید

### فایل‌های تکراری دانلود می‌شوند
- بررسی کنید `is_downloaded` به درستی به‌روزرسانی می‌شود
- ممکن است خطا در commit دیتابیس باشد

## 📝 یادداشت‌ها

- فقط فایل‌هایی که `is_downloaded=0` هستند دانلود می‌شوند
- نام فایل از هدر HTTP استخراج می‌شود (نه از URL)
- کاراکترهای نامعتبر در نام فایل (`/`, `:`) با `-` جایگزین می‌شوند

## 🔗 لینک‌های مرتبط

- [مستندات مرحله 2](workflows/02_download_pipeline.md)
- [مستندات مرحله 3 - زیرنویس](workflows/03_subtitle_generation.md)

