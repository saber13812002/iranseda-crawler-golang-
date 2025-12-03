# مرحله ۶ – تولید صفحات وب / Stage 6 – Site Generation

## 🎯 هدف / Goal
- ساخت خروجی استاتیک (`docs/` و `docs/programs/*.html`) از داده‌های دیتابیس و فایل‌های دانلود‌شده تا در GitHub Pages منتشر شود.

## 🧱 اجزای اصلی / Core Components
- `generate_site.py`: منطق اصلی تولید HTML و آمار.
- `run_generator.py`: راه‌اندازی‌گر محیطی که فایل مناسب `.env` را لود می‌کند.
- `config.py`: تعریف کلاس `Config` برای خواندن تنظیمات دیتابیس، GitHub و مسیرها.
- n8n workflow `generate_site_go.json`: اجرای زمان‌بندی‌شده اسکریپت با فعال‌سازی virtualenv (`venv/`) و ست‌کردن متغیرها.
- خروحی نهایی: `docs/index.html` و `docs/programs/<id>.html`.

## ⚙️ معماری و جریان داده / Architecture & Flow
1. **Environment Load**: `generate_site_go.json` محیط را آماده می‌کند (`ENVIRONMENT=server`, مقادیر DB/GitHub). به‌صورت محلی نیز می‌توان با `run_generator.py --env local` این کار را کرد.
2. **DB Fetch**: `generate_site.py` به MySQL وصل شده و `radio_programs` و جلسات مرتبط (`radio_program_sessions`, `radio_program_session_files`) را می‌خواند.
3. **File Linking**: تابع `find_subtitles_for_session` با استفاده از `config.paths['downloads']` وجود زیرنویس خام و متن کامل را بررسی کرده و لینک‌های GitHub Raw می‌سازد.
4. **Stats & Pages**: 
   - `render_index`: آمار زمانی تولید زیرنویس، آخرین برنامه‌های دارای متن کامل و جدول آخرین فایل‌های cleaned را نمایش می‌دهد.
   - برای هر برنامه، فایل مجزایی شامل متادیتا، جلسات و لینک‌های دانلود تولید می‌شود.
5. **Artifacts**: فایل `.nojekyll` ایجاد می‌شود تا ساختار پوشه در GitHub Pages حفظ شود.

## 🔗 ارتباط با مراحل دیگر / Relationships
- به داده‌های مرحله ۱ (برنامه‌ها)، مرحله ۲ (فایل‌های دانلود شده)، مرحله ۳ و ۴ (زیرنویس/متن کامل) و مرحله ۵ (Push به Git) وابسته است.
- خروجی این مرحله در مرورگر کاربر نهایی دیده می‌شود و مبنای گزارش‌دهی است.

## 🛠️ تنظیمات و متغیرها / Configuration
- متغیرهای کلیدی محیطی (نمونه در `env.local.example`, `env.server.example`, `env.production.example`):
  - `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME`
  - `GITHUB_USER`, `GITHUB_REPO`, `GITHUB_BRANCH`
  - `DOWNLOADS_PATH`, `DOCS_PATH`, `PROGRAMS_PATH` (در محیط production)
- اجرای محلی:
  ```bash
  python3 run_generator.py --env local
  # یا
  python3 run_generator.py --env-file path/to/custom.env
  ```

## 🧪 تست و مانیتورینگ / Testing
- پس از اجرای اسکریپت، فایل‌های تازه را در `docs/` بررسی و در مرورگر باز کنید.
- برای عیب‌یابی اتصال DB، می‌توانید `config.print_config()` را موقتاً فراخوانی کنید تا تنظیمات فعلی چاپ شوند.
- در صورت بروز خطا در n8n، لاگ اجرا مسیر فعال‌سازی venv و متغیرها را نشان می‌دهد؛ ابتدا اطمینان حاصل کنید python ماژول‌های `pymysql` و غیره را دارد.

## ⚠️ نکات نگهداری / Maintenance Notes
- هرگونه تغییر در ساختار HTML (کلاس‌ها، متن نمایش) باید در این سند ثبت شود تا تیم محتوا و UI مطلع باشند.
- اگر ستون‌های جدیدی به `radio_programs` اضافه شد که باید در سایت نشان داده شوند، منطق کوئری و تمپلیت را به‌روزرسانی و در این فایل توضیح دهید.
- برای سرعت بیشتر، می‌توان کش نتایج را پیاده‌سازی کرد؛ در صورت انجام، معماری را در این سند مستند کنید.

## 📝 یادداشت به‌روزرسانی / Update Memo
- تغییر در مسیرها، نام شاخه GitHub، یا اضافه‌شدن آمارهای جدید باید همین‌جا ثبت شود تا کل چرخه انتشار قابل پیگیری بماند.

