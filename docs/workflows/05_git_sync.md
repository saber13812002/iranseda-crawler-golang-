# مرحله ۵ – همگام‌سازی Git روی سرور / Stage 5 – Server Git Sync

## 🎯 هدف / Goal
- اطمینان از اینکه مخزن سرور همواره با شاخه ریموت (`download-db`) هماهنگ است و خروجی‌های جدید (فایل‌های دانلود، متن کامل، صفحات تولیدشده) به GitHub پوش داده می‌شوند.

## 🧱 اجزای اصلی / Core Components
- n8n workflow `git_push.json`: شامل `Schedule Trigger` و نود `SSH`.
- اسکریپت دستوراتی که در سرور اجرا می‌شوند:
  ```bash
  set -e
  cd /mnt/data/saberprojects/iranseda-crawler-golang-/
  git fetch origin download-db
  git reset --hard origin/download-db
  git add .
  git commit -m "auto update from n8n" || echo "No changes to commit"
  git push origin download-db
  ```
- احراز هویت SSH (`SSH new server`) برای دسترسی به سرور و GitHub.

## ⚙️ معماری و جریان داده / Architecture & Flow
1. **Trigger**: هر ۹۰ دقیقه اجرا می‌شود (قابل تغییر در `Schedule Trigger`).
2. **Hard Reset**: ابتدا شاخه محلی با `git reset --hard origin/download-db` پاک‌سازی می‌شود تا تعارض‌های محلی حذف شوند.
3. **Staging Outputs**: تمام فایل‌های پروژه (دانلودها، cleaned، docs) stage می‌شوند.
4. **Conditional Commit**: اگر تغییری وجود نداشته باشد، پیام `No changes to commit` چاپ می‌شود و مرحله commit نادیده گرفته می‌شود.
5. **Push**: در صورت وجود تغییر، commit جدید به `origin/download-db` ارسال می‌شود؛ این شاخه برای GitHub Pages و بکاپ فایل‌ها استفاده می‌شود.

## 🔗 ارتباط با مراحل دیگر / Relationships
- تمام مراحل ۱ تا ۴ داده‌هایی تولید می‌کنند که باید در Git ذخیره شوند.
- مرحله ۶ (تولید سایت) برای انتشار در GitHub Pages به خروجی این Sync وابسته است.

## 🛠️ تنظیمات و مراقبت‌ها / Configuration & Care
- این فرآیند destructive است (reset hard). اگر قصد دارید تغییر دستی در سرور نگه دارید، پیش از اجرای خودکار commit کنید یا workflow را موقتاً غیرفعال نمایید.
- در صورت تغییر نام شاخه، دستور `git fetch` و `git push` را در workflow و این سند به‌روزرسانی کنید.
- مطمئن شوید کاربر سرور دارای SSH key یا Personal Access Token معتبر برای push است.

## 🧪 تست و مانیتورینگ / Testing
- اجرای دستی دستور فوق روی سرور (با همان کاربر n8n) قبل از فعال‌سازی workflow.
- بررسی لاگ n8n برای پیام‌های خطا (مثلاً `permission denied`, `fatal: could not read from remote repository`).

## ⚠️ نکات نگهداری / Maintenance Notes
- برای جلوگیری از رشد مخزن به علت فایل‌های حجیم، سیاست پاکسازی `downloads/` یا استفاده از Git LFS را درنظر بگیرید (TODO).
- هر تغییری در ساختار دایرکتوری که باید در Git نگهداری شود (مثلاً اضافه شدن `downloads/processed`) را اینجا مستند کنید.

## 📝 یادداشت به‌روزرسانی / Update Memo
- اگر بازه زمانی trigger یا فرمان Git تغییر کرد، این فایل باید بلافاصله به‌روزرسانی شود تا نقش آن در گردش‌کار مشخص بماند.

