# گزارش جامع — بانک رادیو معرّف: از MySQL/فایل‌ها تا RAG، radio.ai.ismc.ir و Job شبانه

**تاریخ:** 2026-10-22 · **وضعیت:** فقط تحقیق + طراحی (بدون هیچ تغییری در تولید)
**زبان داده:** فارسی (اس‌اِر‌تی و متون) + انگلیسی (فقط خلاصهٔ EN) · **حجم:** ~4,100 اپیزود

---

## ۱. نتیجهٔ یک‌خطی

بله — برای **۹۶.۷٪ اپیزودهای رادیو معرّف (۳٬۹۶۶ از ۴٬۱۰۰)**، مجموعهٔ کامل ۶تایی وجود دارد:
زیرنویس خام + متن کامل (full) + متن تصحیح‌شده + زیرنویس تصحیح‌شده + خلاصهٔ فارسی + خلاصهٔ انگلیسی — هم در **MySQL** (جدول `llm_output`) و هم در **فایل‌ها** (`downloads/cleaned/`). ۱۳۴ اپیزود (۳.۳٪) تازه‌اند و هنوز لایهٔ LLM روی آن‌ها نیامده (اپیزودهای ۱۱ اکتبر به بعد) — دقیقاً همان چیزی که job شبانه باید پر کند.

---

## ۲. معماری فعلی (آنچه روی سرور ۵۳ بالا است)

```
radio.iranseda.ir (EPG + MP4/MP3)
        │  Go downloader (download_db.go، هر ۲h، scan.go)
        ▼
MySQL «radio» — کانتنر iranseda-mysql روی 172.20.1.53:3308
   (کاربر n8nuser / رمز از محیط `DB_PASS` در .env — هرگز hardcode نمی‌شود)
        │  crawler.py (هر ۴۵ min): دانلود + زیرنویس
        ▼
ASR: رُشان (asr.ismc.ir، مدل asr-ismc-fa)  ← ⚠️ ۲۰۲۶-۱۰-۲۰ خطای 503/401 (UPSTREAM_503)
        │  خروجی: downloads/radio-maaref-MM-DD-HH-MM-SS.srt + .txt
        ▼
Jobs LLM (qwen38-nothinking از LiteLLM 52:4000) — dashboard/llm_jobs.py
        │  full_text · summary (FA+EN) · correct_text · correct_subtitles
        ▼
downloads/cleaned/<base>.{full.txt,correct.txt,correct.srt,summary.txt,summary.en.txt}
   + سطردر llm_output (دوگانه‌نویسی DB + فایل)
        │  generate_site.py (هر ۲h) + dashboard (FastAPI :8990، auth)
        ▼
سایت ایستا (GitHub Pages سبک) + داشبورد داخلی 172.20.1.53:8990
```

**ایجاد radio.ai.ismc.ir:** هنوز وجود ندارد. الگو دقیقاً همان الگوی taghrir/mesbah/eiis است:
nginx vhost روی 52 + `radio_frontend` (nginx، مثلاً 53:8044) + `radio_api` (53:8043) — با همان backend langgraph/Neo4j مشترک یا نسخهٔ ساده‌تر مستقل.

---

## ۳. پاسخ مستقیم سؤال: «برای هر برنامه، در MySQL چه چیزی می‌بینم؟»

### ۳.۱ جدول‌های اصلی (DB `radio`، ۱۴ جدول)

| جدول | سطر | نقش |
|---|---:|---|
| `radio_programs` | 55 | برنامهٔ هفتگی (id, name, time, time_description, description, radio, radio_id, start, is_legacy) — **متادیتای «برنامه»** |
| `radio_program_sessions` | 5,904 | هر اپیزود پخش‌شده (id, program_id, link, filename, srt_filename, is_downloaded, status, is_subtitled, attempts, last_error, created_at, updated_at) — **کلید اصلی** |
| `llm_output` | 13,603 | خروجی هر LLM job به ازای هر session (session_id, job_type, model, prompt_id, job_id, **content**, **content_en**, **srt_content**, file_relpath, started_at, finished_at, status, error, input_tokens, output_tokens) |
| `llm_job` | 1,099 | تاریخچهٔ بچ‌ها (job_type, model, total, done, failed, note) |
| `pipeline_steps` | 6 | مراحل فعال: program_block / full_text / summary / correct_text / correct_subtitles / correct_text_v2 |
| `prompts` | 4 | پرامپت‌های دقیق فعلی (capture شده، در بخش ۸) |
| `asr_output` | 1 | خروجی ASR (provider, model_name, audio_sha256, srt_path, duration_ms, rtf, error_code) |

### ۳.۲ نگاشت ۵ محصول به فیلدها (قلب گزارش)

کلید ۱:۱ همه‌چیز = **`session.filename` بدون پسوند** = basename فایل. مثال: `radio-maaref-05-07-19-13-30`

| محصول | فایل خام | فایل LLM (cleaned/) | ردیف MySQL |
|---|---|---|---|
| **زیرنویس** (raw SRT) | `downloads/<base>.srt` | — | `srt_filename` + فایل روی دیسک |
| **متن کامل** (raw full text) | `downloads/<base>.txt` | — | همان فایل |
| **متن تصحیح‌شده** | — | `<base>.correct.txt` | `llm_output` job=`correct_text` → `content` |
| **زیرنویس تصحیح‌شده** | — | `<base>.correct.srt` | `llm_output` job=`correct_subtitles` → `srt_content` |
| **خلاصهٔ فارسی** | — | `<base>.summary.txt` (بخش FA) | `llm_output` job=`summary` → `content` |
| **خلاصهٔ انگلیسی** | — | `<base>.summary.en.txt` | `llm_output` job=`summary` → `content_en` |
| (بامزه) متن کاملِ یکپارچه | — | `<base>.full.txt` | `llm_output` job=`full_text` → `content` (فقط ۹۳۳ ردیف — job قدیمی/اختیاری) |

### ۳.۳ پوشش دقیق (اعداد واقعی، امروز سنجیده‌شده)

کل ۵٬۹۰۴ session: 5,694 subtitled (mp4: 4,228 + mp3: 1,595). **mp3ها قدیمی‌اند (۱۴۰۳) و بدون ASR/LLM** — کُرپس واقعی RAG = **mp4 subtitled: 4,100**.

| محصول | پوشش (از ۴٬۱۰۰ mp4 subtitled) |
|---|---:|
| زیرنویس خام (.srt) | **4,100 (100%)** |
| متن خام (.txt) | **4,100 (100%)** |
| .correct.srt (زیرنویس تصحیح‌شده) | 4,002 (97.6%) |
| .full.txt | 3,969 (96.8%) |
| .correct.txt (متن تصحیح‌شده) | 3,969 (96.8%) |
| .summary.txt (خلاصه FA) | 3,969 (96.8%) |
| .summary.en.txt (خلاصه EN) | 3,966 (96.7%) |
| **مجموعهٔ کامل ۶تایی** | **3,966 (96.7%)** |

**شکاف‌ها:** 134 اپیزود بدون هیچ LLM output (اپیزودهای ۲۰۲۶-۱۰-۱۱ به بعد). دلیل مستند: (الف) بچ‌های correct_subtitles روز ۲۰۲۶-۱۰-۱۱ (total=2141/2142) **خاموش مانده‌اند** (done=0/1)؛ (ب) ASR رُشان ۲۰۲۶-۱۰-۲۰ با UPSTREAM_503/401 قطع شد (با memory «Roshan has no upstream» مطابقت دارد).

---

## ۴. طراحی پایپ‌لاین تکرارپذیر (MySQL → JSON → dump → RAG)

### ۴.۱ شکل سند (elastic-like document)

هر اپیزود = **۱ سند مادر** + **N سگمنت** (الگوی taghrir_seg). اسکیما پیشنهادی:

```json
{
  "index": "radio_maaref_seg",
  "_id": "radio-maaref-05-07-19-13-30::seg::42",
  "embedding": "<dense_vector 1024 — Qwen3-Embedding-0.6B>  (تأییدشده در STEP 1: مدل RAG query همان 0.6B/1024 است)",
  "text": "متن سگمنت (از correct.srt، ~700 کاراکتر، timestamped)",
  "episode_id": "radio-maaref-05-07-19-13-30",
  "seg_index": 42, "seg_count": 310,
  "seg_start": "00:29:30", "seg_end": "00:30:45",
  "channel": "radio-maaref",
  "air_date": "1405-07-19",           // از basename (شمسی) — با miladcalendar به میلادی
  "air_time": "19:13:30",
  "program_name": "نماز شب",            // join با radio_programs از program_id
  "program_radio": "رادیو مکرّم",
  "has_summary_fa": true, "has_summary_en": true,
  "citation": "radio://radio-maaref-05-07-19-13-30#29:30"
}
```
+ ایندکس دوم `radio_maaref_episode` (سطح اپیزود): summary_fa (embedding جدا)، summary_en، full_text، correct_text، duration، channel، program_name.

**Grounding واقعی** = `episode_id` + `seg_start` (timestamp) — دقیق‌تر از تقریرات (که page ندارد).

### ۴.۲ مراحل تکرارپذیر (هر مرحله idempotent + checkpointed)

```
extract.py    MySQL + filesystem → state/radio_episodes.jsonl  (سند مادر، بدون embedding)
              JOIN: sessions × llm_output (pivot: job_type→فیلد) × radio_programs
              فیلتر: status='subtitled' AND filename LIKE '%mp4'
correct.py    (اختیاری) لایهٔ LLM براپایاپس‌اف: full/correct/summary برای ۱۳۴ خالی
              — همان jobها و پرامپت‌های فعلی dashboard/llm_jobs.py، فقط backfill
embed.py      LiteLLM 52:4000 Qwen3-Embedding-0.6B (1024-dim، تأییدشده در STEP 1) → state/radio_embeddings.jsonl
              (سگمنت‌ها از correct.srt؛ EN summary جدا)
index.py      PUT mapping + bulk index → ES 52:9200  (radio_maaref_seg + radio_maaref_episode)
              replicas=0، single-node (الگوی taghrir-es)
es2dump.py    (اختیاری) ES → Neo4j برای چت graph-RAG — الگوی موجود taghrir
```

**روی سرور دیگه‌ای (محل آپدیت مداوم برنامه‌ها):** فقط `extract.py` + `embed.py` + `index.py` لازم است — ورودی‌ها فقط MySQL (replication/Dump روزانه یا SSH) + پوشهٔ `cleaned/` (rsync/rclone). هیچ وابستگی به ASR یا لایهٔ دانلود ندارد.

### ۴.۳ job شبانه (نصب در rag-portal، الگوی T7 موجود)

- **ویندو:** ۱۴:۰۰–۰۸:۰۰ تهران، تیک ۱۰ دقیقه، gate GPU آزاد (الگوی دقیق `_qa_bank_loop`)
- **اقتزازی:** هر اپیزود که `llm_output` کاملش ≥ 5 job دارد → 1× embed + 1× index (sha256(episode_id + content_hash) به‌عنوان idempotency key)
- **QA تولیدی:** برای هر اپیزود جدید، ۳–۵ سؤال از summary + correct_text (پرامپت بخش ۸) → ایندکس `radio_qa` → در دسترس job QA bank (T7) به‌عنوان corpus جدید `rag-radio`
- **رأس‌به‌رأس با P4:** دقیقاً همان الگو (cursor/incremental، checkpointed، بدون دست‌زدن به corpus اصلی)

### ۴.۴ radio.ai.ismc.ir

1. repo جدید `rag/radio-portal` (یا پوشه در langgraph-neo4j-qa با instance override — **هشدار: backend مشترک با mesbah/eiis**)
2. `radio_api` (FastAPI 53:8043) + `radio_frontend` (nginx 53:8044) — کپی الگوی taghrir_frontend
3. nginx vhost روی 52 + Let's Encrypt (الگوی taghrir.ai.ismc.ir)
4. UI: جستجوی معنایی (kNN روی seg)، فیلتر channel/tarih/برنامه، نمایش transcript + سگمنت هایلایت + timestamp playback، tab QA، tab خلاصه‌های دوزبانه

### ۴.۵ یکپارچگی با rag.ai.ismc.ir

- در `ragportal_api` corpus جدید `rag-radio` (مثل `rag-taghrir`) — LiteLLM model alias + ES index
- در تب «بانک سؤال» (P4/P8): radio به‌عنوان منبع جدید؛ فیلتر `corpus=radio`
- در `/api/ask` هم‌جای تقریرات (multi-corpus)

---

## ۵. کارهای امبدینگ (چند دقیق)

| مورد | مقدار |
|---|---|
| مدل | `Qwen3-Embedding-0.6B` از LiteLLM `http://172.20.1.52:4000/v1` (تأییدشده: همان مدل RAG query) |
| بُعد | **1024**، cosine (سازگار با ES taghrir / بانک Q&A مشترک) |
| سگمنت | ~700 کاراکتر از `.correct.srt` (بلوک‌های SRT را به سگمنت‌های متنی تبدیل با حفظ timestamp) — **متن تصحیح‌شده، نه خام** |
| تعداد | ~4,100 اپیزود × ~300 سگمنت ≈ **1.2M سگمنت** ⚠️ |
| برآورد زمان | ~10h–14h روی H100 (الگو: 22K سگمنت تقریر ≈ چند ساعت؛ با window شبانه) |
| EN summary | امبدینگ جدا (زبان دیگری است؛ در فیلد `summary_en_embedding` یا ایندکس جدا) |
| episode summary FA | امبدینگ جدا در ایندکس `radio_maaref_episode` |
| checkpoint | `state/radio_embeddings.jsonl` — هر سگمنت با `episode_id::seg_index` idempotent |

**هشدار مقیاس:** 1.2M سگمنت ~12–15GB در ES (الگوی taghrir_seg: 22K≈1GB). ظرفیت دیسک ES روی 52 را قبل از شروع چک کنید؛ در غیر این صورت ابتدا با `correct.txt` به‌صورت کل‌اپیزود (4,100 سند) شروع کنید و سگمنت‌بندی را فاز دوم بگذارید.

---

## ۶. گام‌های اجرایی (ترتیب پیشنهادی)

1. **P0 — backfill شکاف:** ۱۳۴ اپیزود بدون LLM → اجرای jobهای موجود dashboard (same prompts) + رفع خطای ASR رُشان برای اپیزودهای جدید
2. **P1 — extract + embed + index:** ۴ مرحلهٔ بخش ۴.۲؛ خروجی: ۲ ایندکس ES سبز
3. **P2 — radio.ai.ismc.ir:** repo + api + frontend + nginx/SSL
4. **P3 — یکپارچگی rag.ai.ismc.ir:** corpus `rag-radio` + فیلتر در بانک سؤال
5. **P4 — job شبانه:** T7-style loop در rag-portal (QA از اپیزودهای جدید + backfill خودکار)
6. **P5 — es2dump → Neo4j** (اختیاری، برای graph-RAG چت رادیو)

---

## ۷. آدرس‌ها و راه‌های دسترسی (تمام)

| مورد | آدرس |
|---|---|
| repo رادیو | `/home/saber/saberprojects/iranseda-crawler-golang-/` روی 53 · remote: `git@github.com:saber13812002/iranseda-crawler-golang-.git` (branch `download-db`) |
| MySQL | کانتنر `iranseda-mysql` @ `172.20.1.53:3308`، user `n8nuser` / pass از env `DB_PASS` (در `.env`)، db `radio` |
| فایل خام | `/home/saber/saberprojects/iranseda-crawler-golang-/downloads/` (4,379 srt + txt) |
| فایل LLM | `.../downloads/cleaned/` (24,666 فایل) |
| داشبورد | `172.20.1.53:8990` (FastAPI، auth-token؛ `/api/stats`, `/api/jobs`, `/api/window`, `/metrics`) |
| LiteLLM | `http://172.20.1.52:4000/v1` (چت `qwen38-nothinking`، امبدینگ `Qwen3-Embedding-0.6B` 1024 — تأییدشده در STEP 1) |
| ES | `http://172.20.1.52:9200` (cluster `taghrir-es` — ایندکس radio **هنوز وجود ندارد**) |
| الگوی سایت | taghrir.ai.ismc.ir (nginx 52 + frontend 53:8024 + api 53:8023) |
| cron فعلی | `iranseda-deploy.timer` هر ۳h + cron داخلی download (2h) / crawler (45m) / site (2h) |

---

## ۸. پرامپت جامع (master prompt) — آمادهٔ کپی در جلسهٔ اجرا

```
# نقشهٔ کامل پروژهٔ RAG رادیو معرّف — پرامپت جامع برای AI اجراکننده

## هدف
تبدیل ~۴٬۱۰۰ اپیزود رادیو مکرّم (رادیو معرّف) به یک منبع RAG قابل‌جستجو،
با سایت مستقل radio.ai.ismc.ir، یکپارچگی در rag.ai.ismc.ir، و تولید QA
شبانه — بدون هیچ اختلالی در سرویس‌های فعلی.

## ۱) دسترسی‌ها (همه روی سرور 53 مگر ذکر شده)
- SSH: ssh jump53  (172.20.1.53, user saber). سرور 52 فقط از ProxyJump (s52 مستقیم قطع است).
- repo: /home/saber/saberprojects/iranseda-crawler-golang-/
  (remote GitHub saber13812002/iranseda-crawler-golang-، branch download-db — فقط خوان)
- MySQL: docker exec iranseda-mysql mysql -un8nuser -p"$DB_PASS" radio  (رمز از env)
  (172.20.1.53:3308، db=radio، 14 جدول)
- LiteLLM: http://172.20.1.52:4000/v1 — chat: qwen38-nothinking،
  embedding: Qwen3-Embedding-0.6B (1024-dim، cosine — تأییدشده در STEP 1)
- Elasticsearch 8.13: http://172.20.1.52:9200 (cluster taghrir-es، single-node، replicas=0)
- الگوی deploy: taghrir.ai.ismc.ir = nginx vhost (52) + *_frontend nginx (53:8024)
  + *_api FastAPI (53:8023) + Let's Encrypt. repo backend: langgraph-neo4j-qa
  ⚠️ backend مشترک با mesbah/eiis است — برای رادیو از instance override یا repo جدا استفاده کن.
- داشبورد فعلی رادیو: 172.20.1.53:8990 (auth) — jobها با POST /api/jobs/{job}/run

## ۲) مدل داده (کلید ۱:۱ = basename فایل)
جدول کلیدی: radio_program_sessions (id, program_id, link, filename, srt_filename,
status, is_subtitled, created_at). filename نمونه: radio-maaref-05-07-19-13-30.mp4
تاریخ در basename = شمسی (MM-DD-HH-MM-SS). 55 برنامه در radio_programs
(name, time, radio, start) — join با program_id.

پوشش فعلی (4100 session mp4 subtitled):
- زیرنویس خام:  downloads/<base>.srt        (100%)
- متن خام:      downloads/<base>.txt         (100%)
- متن تصحیح:    downloads/cleaned/<base>.correct.txt      (96.8%)
- زیرنویس تصحیح: downloads/cleaned/<base>.correct.srt     (97.6%)
- خلاصه FA:     downloads/cleaned/<base>.summary.txt      (96.8%)
- خلاصه EN:     downloads/cleaned/<base>.summary.en.txt   (96.7%)
همه در llm_output هم ثبت‌اند: job_type ∈
{full_text(933), summary(4212: content=FA, content_en=EN), correct_text(4212),
 correct_subtitles(4245: srt_content), qa(1)}
شکاف: 134 اپیزود جدید (بعد از 2026-10-11) بدون LLM output؛ ASR رُشان
(asr.ismc.ir) از 2026-10-20 با UPSTREAM_503 خراب است.

## ۳) پرامپت‌های LLM فعلی (از جدول prompts — حفظ کن)
- summary: فارسی ۵–۸ جمله + خط «English Summary:» + انگلیسی (دوزبانه در یک call)
- correct_text: «خطاهای whisper را اصلاح کن؛ فقط متن تصحیح‌شده را برگردان»
- correct_subtitles: «متن بلوک‌های SRT را اصلاح کن؛ شماره‌ها و زمان‌ها را دست نزن؛
  خروجی = متون بلوک‌ها با ' ||| ' جداشده»
- correct_text_v2: windowed با [پیش‌زمینه]/[بلوک‌های هدف]/[پس‌زمینه]، خلاصه‌نویسی ممنوع،
  کلمات مشکوک حفظ می‌شوند، ' ||| ' separator

## ۴) کارهایی که باید انجام شود (ترتیب)
P0: backfill 134 اپیزود با jobهای موجود dashboard + پیگیری خطای ASR
P1: extract.py — JOIN sessions×llm_output×radio_programs (فیلتر mp4+subtitled)
    → state/radio_episodes.jsonl (idempotent، کلید = basename)
P2: embed.py — سگمنت‌بندی correct.srt (~700 کاراکتر) → Qwen3-Embedding-0.6B (1024-dim)
    checkpointed به state/radio_embeddings.jsonl؛ EN summary جدا
P3: index.py — 2 ایندکس: radio_maaref_seg (embedding 1024, text, episode_id,
    seg_index, seg_start/seg_end, channel, air_date, air_time, program_name,
    citation="radio://<base>#<mm:ss>") + radio_maaref_episode
    (summary_fa_embedding, summary_en_embedding, full_text, correct_text, ...)
    ES: replicas=0. حجم برآوردی سگمنت: ~1.2M سند ≈ 12-15GB — قبلش دیسک 52 را چک کن.
P4: radio.ai.ismc.ir — repo جدید rag/radio-portal، radio_api (53:8043) +
    radio_frontend (53:8044)، vhost+SSL روی 52 (الگو taghrir)
P5: rag.ai.ismc.ir — corpus جدید rag-radio در ragportal_api + فیلتر corpus=radio
    در تب بانک سؤال + multi-corpus در /api/ask
P6: job شبانه در rag-portal (الگوی T7: window 14:00-08:00 تهران، tick 10min،
    GPU gate، idempotency = sha256(episode_id+content_hash)):
    برای هر اپیزود جدید: backfill LLM → embed → index → 3-5 QA (پرامپت پایین)
    → ایندکس radio_qa → در دسترس QA bank
P7 (اختیاری): es2dump → Neo4j برای graph-RAG

## ۵) پرامپت تولید QA برای رادیو
«بر اساس خلاصه و متن زیر از برنامهٔ رادیویی «{program_name}» (تاریخ پخش {air_date}،
 {channel})، ۳ تا ۵ پرسش‌وپاسخ آموزشی بساز. هر پرسش به‌تنهایی معنادار باشد،
پاسخ فقط از متن برنامه باشد (بدون دانش خارج)، و یک span دقیق از متن را به‌عنوان
منبع نشان بده. خروجی JSON: [{"question","answer","span"}].
خلاصه: {summary_fa}
متن: {correct_text}»

## ۶) قوانین سخت
- هیچ تغییری در production فعلی (ASR/crawler/داشبورد/سایت) — فقط خوان + ساخت موازی
- همهٔ گام‌ها checkpointed/idempotent؛ بازاجرا = فقط کار جدید
- فیلتر ES داخل knn.filter (ES 8.13)، paginate با scroll نه sort _id
- secret scan قبل از هر push؛ branch جدا؛ merge به main ممنوع بدون تأیید
- گزارش نهایی با اعداد واقعی (queryهای اجراشده)، نه برآورد

## ۷) سؤالات تحویل
۱. چند اپیزود در هر ایندکس ایندکس شدند؟ ۲. پوشش هر محصول پس از backfill؟
۳. زمان واقعی embed برای کل کُرپس؟ ۴. radio.ai.ismc.ir روی چه آدرس/پورتی زنده شد؟
۵. چند QA در radio_qa تولید شد؟ ۶. job شبانه چند اپیزود در ویندوی اول پردازش کرد؟
۷. دیسک/حافظهٔ ES بعد از ایندکس چقدر شد؟ ۸. چه شکافی باقی ماند و چرا؟
```

---

## ۹. هشدارها (gotchaهای سنجیده‌شده)

1. **mp3 vs mp4:** 1,595 session mp3 (۱۴۰۳) subtitled هستند ولی بدون ASR/LLM — از کُرپس RAG حذف (فقط mp4)
2. **تاریخ شمسی در basename** — برای فیلتر ES باید با miladcalendar به میلادی/ISO تبدیل شود
3. **`programs` table خالی است** — متادیتای برنامه در `radio_programs` (55 سطر)
4. **backend langgraph مشترک** با mesbah/eiis است (الگوی taghrir)
5. **Roshan ASR قطع است** — اپیزودهای بعد از ۱۰-۲۰ هنوز raw SRT هم ندارند (فقط pending)
6. **1.2M سگمنت** — بزرگ‌ترین تصمیم: سگمنت‌بندی کامل vs کل‌اپیزود (دیسک 52 را چک کنید)
7. **`full_text` job فقط 933 سطر** دارد — برای RAG، `correct.txt` (4,251) مرجع اصلی متن است، نه `full.txt`
8. **دوگانه‌نویسی DB+فایل** ممکن است drift کند — در extract، فایل مرجع نهایی است و `llm_output` فقط برای join و metadata
