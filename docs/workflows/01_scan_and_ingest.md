# مرحله ۱ – اسکن لینک و ثبت برنامه / Stage 1 – Scan & Ingest

## 🎯 هدف / Goal
- تشخیص برنامه‌های جدید ایران‌صدا، ثبت متادیتا و ایجاد صف دانلود برای هر قسمت.

## 🧱 اجزای اصلی / Core Components
- `crawler/crawler.py`: خزش صفحات برنامه‌ و درج/به‌روزرسانی رکوردهای `radio_programs`.
- `crawler/crawl_links.txt`: ورودی دستی فهرست صفحات برنامه هدف.
- `scan.go`: پیمایش رکوردهای `radio_programs` و کشف لینک‌های `epgarchivePart` برای جدول `radio_program_sessions`.
- دیتابیس MySQL (`radio_programs`, `radio_program_sessions`).
- n8n workflows: `crawl_go_copy.json` (اجرای Python crawler) و `scan_go_copy.json` (اجرای اسکریپت Go).

## ⚙️ معماری و جریان داده / Architecture & Flow
1. **Seed Links**: فهرست برنامه‌ها در `crawler/crawl_links.txt` نگهداری می‌شود؛ هر خط یک صفحه `Program/?VALID=TRUE...` است.
2. **Program Crawl**: اسکریپت `crawler.py` با تریگر n8n (`crawl_go_copy`) هر ۴۵ دقیقه اجرا می‌شود، متادیتای برنامه (نام، توضیح، زمان پخش، شناسه رادیو) را استخراج و در `radio_programs` درج/به‌روزرسانی می‌کند.
3. **Session Discovery**: `scan.go` که توسط n8n (`scan_go_copy`) هر ۲ ساعت اجرا می‌شود، به ازای هر برنامه ذخیره‌شده وارد صفحه اصلی برنامه شده و لینک‌های `epgarchivePart` را استخراج می‌کند.
4. **Deduplication**: قبل از درج، `scan.go` با `sessionExists` بررسی می‌کند تا لینک تکراری در `radio_program_sessions` ذخیره نشود.
5. **Queueing**: برای هر لینک جدید، رکوردی شامل `program_id`, `link`, `is_downloaded=0` ایجاد می‌شود تا مراحل بعدی (دانلود فایل صوتی) بتوانند وضعیت را دنبال کنند.

## 🔗 ارتباط با مراحل دیگر / Downstream Relationships
- خروجی `radio_programs` و `radio_program_sessions` ورودی مستقیم مرحله ۲ (دانلود) است.
- متادیتای ذخیره‌شده (نام، زمان، رادیو) در مرحله ۶ برای تولید صفحات HTML استفاده می‌شود.

## 🛠️ تنظیمات و پیش‌نیازها / Configuration
- فایل `.env` ریشه باید شامل `DB_HOST`, `DB_USER`, `DB_PASS`, `DB_NAME` باشد؛ `crawler.py` و `scan.go` هر دو از آن استفاده می‌کنند (Go از `godotenv`، Python از `dotenv`).
- برای اجرای Python crawler روی سرور، n8n ابتدا `crawler/venv` را فعال می‌کند؛ مطمئن شوید وابستگی‌های `requests`, `pymysql`, `beautifulsoup4`, `python-dotenv` نصب هستند.
- `scan.go` با مسیر `/usr/local/go/bin/go run scan.go` اجرا می‌شود؛ مسیر کاری n8n باید ریشه مخزن باشد تا `.env` پیدا شود.

## ✅ نگهداری و تست / Maintenance
- پس از افزودن برنامه جدید به `crawl_links.txt`، یک بار `python crawler/crawler.py` را محلی اجرا کنید تا صحت استخراج بررسی شود.
- برای تست `scan.go` روی یک برنامه خاص، کوئری `radio_programs` را محدود کرده یا به صورت موقت لیست را کوچک کنید.
- هنگام تغییر ساختار جدول یا نام ستون‌ها، این مستند و هر دو فایل (`crawler.py`, `scan.go`) باید هم‌زمان به‌روزرسانی شوند.

## 📝 یادداشت به‌روزرسانی / Update Memo
- هر تغییری در شِمای دیتابیس یا پارامترهای n8n (فواصل زمانی، مسیرها) باید همین فایل را به‌روزرسانی کند تا منبع واحد معماری باقی بماند.

