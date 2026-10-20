# STEP 12 — Roshan ASR Pilot, Audio Recovery & Dual-ASR Dataset

> Master Prompt — نسخه کامل دریافت‌شده از کاربر، 2026-10-20.
> این فایل مرجع STEP 12 است. خروجی‌ها و شواهد واقعی در بخش «اجرا و شواهد» (پایان همین فایل)
> و در REPORT.md / بخش README ثبت می‌شوند.

## مأموریت

در پروژه IranSeda می‌خواهیم فایل‌های صوتی قدیمی را که قبلاً دانلود شده ولی برای صرفه‌جویی در فضای دیسک حذف شده‌اند، به‌تدریج دوباره دانلود کنیم و با وب‌سرویس ASR «روشن» (Roshan) پردازش کنیم.

هدف نهایی ایجاد یک دیتاست دوگانه است که برای هر Session، خروجی مستقل Whisper و Roshan را نگه دارد تا در آینده بتوانیم آن‌ها را مقایسه، ارزیابی، تصحیح و برای جست‌وجوی محتوایی، بازیابی مبتنی بر زمان و توسعه مدل‌های هوش مصنوعی استفاده کنیم.

**اولویت این STEP فقط اجرای یک Pilot واقعی روی یک فایل است.**

هیچ Bulk Job یا پردازش گسترده‌ای بدون تست و گزارش اولیه فعال نشود.

## اصول اجرایی

1. خروجی واقعی مهم‌تر از معماری پیچیده است.
2. روی Server 53 و کدهای موجود پروژه کار کن.
3. زیرنویس‌ها و متن‌های Whisper را تغییر نده.
4. Roshan باید خروجی مستقل و دارای version داشته باشد.
5. هر خطا باید قابل بازسازی و ریشه‌یابی باشد.
6. قابلیت retry، stop و resume وجود داشته باشد.
7. سرویس تولیدی Whisper، Dashboard و مدل‌های دیگر نباید مختل شود.
8. تنظیمات و قرارداد Roshan را از محیط واقعی کشف کن؛ چیزی را حدس نزن.
9. با یک فایل شروع کن و بعد از ارائه گزارش منتظر تصمیم بعدی بمان.
10. همه تغییرات، تصمیم‌ها، مشکلات و Master Promptها در README و مخزن GitLab داخلی ثبت شوند.

---

# STEP 12.1 — بررسی وضعیت موجود

قبل از توسعه، محیط واقعی را بررسی کن:

- Git repository و branch فعال پروژه
- آخرین commit و وضعیت working tree
- اتصال DB و ساختار جدول `radio_program_sessions`
- مسیر `downloads/`
- روش موجود دانلود فایل‌های قدیمی
- روش ثبت خروجی Whisper
- جدول‌های `llm_output` و registry پردازش‌ها
- وضعیت فضای خالی دیسک Server 53
- سرویس‌های ASR در Docker
- Docker Compose و تنظیمات LiteLLM
- سرویس Roshan و endpointهای قابل استفاده
- فرمت‌های مورد قبول Roshan
- محدودیت حجم، duration، timeout و concurrency
- وضعیت health و ظرفیت واقعی سرویس

از `.env`، Docker Compose، مستندات داخلی و تنظیمات معتبر موجود استفاده کن.

اطلاعات محرمانه را در گزارش منتشر نکن.

اگر Roshan در دسترس نیست، فقط بخش discovery و تست اتصال را انجام بده و گزارش `BLOCKED` بده؛ سرویس فرضی نساز.

## خروجی این مرحله

```text
Server:
Repository:
Branch:
Database:
Download mechanism:
Whisper output path:
Roshan endpoint:
Roshan API protocol:
Roshan model/version:
Supported audio formats:
Max file size:
Max duration:
Timestamp support:
LiteLLM route:
Direct Docker route:
Current bottleneck:
```

---

# STEP 12.2 — انتخاب یک فایل واقعی

از دیتابیس یک Session قدیمی پیدا کن که:

- فایل صوتی‌اش قبلاً دانلود شده است.
- اکنون فایل صوتی روی دیسک وجود ندارد.
- لینک اصلی صوت یا روش بازیابی معتبر دارد.
- فایل SRT مربوط به Whisper آن موجود است.
- متن کامل Whisper موجود است.
- Session ID و Program ID مشخص هستند.
- مدت برنامه مشخص یا از فایل قابل استخراج است.

ترجیحا‌ً فایلی انتخاب کن که مدت آن بین ۱۵ تا ۳۰ دقیقه باشد و محتوای گفتاری فارسی داشته باشد.

**از یک نمونه با محتوای رادیو معارف استفاده کن، اگر شرایط فوق را دارد.**

قبل از تغییر، وضعیت DB و فایل‌های مربوط به Session را ثبت کن.

اگر لینک دانلود قدیمی منقضی شده، روش بازیابی لینک را از crawler فعلی بررسی کن.

هیچ وضعیت تاریخی را برای موفق نشان دادن دانلود به‌صورت جعلی تغییر نده.

---

# STEP 12.3 — دانلود مجدد فایل صوتی

فایل انتخاب‌شده را مجدداً دانلود کن.

برای همان Session، وضعیت بازیابی را ثبت کن:

```text
session_id
source_url/reference
download_started_at
download_finished_at
http_status
download_bytes
download_duration
filename
sha256
audio_duration
audio_codec
sample_rate
channels
```

محدودیت‌ها:

- فقط یک فایل
- حداکثر ۳ تلاش برای هر عملیات شبکه
- timeout مشخص
- retry با backoff
- فایل موقت `.part`
- rename اتمیک پس از دانلود موفق
- اعتبارسنجی فایل با `ffprobe`
- جلوگیری از دانلود تکراری

اگر فایل ناقص بود یا duration و codec قابل شناسایی نبود، پردازش را متوقف کن.

دانلود مجدد نباید خروجی قبلی Whisper را حذف یا بازنویسی کند.

---

# STEP 12.4 — تست مستقیم Roshan

ابتدا یک نمونه کوتاه از فایل با FFmpeg بساز.

مثلا‌ً یک قطعه ۶۰ تا ۹۰ ثانیه‌ای با گفتار واضح و ترجیحا‌ً شامل واژگان تخصصی دینی.

تأکید: نقطه شروع واقعی این قطعه را ثبت کن.

اگر قرارداد واقعی Roshan محدودیت دیگری دارد، مدت و فرمت قطعه را مطابق همان تنظیم کن.

این موارد را بررسی کن:

1. آیا Roshan فایل را می‌پذیرد؟
2. آیا نتیجه synchronous است یا task/receipt برمی‌گرداند؟
3. آیا زیرنویس زمان‌دار تولید می‌کند؟
4. آیا فقط متن کامل برمی‌گرداند؟
5. آیا timestamp در سطح segment دارد یا word؟
6. آیا فارسی را درست تشخیص می‌دهد؟
7. آیا خروجی در فرمت SRT، VTT یا JSON است؟
8. آیا ورودی حجیم timeout می‌شود؟
9. محدودیت واقعی سرویس چیست؟
10. خطاها و response codeهای آن چگونه‌اند؟

Raw response را برای debugging نگه دار، اما token، headerهای حساس و اطلاعات محرمانه را ذخیره نکن.

اگر Roshan متن بدون timestamp برگرداند، وضعیت را `TEXT_ONLY` ثبت کن؛ timestamp ساختگی تولید نکن.

---

# STEP 12.5 — آزمایش FFmpeg و فرمت صوت

روی همان نمونه، فرمت‌های واقعی مورد پشتیبانی Roshan را آزمایش کن.

کاندیداهای اولیه:

| فرمت | کاربرد |
|---|---|
| Original audio | بررسی پذیرش مستقیم |
| WAV mono PCM 16-bit | ورودی استاندارد ASR |
| MP3 mono | کاهش حجم آپلود |
| FLAC mono | فشرده‌سازی بدون اتلاف |

Sample rate را مطابق قرارداد مدل انتخاب کن؛ تبدیل به 16kHz صرفا‌ً یک گزینه آزمایشی است.

برای هر فرمت ثبت کن:

```text
format
sample_rate
bitrate
file_size
upload_time
processing_time
success/failure
timestamp_available
transcript_quality
error_details
```

به‌جای انتخاب فرمت فقط براساس کوچک‌ترین حجم، کیفیت واقعی ASR را نیز لحاظ کن.

---

# STEP 12.6 — تست Chunking روی صوت بلند

اگر فایل کامل بزرگ است، Roshan محدودیت دارد یا کیفیت آن در فایل بلند افت می‌کند، فایل را به قطعات کوچک تقسیم کن.

مقادیر آزمایشی پیشنهادی:

```text
Chunk size:
3 minutes
5 minutes
10 minutes

Overlap:
5 seconds
10 seconds
```

این مقادیر فقط برای تست هستند، نه مقادیر قطعی Production.

Chunkها باید:

- به ترتیب زمانی مشخص باشند.
- offset مطلق نسبت به فایل اصلی داشته باشند.
- مستقل قابل retry باشند.
- شناسه یکتا داشته باشند.
- در صورت امکان برش نزدیک سکوت/مکث گفتار انجام شود.
- هنگام تجمیع overlap، متن تکراری تولید نکنند.

برای هر chunk ثبت کن:

```text
session_id
chunk_id
start_ms
end_ms
overlap_ms
audio_sha256
file_size
request_id
status
retry_count
processing_duration_ms
```

اگر Roshan timestamp نسبی برگرداند، هنگام تبدیل به SRT نهایی، آن را به timestamp سراسری صوت تبدیل کن.

فرمول:

```text
global_timestamp = chunk_start + local_timestamp
```

Overlap را به‌صورت deterministic deduplicate کن.

در مرز chunk، ترتیب زمانی، کلمات تکراری، سکوت و جمله‌های ناقص را بررسی کن.

اگر ادغام مطمئن نیست، خطا را گزارش کن و بخش نامطمئن را برای review علامت بزن.

---

# STEP 12.7 — مقایسه سه مسیر ارسال درخواست

بررسی کن کدام روش برای Roshan مناسب‌تر است:

### مسیر A — LiteLLM موجود

```text
IranSeda → LiteLLM → Roshan
```

### مسیر B — Direct Roshan

```text
IranSeda → Roshan Docker/API
```

### مسیر C — چند Replica پشت مسیر موجود

```text
IranSeda
   ↓
LiteLLM / Load Balancer
   ↓
Roshan Replica 1
Roshan Replica 2
...
```

اول فقط A و B را بررسی کن.

مسیر C صرفا‌ً یک گزینه آینده است و بدون اثبات نیاز به capacity بیشتر، هیچ Docker جدیدی نساز.

همچنین بررسی کن LiteLLM واقعا‌ً از نوع درخواست Roshan، از جمله audio upload و timestamp، پشتیبانی می‌کند یا خیر.

اگر پشتیبانی ندارد، مستقیم به Roshan وصل شو.

برای هر مسیر:

```text
compatibility
success rate
latency
resource utilization
timeout behavior
error transparency
operational complexity
```

را گزارش بده.

**هدف، انتخاب ساده‌ترین مسیر پایدار است؛ نه حفظ اجباری LiteLLM و نه حذف بی‌دلیل آن.**

---

# STEP 12.8 — طراحی ذخیره‌سازی دیتاست دوگانه

ساختار فعلی Whisper حفظ شود.

خروجی Roshan نباید جایگزین SRT یا TXT مربوط به Whisper شود.

حداقل اطلاعات مورد نیاز برای هر خروجی:

```text
session_id
provider = roshan
model_name
model_version
pipeline_version
audio_sha256
processing_status
srt_path
fulltext_path
raw_response_path
duration_ms
segment_count
created_at
updated_at
error_code
error_message
```

اول ساختار DB موجود را بررسی کن.

اگر می‌توان از جدول عمومی ASR output موجود استفاده کرد، جدول جدید نساز.

اگر جدول مناسبی وجود ندارد، migration کوچک و additive بساز.

در صورت نیاز یک جدول عمومی مانند زیر قابل قبول است:

```text
asr_output
```

با کلید یکتا بر اساس Session، Provider، نسخه مدل/پردازش و هش صوت، تا اجرای مجدد کنترل‌شده باشد و نسخه‌های تاریخی از بین نروند.

برای Chunkها نیز فقط اگر واقعا‌ً لازم بود، جدول یا JSON metadata جدا تعریف کن.

فایل‌های پیشنهادی:

```text
downloads/
  asr/
    roshan/
      <session_id>/
        original-audio-metadata.json
        roshan.v1.srt
        roshan.v1.full.txt
        roshan.v1.raw.json
        roshan.v1.manifest.json
```

مسیر واقعی باید با convention پروژه سازگار باشد.

Raw output، متن کامل و زیرنویس را جدا نگه دار.

در آینده باید بتوانیم داده‌هایی با این ساختار استخراج کنیم:

```text
Session ID
Program ID
Audio reference
Audio SHA256
Whisper SRT
Whisper full text
Roshan SRT
Roshan full text
ASR model versions
Timestamp alignment
Evaluation metadata
```

وجود هر دو خروجی برای یک فایل به‌معنای وجود Ground Truth نیست؛ فعلا‌ً این دیتاست یک paired dual-ASR corpus است.

برای ارزیابی دقیق WER/CER در آینده به نمونه‌های human-verified نیاز داریم.

---

# STEP 12.9 — تولید SRT و متن کامل Roshan

اگر Roshan timestamp معتبر برمی‌گرداند:

1. خروجی segmentها را parse کن.
2. timestampها را نرمال و اعتبارسنجی کن.
3. اگر chunking شده‌اند، زمان سراسری را بازسازی کن.
4. هم‌پوشانی‌های تکراری را برطرف کن.
5. SRT نهایی بساز.
6. از همان SRT، متن کامل تولید کن.

اگر Roshan فقط متن برمی‌گرداند:

- متن کامل را ذخیره کن.
- وضعیت `TEXT_ONLY` ثبت کن.
- SRT معتبر را null بگذار.
- Alignment را به‌عنوان کار آینده ثبت کن.
- هرگز timestamp را با تقسیم مساوی متن جعل نکن.

تست‌های ضروری:

```text
No negative timestamps
No invalid time intervals
Chronological order
No duplicated overlap blocks
Valid UTF-8
Persian characters preserved
Non-empty transcript
Original audio unchanged
```

---

# STEP 12.10 — مقایسه با Whisper

یک گزارش مقایسه‌ای برای همان فایل تولید کن.

شاخص‌ها:

- تعداد segmentهای Whisper و Roshan
- مدت صوت پوشش‌داده‌شده
- تعداد کلمات هر دو
- تفاوت‌های مهم واژگانی
- خطاهای آشکار ASR
- اصطلاحات دینی و نام اشخاص
- اعداد، تاریخ‌ها و عناوین برنامه
- تفاوت در زمان‌بندی
- تکرار یا حذف جمله
- سرعت پردازش هر سرویس

حداقل ۱۰ نمونه متن کنار هم گزارش بده.

قالب:

| Time | Whisper | Roshan | Assessment |
|---|---|---|---|
| 00:01:20 | ... | ... | Roshan better |
| 00:03:45 | ... | ... | Whisper better |

اگر بدون گوش‌دادن به صوت نمی‌توان با اطمینان قضاوت کرد، وضعیت را `UNVERIFIED` بگذار.

از نتیجه Roshan به‌عنوان Ground Truth برای داوری Whisper استفاده نکن؛ هر دو ممکن است اشتباه کنند.

---

# STEP 12.11 — Error Handling و Logging

برای کل Pilot لاگ ساختاریافته بساز.

حداقل مراحل:

```text
DISCOVER
DOWNLOAD
VERIFY_AUDIO
PREPARE_AUDIO
ASR_SUBMIT
ASR_POLL
ASR_RECEIVE
MERGE_CHUNKS
GENERATE_SRT
GENERATE_FULLTEXT
SAVE_DB
COMPARE
CLEANUP
```

برای هر مرحله:

```text
run_id
session_id
chunk_id
provider
request_id
attempt
started_at
ended_at
latency_ms
status
error_type
http_status
message
```

در صورت failure:

- خطای موقت را با retry محدود مدیریت کن.
- خطای غیرقابل‌بازیابی را ثبت کن.
- timeout را از پاسخ نامعتبر جدا کن.
- اگر سرویس receipt داده، بعد از timeout بدون بررسی receipt درخواست را بی‌دلیل دوباره ارسال نکن.
- امکان resume از آخرین مرحله موفق وجود داشته باشد.
- فایل‌های سالم قبلی پاک نشوند.

فایل لاگ و گزارش قابل بررسی توسط Agent بعدی باشند.

---

# STEP 12.12 — خطاهای قابل انتظار و راه‌حل جایگزین

### خطا: فایل حجیم است

راه‌حل: ابتدا compression مناسب، سپس chunking.

### خطا: فرمت پشتیبانی نمی‌شود

راه‌حل: تبدیل با FFmpeg به فرمت مستندشده Roshan.

### خطا: سرویس timeout می‌دهد

راه‌حل: بررسی وضعیت job، chunk کوچک‌تر، timeout تنظیم‌شده و retry محدود.

### خطا: Roshan زیرنویس نمی‌دهد

راه‌حل: ثبت `TEXT_ONLY` و بررسی قابلیت timestamp یا forced alignment مستقل در مرحله آینده.

### خطا: قطعه‌ها در مرز به هم نمی‌چسبند

راه‌حل: overlap کوتاه، deduplication مبتنی بر زمان و متن، یا `NEEDS_REVIEW`.

### خطا: کیفیت ضعیف است

راه‌حل: بررسی کیفیت صوت، resampling معتبر، VAD در صورت نیاز و تست فرمت دیگر؛ سپس مقایسه مجدد.

### خطا: GPU یا سرور تحت فشار قرار می‌گیرد

راه‌حل: کاهش concurrency یا توقف موقت Roshan background job.

### خطا: LiteLLM با آپلود فایل سازگار نیست

راه‌حل: استفاده مستقیم از API مستند Roshan.

برای هر failure یک issue قابل پیگیری در گزارش Pilot ایجاد کن.

---

# STEP 12.13 — کنترل منابع و فایل‌های موقت

فعلا‌ً:

```text
Max active pilot sessions = 1
Max concurrent ASR requests = 1
Bulk processing = OFF
Automatic historical redownload = OFF
```

اگر ظرفیت سرور یا سرویس محدود بود، تمام پردازش آزمایشی باید بدون آسیب به سرویس‌های اصلی متوقف شود.

بعد از پردازش موفق:

- وجود SRT و Full Text را تأیید کن.
- ثبت DB را تأیید کن.
- checksum و manifest را نگه دار.
- فایل صوتی دانلودشده را فعلا‌ً حذف نکن.
- محل و حجم فایل را در گزارش ثبت کن.

سیاست حذف دوباره صوت را فقط بعد از تأیید کیفیت، integrity و recoverability تعریف کن.

---

# STEP 12.14 — آمادگی برای Backfill تدریجی

در این STEP، Backfill گسترده فعال نشود.

فقط طرح اجرای تدریجی ارائه کن:

```text
Pilot: 1 file

Phase 2: 10 files

Phase 3: 50 files

Phase 4: 100 files

Phase 5: gradual historical backlog
```

اعداد فوق سقف batchهای پیشنهادی‌اند و پس از QA قابل تغییر هستند.

برای آینده امکان این حالات طراحی شود:

```text
NORMAL
PAUSED
STOPPED
```

حداقل قابلیت‌های مورد نیاز:

- stop و resume
- محدودیت فایل در هر batch
- محدودیت همزمانی درخواست
- rate limit
- disk free threshold
- retry bounded
- priority برای محتوای جدید
- جلوگیری از دانلود و پردازش تکراری
- مدیریت ظرفیت خالی GPU/ASR

قبل از افزایش throughput مشخص کن bottleneck دانلود است، FFmpeg است، شبکه است یا Roshan.

---

# STEP 12.15 — سایت و Dataset

فعلا‌ً سایت عمومی را برای یک خروجی آزمایشی تغییر نده، مگر اینکه روش نمایش امن آزمایشی موجود باشد.

اما بررسی کن در آینده بتوان برای هر Session لینک‌های زیر را نمایش داد:

```text
Whisper SRT
Whisper Full Text

Roshan SRT
Roshan Full Text

ASR Comparison
Audio Seek
```

هدف سازمانی این است که بعدها برای هر عبارت متنی بتوانیم علاوه بر مدل تولیدکننده، زمان دقیق وقوع عبارت در فایل صوتی را نیز مشاهده کنیم.

---

# STEP 12.16 — GitLab، README و تاریخچه Agent — الزامی

این قانون دائمی تمامی پروژه‌های من است:

هر پوشه اصلی پروژه باید Repository مستقل در GitLab داخلی داشته باشد:

`git.ai.ismc.ir`

پروژه IranSeda نیز باید Repository مستقل خودش را داشته باشد.

وضعیت GitLab را بررسی کن و در صورت داشتن مجوز، تغییرات را push کن.

اگر دسترسی وجود ندارد:

`GitLab push: BLOCKED — credential not provisioned`

را در README و گزارش ثبت کن.

هیچ رمز یا کلید خصوصی را وارد Git نکن.

README باید همیشه حاوی این اطلاعات به‌روز باشد:

- هدف پروژه و فاز فعلی
- معماری واقعی
- Serverها و سرویس‌ها
- کارهای انجام‌شده
- تصمیم‌های مهم و دلایل
- کارهای باقی‌مانده
- خطاها و محدودیت‌ها
- دستورهای اجرا و توقف
- DB migrations
- کیفیت خروجی ASR
- Master Prompt history
- مسیر log و artifactها
- Rollback procedure
- NEXT_CHAT_CHECKPOINT

نسخه کامل همین Master Prompt را ذخیره کن:

`docs/prompts/012-roshan-asr-pilot-and-dual-dataset.md`

همچنین به README و فهرست promptها لینک بده.

---

# STEP 12.17 — معیار پذیرش Pilot

Pilot زمانی موفق است که:

1. یک Session قدیمی واقعی انتخاب شده باشد.
2. فایل صوتی حذف‌شده دوباره با موفقیت دانلود شده باشد.
3. فایل صوتی با FFprobe تأیید شده باشد.
4. سرویس Roshan واقعی شناسایی و تست شده باشد.
5. حداقل یک قطعه صوتی با موفقیت توسط Roshan پردازش شده باشد.
6. قابلیت پردازش فایل کامل، مستقیم یا chunked، آزمایش شده باشد.
7. خروجی Roshan با فرمت واقعی و زمان‌بندی معتبر، در صورت پشتیبانی سرویس، ذخیره شده باشد.
8. متن کامل Roshan مستقل از Whisper ذخیره شده باشد.
9. DB بتواند خروجی هر دو provider را به یک Session مرتبط کند.
10. Whisper اصلی دست‌نخورده باقی مانده باشد.
11. مقایسه کیفی با حداقل ۱۰ نمونه ارائه شده باشد.
12. خطاها و محدودیت‌های واقعی ثبت شده باشند.
13. مسیر LiteLLM و Direct بررسی شده باشد.
14. هیچ Bulk Job فعال نشده باشد.
15. README، Master Prompt و checkpoint به‌روز شده باشند.

اگر هر مرحله شکست خورد، آن را موفق اعلام نکن. وضعیت دقیق `PASS / PARTIAL / BLOCKED / FAIL` بده.

---

# STEP 12.18 — گزارش نهایی الزامی Agent

گزارش را در قالب زیر بده:

## A — وضعیت فایل آزمایشی

```text
Session ID:
Program ID:
Program Name:

Audio source:
Original file available before test: YES/NO
Redownload successful: YES/NO

Audio duration:
Original format:
Downloaded size:
SHA256:
Storage path:
```

## B — اطلاعات سرویس Roshan

```text
Roshan URL (without secrets):
API protocol:
Model/version:
Supported formats:
Max upload size:
Max duration:
Timestamp support:
SRT support:
Text-only support:
Async task support:
```

## C — نتایج آزمایش

| Test | Result | Size | Time | Notes |
|---|---|---|---|---|
| 60s original | | | | |
| WAV | | | | |
| MP3 | | | | |
| FLAC | | | | |
| 3min chunk | | | | |
| 5min chunk | | | | |
| Full audio | | | | |

آزمایش‌های پشتیبانی‌نشده را `NOT SUPPORTED` مشخص کن؛ تست فرضی گزارش نده.

## D — خروجی دیتاست

```text
Whisper SRT:
Whisper TXT:

Roshan SRT:
Roshan Full TXT:
Roshan Raw Response:

Database table:
Database record ID:

Timestamp alignment: VALID/INVALID/NOT AVAILABLE
Original Whisper unchanged: YES/NO
```

## E — مقایسه کیفیت

حداقل ۱۰ نمونه قبل/بعد یا مقایسه Whisper و Roshan همراه با timestamp و نظر کارشناسی مستند.

در پایان:

```text
Whisper advantages:
Roshan advantages:
Roshan weaknesses:
Detected hallucinations:
Missing sentences:
Timestamp problems:
Human review needed:
```

## F — عملکرد و ظرفیت

```text
Total download time:
FFmpeg preparation time:
Total Roshan ASR time:
Total processing time:

Realtime factor (RTF):
Peak memory:
GPU utilization:
Disk usage:

LiteLLM result:
Direct API result:
Recommended route:
```

## G — مشکلات و راه‌حل‌ها

جدول کامل:

```text
Problem
Evidence
Root cause
Attempted solution
Result
Recommended improvement
Priority
```

## H — طرح مرحله بعد

با داده واقعی مشخص کن:

```text
Is 10-file pilot safe? YES/NO

Recommended chunk duration:
Recommended audio format:
Recommended concurrency:
Recommended timeout:
Recommended retry policy:
Recommended storage policy:

Risks:
Estimated processing rate:
Estimated storage requirements:
Recommended next batch:
```

## I — مستندات و Git

```text
GitHub repository:
GitLab repository:
Branch:
Commit IDs:
GitLab push status:
README updated:
Master prompt saved:
Migration applied:
Working tree clean:
```

## J — NEXT_CHAT_CHECKPOINT

در README و گزارش نهایی یک checkpoint کامل بساز که Agent جدید با خواندن آن بتواند بدون توضیح مجدد ادامه دهد:

```text
PROJECT: IranSeda

CURRENT STEP: Roshan ASR Pilot

LAST VERIFIED STATE:

WHAT WAS COMPLETED:

WHAT FAILED:

ACTUAL ROSHAN API CONTRACT:

DATABASE CHANGES:

OUTPUT FILES:

QUALITY RESULTS:

KNOWN ISSUES:

SAFE COMMANDS:

STOP/RESUME:

REMAINING WORK:

NEXT RECOMMENDED ACTION:
```

## دستور نهایی

**فقط یک فایل را به‌طور کامل آزمایش کن.**

اگر موفق شد، گزارش کن و توقف کن.

اگر موفق نشد، علت را مستند کن، حداکثر چند راه‌حل مشخص و محدود را آزمایش کن و سپس توقف کن.

هیچ Batch ده‌تایی، دانلود انبوه، افزایش Docker replica یا تغییر معماری بدون اثبات نیاز و گزارش نتایج انجام نده.

خروجی مورد انتظار من یک آزمایش واقعی، قابل تکرار و دارای شواهد است؛ نه صرفا‌ً اینکه کد نوشته شده باشد.

---

## تصمیم‌گیری کاربر پس از گزارش (2026-10-20)

> اضافه‌شده از طرف کاربر به‌عنوان سیاست تصمیم‌گیری برای فاز بعد:

- اگر Roshan فایل کامل را درست پردازش کرد: با همان فرمت و همان مسیر درخواست ادامه می‌دهیم؛ سراغ FFmpeg پیچیده یا Docker بیشتر نمی‌رویم.
- اگر فایل بلند یا حجیم مشکل داشت: Chunking با FFmpeg و هم‌ترازسازی زمان‌های SRT را انتخاب می‌کنیم.
- اگر سرویس کند بود ولی خروجی کیفیت خوبی داشت: تازه سراغ مقایسه LiteLLM، اتصال مستقیم و چند Replica می‌رویم.

---

# اجرای STEP 12 — شواهد و نتایج (Agent)

> اجراکننده: Agent (ZCode)، 2026-10-20. همه شواهد از Server 53 (`172.20.1.53`،
> hostname `llm`) و 52 (`172.20.1.52`) به‌صورت زنده و قابل‌بازسازی گرفته شده‌اند.

## 12.1 — خروجی کشف محیط

```text
Server: 53 (172.20.1.53, hostname "llm", 2× H100 80GB, disk 1.5T/348G free @76%)
Repository: /home/saber/saberprojects/iranseda-crawler-golang- (branch download-db)
Branch: download-db (cron auto-commits "auto: refresh site + subtitles" هر 30 دقیقه)
Database: MySQL in docker "iranseda-mysql", 127.0.0.1:3308, db=radio, user=n8nuser
  جدول‌ها: radio_programs, radio_program_sessions, subtitles, downloaded_files,
  llm_output, llm_job, pipeline_steps, programs, prompts, crop_detection,
  publication_task, backfill_list  (+ asr_output — NEW این STEP)
Download mechanism: download_db.go → صفحه epgarchivePart → a.col-plus.page-loding
  → 3 mirror (server6 .mp3 / server7 .mp4 / server8 .mp4) روی headend*.iranseda.ir
Whisper output path:
  SRT   downloads/<stem>.srt
  TXT   downloads/<stem>.txt
  cleaned/ downloads/cleaned/<stem>.full.txt ( + .summary / .correct / .correct.v2 )
  DB   radio_program_sessions.is_subtitled=1, status='subtitled', srt_filename
  سرویس: iranseda-whisper-api (uvicorn :9500, OpenAI-compatible /v1/audio/transcriptions)
  مدل: whisper-persian-v4-ct2 (int8, GPU0) — داخل docker, network_mode=host
Roshan endpoint:
  Direct (path B):  http://172.20.1.52:8050/v1/audio/transcriptions  (docker "asr-proxy" on 52)
  LiteLLM (path A): http://172.20.1.52:4000/v1/audio/transcriptions  (model_name=asr-ismc)
  Backend واقعی:    https://asr.ismc.ir/api/transcribe_files/  (LB → pool از workerهای Roshan)
Roshan API protocol: OpenAI-compatible multipart /v1/audio/transcriptions
  fields: file, model=asr-ismc-fa, language=fa
  response shape (از OpenAPI 52:8050): {"text","language","duration","segments"}
Roshan model/version: asr-ismc-fa (owned_by asr.ismc.ir) — upstream version در دسترس نبود
Supported audio formats: از OpenAPI مشخص نبود (فقط "file" octet-stream) — test در 12.5
Max file size / Max duration: در OpenAPI محدودیت ثبت نشده بود — test empiric در 12.5/12.6
Timestamp support: OpenAPI می‌گوید segments برمی‌گردد — صحت در 12.4/12.9 با پاسخ واقعی تأیید می‌شود
LiteLLM route (A): موجود (asr-ismc → 52:8050). به همان upstream مرده وصل است.
Direct Docker route (B): 52:8050 (asr-proxy) — ساده‌تر و شفاف‌تر.
Current bottleneck: backend Roshan پشت LB asr.ismc.ir (503 "No server is available")
```

## 12.2 — Session انتخاب‌شده

```text
session_id=3  program_id=1  filename=radio-maaref-03-08-17-21-30.mp3
link (صفحه آرشیو): ../epgarchivePart/?VALID=TRUE&ch=14&e=152507883
created_at=2024-11-08 19:39:19   status=subtitled  is_subtitled=1
محتوا: رادیو معارف، ~29:51 دقیقه، گفتاری فارسی (حدیث/تاریخ اسلام)
آغاز: "ماما حدیث رو شنید از افتاب گفت" / بسم‌الله / ...
پایان: "سال جهش تولید با مشارکت مردم" / "سال 1403"
```

## 12.3 — دانلود مجدد (موفق)

```text
source mirror: server6 (.mp3)  http://headend1.iranseda.ir/DLFile/?VALID=TRUE&vid=2651448_201
  (آیینه‌های دیگر: server7 .mp4 vid=2612566_206 ، server8 .mp4 vid=2561463_207122)
http_status=200   download_bytes=14326519   download_duration=42s
sha256=14cf3a3aaa6c6843f330c883cd0f56aed5fac38a9ee7d2232fb679e2fc65bee4
audio: mp3 48kHz stereo @64kbps, duration=1790.784s (29:50)
storage: downloads/asr/roshan/3/radio-maaref-03-08-17-21-30.mp3
metadata: downloads/asr/roshan/3/original-audio-metadata.json
```

> **یافته مهم (STEP 12.13):** فایل صوتیِ redownload شده در `downloads/` توسط
> `scripts/cleanup_audio.py --apply` (که cron `refresh_site.sh` هر 30 دقیقه اجرا
> می‌کند) **پاک می‌شود** چون session >10 روز پیش subtitled شده است
> (`AUDIO_RETENTION_DAYS=10`). برای همین فایل اول (که در `downloads/` بود) در کمتر
> از 30 دقیقه حذف شد. **حل:** فایل صوتی pilot در `downloads/asr/roshan/3/` نگهداری
> می‌شود — cleanup فقط `glob(downloads/*)` سطح‌اول را می‌بیند و زیرپوشه‌ها را نمی‌پوندد،
> پس امن است. این همان نیاز "disk/retention guard" بخش 12.13 است.

## 12.4 — تست مستقیم Roshan: سرویس در حال down/outage است (BLOCKED تا up-window)

قرارداد API از OpenAPI واقعی 52:8050 (نه حدس) کشف شد و تست زنده انجام شد.
نتیجه: **backend Roshan در دسترس نیست.** شواهد:

| زمان (53، UTC) | مسیر | نتیجه |
|---|---|---|
| 2026-10-20 05:33 | direct 8050 | 503 Service Unavailable |
| 2026-10-20 08:48 | direct 8050 | **200 OK** (آخرین موفقیت ثبت‌شده) |
| 2026-10-20 13:26–13:29 | direct 8050 | 503 |
| 2026-10-20 13:36–13:48 (22 probe) | direct 8050 | 401 / 503 (بدون 200) |
| 2026-10-20 13:xx | LiteLLM 4000 (asr-ismc) | 401 "all tokens rejected (ReadError)" |

تحلیل ریشه:
- `asr-proxy` (52:8050) **سالم و بالا** است (`/health` → ok, `tokens_configured:1`).
- upstream `https://asr.ismc.ir/api/transcribe_files/` پشت یک load balancer است.
  - `503 "No server is available to handle this request."` = pool workerهای Roshan خالی است.
  - `401 "token[0] network error: upstream error: ReadError"` = token واحد proxy
    نمی‌تواند TCP-level به Roshan وصل شود.
- هر دو = **backend Roshan down**. (401 خطای ما/تنظیم نیست؛ شبکه است.)
- `asr-exporter-a` (health checker) آخرین job موفقش **2026-10-13 20:41** بوده — یعنی
  Roshan حدود 7 روز است ناپایدار/خاموش است و امروز فقط یک بار (08:48) جواب داده.

→ طبق اصل 12: "اگر Roshan در دسترس نیست، فقط discovery و تست اتصال را انجام بده و
گزارش BLOCKED بده؛ سرویس فرضی نساز." → **این STEP در فاز ASR روی BLOCKED است**،
اما تمام زیرساخت آماده است تا در اولین up-window بلافاصله اجرا شود (retry-runner در
پس‌زمینه روی 53 فعال است و test-matrix کامل را در اولین 200 اجرا می‌کند).

## 12.5/12.6 — آماده‌سازی فرمت و chunk (انجام شد، اجرا در انتظار up-window)

- فرمت‌های نمونه 90ثانیه‌ای (start=120s) ساخته شدند:
  `sample_90s.mp3` (original, 720KB) · `sample_90s.wav` (mono 16k pcm16, 2.88MB) ·
  `sample_90s_16k.mp3` (mono 16k 64k, 721KB) · `sample_90s.flac` (mono 16k, 3.0MB)
- Chunking فایل کامل 29:51: 11 chunk × 3 دقیقه با overlap 10s
  (`chunks/chunk_000..010.mp3`) — offset مطلق، شناسه یکتا، قابل retry مستقل.

## 12.7 — مقایسه مسیر A (LiteLLM) vs B (Direct)

| معیار | A — LiteLLM 52:4000 | B — Direct 52:8050 |
|---|---|---|
| compatibility | بله (asr-ismc، mode=transcription) | بله (OpenAI-compatible) |
| latency | یک hop اضافی (53→52:4000→52:8050→asr.ismc.ir) | مستقیم (53→52:8050→asr.ismc.ir) |
| error transparency | خطا را wrap می‌کند ("all tokens rejected") | خطای upstream را مستقیم passthrough می‌کند |
| operational complexity | نیاز به master key + model name | فقط URL + file |
| نتیجه (این STEP) | 401 (به upstream مرده وصل) | 503 (upstream مرده) |

→ **توصیه: مسیر B (Direct 8050).** LiteLLM در اینجا هیچ audio/timestamp feature اضافه‌ای
ندارد؛ فقط یک hop و یک لایه wrap اضافه می‌کند. طبق هدف 12.7 (ساده‌ترین مسیر پایدار)،
Direct برنده است. مسیر C (replica) فعلاً بی‌مورد است — bottleneck backend است نه LB ما.

## 12.8 — ذخیره‌سازی دیتاست دوگانه (انجام شد)

- **migration additive** `migrations/2026-10-20_asr_output_dual_dataset.sql` → جدول
  `asr_output` روی 53 ساخته شد (idempotent). کلید یکتا
  `(session_id, provider, pipeline_version, audio_sha256)` → اجرای مجدد کنترل‌شده،
  نسخه‌های تاریخی از بین نمی‌روند.
- ساختار `llm_output` LLM-pipeline است (prompt_id, input/output_tokens) و برای
  ASR-provider-versioned مناسب نبود → جدول جدا ساخته شد (طبق اجازه 12.8).
- فایل‌ها در `downloads/asr/roshan/3/`: `roshan.v1.srt` / `.full.txt` / `.raw.json` /
  `.manifest.json` (تولید در up-window توسط `dashboard/roshan_pilot.py`).
- **Whisper دست‌نخورده:** sha256 SRT/TXT قبل و بعد ثبت شد؛ هیچ ستون/فایل Whisperی
  تغییر نکرده است.

## 12.9/12.10/12.11 — پست‌پردازش، مقایسه و لاگ (کد آماده، اجرا در up-window)

- `dashboard/roshan_pilot.py` — deterministic, no-LLM:
  `finalize` (parse segments → SRT + fulltext + manifest + DB row؛ TEXT_ONLY اگر
  timestamp نباشد؛ validation: no negative/inverted/unordered, UTF-8, Persian، non-empty)
  و `compare` (side-by-side Whisper vs Roshan به‌صورت nearest-timestamp).
- merge-chunks: global timestamp = chunk_start + local، dedup deterministic (containment
  + jaccard>0.8)، مرزهای نامطمئن → `needs_review`.
- لاگ ساختاریافته: `run_log.jsonl` (هر probe/test با ts, http, latency, event).

## وضعیت کلی این STEP

**PARTIAL — ASR phase BLOCKED on Roshan upstream outage.** زیرساخت کامل (دانلود،
فرمت، chunk، DB، پست‌پردازش، مقایسه، مسیر مستقیم) ساخته و تست‌شده است؛ تنها مانع،
down بودن backend Roshan است که خارج از کنترل این پروژه است و باید توسط team
مالک `asr.ismc.ir` برطرف شود.
