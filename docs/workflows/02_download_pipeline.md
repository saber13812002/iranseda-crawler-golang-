# مرحله ۲ – دانلود از دیتابیس / Stage 2 – DB-driven Downloads

## 🎯 هدف / Goal
- تبدیل رکوردهای `radio_program_sessions` به فایل‌های صوتی واقعی در پوشه `downloads/` و ثبت متادیتای فایل.

## 🧱 اجزای اصلی / Core Components
- `download_db.go`: اجرای حلقه دانلود بر اساس وضعیت `is_downloaded`.
- دیتابیس MySQL (`radio_program_sessions` و ستون‌های `link`, `filename`, `is_downloaded`).
- n8n workflow `download_db_go.json`: اجرای زمان‌بندی‌شده (`go run download_db.go` هر ۲ ساعت).
- مسیر ذخیره‌سازی `./downloads` (به اشتراک با مراحل زیرنویس و متن کامل).

## ⚙️ معماری و جریان داده / Architecture & Flow
1. **Read Queue**: اسکریپت با اتصال محیطی (`MYSQL_CONN`) به دیتابیس وصل شده و همه سطرهای `radio_program_sessions` را می‌خواند.
2. **Filter New Sessions**: تنها رکوردهایی که `is_downloaded = 0` دارند پردازش می‌شوند تا از دانلود تکراری جلوگیری شود.
3. **Normalize Link**: لینک نسبی (شامل `..`) به URL کامل `https://radio.iranseda.ir/...` تبدیل می‌شود.
4. **Resolve Media URL**: تابع `extractDownloadLinkAndFilename` صفحه آرشیو را پارس کرده و آدرس واقعی فایل (معمولاً `DLFile/?VALID=TRUE&vid=...`) را استخراج می‌کند.
5. **Download & Persist**: فایل با HTTP GET گرفته می‌شود، نام خروجی از هدر `Content-Disposition` استخراج و در `downloads/` ذخیره می‌گردد.
6. **Update State**: پس از موفقیت، `filename` و `is_downloaded=1` در دیتابیس ثبت می‌شود تا مراحل بعدی بدانند فایل آماده است.

## 🔗 ارتباط با مراحل دیگر / Relationships
- ورودی: رکوردهای جدید از مرحله ۱.
- خروجی: فایل‌های `.mp3` در `downloads/` برای مرحله ۳ (تولید زیرنویس) و متادیتای `filename` برای مرحله ۶ (لینک‌دهی در HTML).

## 🛠️ تنظیمات و متغیرها / Configuration
- نیازمند `.env` با متغیر `MYSQL_CONN` به شکل `user:pass@tcp(host:port)/radio`.
- دسترسی نوشتن به فولدر `downloads/`؛ n8n روی سرور باید همین مسیر را داشته باشد.
- در صورت نیاز به پراکسی یا timeout سفارشی، باید به `http.Client` اضافه شود (فعلاً استفاده نشده است).

## 🧪 تست و مانیتورینگ / Testing & Monitoring
- اجرای دستی: `go run download_db.go` پس از `source .env`.
- برای دیباگ لینک خاص، مقدار `originalLink` را چاپ و در مرورگر بررسی کنید.
- برای جلوگیری از ریت‌لیمیت سرور ایران‌صدا، در صورت افزایش حجم دانلود، تاخیر بین درخواست‌ها اضافه کنید (TODO).

## ⚠️ نکات نگهداری / Maintenance Notes
- اگر ساختار HTML سایت تغییر کند (کلاس `.col-plus.page-loding`)، تابع استخراج لینک باید به‌روزرسانی شود؛ این فایل و مستند را هم‌زمان اصلاح کنید.
- هر زمان مکان ذخیره فایل یا نام شاخه عوض شود، مسیر در این فایل و در `generate_site.py` (تابع `find_subtitles_for_session`) باید هماهنگ شود.

## 📝 یادداشت به‌روزرسانی / Update Memo
- تغییر هر کدام از ستون‌های `filename` یا `is_downloaded`، نیازمند ثبت در این سند است تا تیم n8n و توسعه‌دهندگان از تاثیر آن مطلع شوند.

