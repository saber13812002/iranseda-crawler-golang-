# مرحله ۳ – تولید زیرنویس / Stage 3 – Subtitle Generation

## 🎯 هدف / Goal
- تولید خودکار فایل‌های زیرنویس (SRT) برای هر فایل صوتی دانلود‌شده و قرار دادن آن‌ها در `downloads/`.

## 🧱 اجزای اصلی / Core Components
- n8n workflows:
  - `srt.json`: اجرای `subAlljob.py` با زبان فارسی (`--language fa`).
  - `srt_farsi.json`, `srt_arabic.json`: کانفیگ‌های زبان دیگر (در صورت نیاز).
  - `suball.json`: نسخه غیرفعال (legacy) از دستور بالایی.
- محیط Python خارجی: `/mnt/data/saberprojects/automated-multi-step-content-processing-and-seo-optimization-system/Subtitle-Generator`.
- دایرکتوری ورودی/خروجی: `iranseda-crawler-golang-/downloads/` (فایل‌های .mp3 و خروجی .srt).

## ⚙️ معماری و جریان داده / Architecture & Flow
1. **Trigger**: n8n هر ۵–۶ ساعت یک اجرا را زمان‌بندی می‌کند (بسته به workflow).
2. **Environment Prep**: دستور SSH فعال‌سازی `myenv/bin/activate` در ریپوی Subtitle-Generator را انجام می‌دهد.
3. **Batch Processing**: اسکریپت `subAlljob.py` دایرکتوری `downloads` را اسکن کرده و برای هر فایل صوتی بدون زیرنویس، مدل ASR مناسب را اجرا می‌کند.
4. **Output Placement**: فایل‌های `.srt` در همان پوشه کنار فایل صوتی ذخیره می‌شوند (و نام فایل مشابه است).
5. **Re-entrancy**: اسکریپت کتابخانه‌ای است و باید از تولید دوباره فایل‌های موجود جلوگیری کند (در حال حاضر توسط خود ابزار مدیریت می‌شود؛ در صورت تغییر رفتار باید بررسی شود).

## 🔗 ارتباط با مراحل دیگر / Relationships
- ورودی: فایل‌های صوتی از مرحله ۲.
- خروجی: فایل‌های `.srt` برای مرحله ۴ (پاک‌سازی و تبدیل به متن کامل) و مرحله ۶ (نمایش لینک دانلود زیرنویس خام).

## 🛠️ تنظیمات و متغیرها / Configuration
- پارامترهای کلیدی subAlljob:
  - `--language`: `fa`, `ar`, `multi` بسته به workflow.
  - `--directory`: مسیر کامل `downloads/`.
- برای افزودن زبان جدید، workflow n8n جدیدی با همان دستور و پارامتر زبان ایجاد کنید و در این سند ثبت نمایید.

## 🧪 تست و مانیتورینگ / Testing
- اجرای دستی روی سرور:  
  `bash -c "cd /mnt/.../Subtitle-Generator && source myenv/bin/activate && python3 subAlljob.py --language fa --directory /mnt/.../downloads/"`
- لاگ‌های خطا در n8n ذخیره می‌شوند؛ در صورت Fail، بررسی کنید مدل‌ها یا GPU در دسترس باشند.

## ⚠️ نکات نگهداری / Maintenance Notes
- تغییر ساختار دایرکتوری یا جابه‌جایی `downloads/` باید با پارامتر `--directory` هماهنگ شود.
- اگر ابزار Subtitle-Generator به نسخه جدیدی ارتقا یافت، این سند باید نسخه و پیش‌نیازهای جدید (مدل، حافظه، GPU) را منعکس کند.
- برای عملکرد بهتر، می‌توان اجرای workflow را پس از اتمام مرحله ۲ تریگر کرد (TODO: وابستگی n8n).

## 📝 یادداشت به‌روزرسانی / Update Memo
- هر تغییری در دستور n8n یا مسیر ابزار خارجی باید در این فایل درج شود تا traceability زنجیره زیرنویس حفظ گردد.

