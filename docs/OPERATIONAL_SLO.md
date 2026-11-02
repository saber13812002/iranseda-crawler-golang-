# IRANSEDA — OPERATIONAL SLO

> سند رسمی شاخص‌های سلامت عملیاتی ایران‌صدا.
> آخرین به‌روزرسانی: 2026-11-02 — ثبت اولیه شاخص‌های مدیریتی (مراجع: `docs/prompts/016-stage1-execution-decision-and-slo.md` و الحاقیه 013، بخش 4).
>
> **قانون ثبت:** مقدار فعلی فقط با شواهد واقعی سرور ۵۳/۵۲ ثبت می‌شود (لاگ، DB، Prometheus، Git). حدس زده نمی‌شود.
> برای شاخص‌های درصدی، مخرج، پنجره زمانی و منبع داده باید تعریف شده باشد.

## 1. شاخص‌های پایش دائمی (تصمیم مدیر 2026-11-02)

| # | شاخص | هدف (SLO) | مخرج / پنجره / منبع داده | مقدار فعلی | وضعیت |
| - | ---- | --------- | ------------------------- | ---------- | ------ |
| 1 | فاصله Commitهای خودکار | حداکثر ۶۰ دقیقه (در صورت وجود تغییر واقعی) | پنجره: ۷ روز؛ منبع: Git history branch عملیاتی | <در انتظار اندازه‌گیری Stage 1/2> | ⬜ |
| 2 | اجرای Pipeline | هر ۳۰ دقیقه | پنجره: ۷ روز؛ منبع: لاگ اجرای Pipeline + متریک `pipeline_runs_total` | <در انتظار اندازه‌گیری> | ⬜ |
| 3 | تأخیر Reporter | حداکثر یک ساعت | پنجره: ۲۴ ساعت؛ منبع: لاگ Reporter + `reporter_last_success_timestamp` | <در انتظار اندازه‌گیری> | ⬜ |
| 4 | روزهای بدون تولید SRT | صفر روز بدون خروجی — **مشروط بر وجود ورودی قابل پردازش** (اگر Queue خالی/منبع جدید نباشد، صفر خرابی نیست ولی علت باید مستند شود) | پنجره: روزانه (Asia/Tehran)؛ منبع: DB رکوردهای subtitled + فایل‌های SRT واقعی | <در انتظار اندازه‌گیری> | ⬜ |
| 5 | انتشار سایت | تطبیق Hash محتوای عمومی (GitHub Pages) با Commit منتشرشده | هر Publish؛ منبع: Hash Blob commit vs Hash فایل زنده | <در انتظار اندازه‌گیری> | ⬜ |
| 6 | سلامت صف | عدم توقف غیرعادی + روند قابل اندازه‌گیری تخلیه صف (pending_download / pending_transcribe) | پنجره: ۲ ساعت؛ منبع: DB وضعیت Session + متریک‌های Queue | <در انتظار اندازه‌گیری> | ⬜ |

**قید اعتبارسنجی:** ارقام بالا «معیار اولیه پیشنهادی» مدیر هستند. ایجنت باید با ظرفیت واقعی سیستم (GPU، ASR، شبکه) اعتبارسنجی کند و در صورت مغایرت، پیشنهاد اصلاح را با شواهد در همین سند ثبت کند — نه اینکه اعداد را بدون مدرک به «موفق» تغییر دهد.

## 2. شاخص‌های SLO تکمیلی (از الحاقیه 013 — بخش 4.1)

| شاخص | هدف |
| ----- | --- |
| Pipeline execution | هر ۳۰ دقیقه |
| Pipeline success | حداقل ۹۹٪ در بازه ۷ روزه (مخرج: کل اجراها؛ منبع: `pipeline_runs_total` / `pipeline_runs_failed_total`) |
| Reporter execution | طبق زمان‌بندی مصوب |
| Site refresh | حداکثر ۶۰ دقیقه |
| Automatic Git publication | حدود هر ۶۰ دقیقه در صورت وجود تغییر واقعی |
| Daily SRT production | هدف اولیه: ۵ تا ۱۰ **برنامه متمایز** دارای خروجی SRT در روز (نه ۵ تا ۱۰ فایل از یک برنامه) |
| Zero-output days | صفر روز بدون خروجی در حالت سلامت و وجود کار قابل پردازش |
| Queue progress | عدم توقف غیرموجه |
| Public site freshness | تطبیق با آخرین انتشار موفق |
| Duplicate episodes | صفر |
| Data loss | صفر |

## 3. متریک‌های لازم برای اندازه‌گیری SLO

### Pipeline
`pipeline_runs_total`, `pipeline_runs_failed_total`, `pipeline_runs_no_new_work_total`, `pipeline_last_success_timestamp`, `pipeline_duration_seconds`, `download_success_total`, `download_failed_total`, `transcription_success_total`, `transcription_failed_total`

### Queue
`pending_download`, `pending_transcribe`, `transcribing`, `failed_permanent`

### تولید
`srt_produced_today`, `srt_produced_yesterday`, `srt_produced_last_7d`, `srt_produced_last_30d`, `active_programs`, `programs_with_srt_today`, `programs_with_zero_output`, `last_srt_timestamp`

### انتشار
`last_git_commit_timestamp`, `last_git_push_timestamp`, `git_push_failures_total`, `last_site_publish_timestamp`, `site_hash_matches_pushed_commit`, `reporter_last_success_timestamp`, `pages_staleness_seconds`

> نام متریک‌ها باید با نام‌های موجود در Prometheus تطبیق داده شود و متریک تکراری ساخته نشود (قانون B11/013).

## 4. Operational Health Score (امتیاز مرکب از ۱۰۰)

| جزء | امتیاز |
| --- | ------ |
| Pipeline و Worker | ۳۰ |
| تولید واقعی SRT | ۲۵ |
| Commit و انتشار سایت | ۲۰ |
| Reporter و گزارش‌ها | ۱۵ |
| Grafana و هشدارها | ۱۰ |
| **جمع** | **۱۰۰** |

> این امتیاز در Grafana نمایش داده می‌شود ولی **جایگزین معیارهای مستقل نیست**؛ سلامت Git نباید خرابی تولید SRT را پنهان کند.

## 5. تاریخچه تغییرات SLO

| تاریخ | تغییر | مرجع |
| ----- | ----- | ---- |
| 2026-11-02 | ثبت اولیه ۶ شاخص پایش دائمی + SLO تکمیلی + Health Score | `docs/prompts/016-stage1-execution-decision-and-slo.md` |
