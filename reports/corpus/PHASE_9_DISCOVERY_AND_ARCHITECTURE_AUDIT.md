# گزارش نهایی PHASE 9 — کشف و ممیزی معماری: «کورپس یکپارچه و معماری RAG» (IRANSEDA)

> **زیرمأموریت:** ST-08 (تألیف گزارش نهایی) — مأموریت فاز ۹ §14–§16
> **تاریخ:** ۲۰۲۶-۱۱-۰۷ (UTC)
> **مخاطب:** مدیر پروژه (PM) — سند تصمیم‌گیری (decision-ready)
> **زبان:** فارسی؛ شناسه‌های فنی، مسیرها، دستورات و SHAها به‌صورت انگلیسی/LTR
> **منابع:** ۷ گزارش زیرمأموریت `.tmp_phase9/ST-01_live_snapshot.md` تا `ST-07_architecture_roadmap.md` + گزارش‌های پیشین `reports/corpus/STAGE_3_FULL_EXPORT_REPORT.md` و `reports/corpus/STAGE_4_PRODUCTION_ACCEPTANCE.md`
> **حالت بازرسی:** فقط‌خوان (read-only) — هیچ نوشتار، تغییر یا عمل مخرب روی سیستم‌های تولید انجام نشده

---

> ### 📎 مدرک‌سنجی (Evidence Audit)
> - **بازۀ بازرسی:** ۲۰۲۶-۱۱-۰۶ ساعت ۱۹:۳۸ تا ۲۰۲۶-۱۱-۰۷ ساعت ~۰۴:۴۰ (UTC)
> - **میدان‌ها:** سرور `llm` (`172.20.1.53`) — MySQL، Docker، Neo4j، فایل‌سیستم، cron، Git — و workspace محلی Windows (`c:/Users/s.tabatabaei/Documents/saberprojects/iranseda`)
> - **روش:** همه یافته‌ها از **بازرسی زنده و read-only** (کوادری SQL فقط‌خوان، `git ls-tree`/`ls-remote`، خواندن فایل، HTTP GET عمومی، کوئری Neo4j فقط‌خوان)؛ هیچ عملیات نوشتاری روی تولید
> - **قابلیت بازسازی:** هر ادعای این گزارش با مرجع `(ST-XX، فایل:خط، جدول.ستون، SHA، خروجی دستور، تعداد، زمان، HTTP status)` پشتیبانی می‌شود و قابل بازسازی است
> - **پوشش:** ۷ زیرمأموریت کشف (ST-01 تا ST-07) + ۲ گزارش مرحله‌ای پیشین (STAGE_3، STAGE_4)
> - **محرمانگی:** هیچ توکن/گذرواژه/URL خصوصی در این سند نیست؛ URLهای GitHub عمومی (raw.githubusercontent.com)

---

## فهرست (۲۰ بخش)

1. [خلاصۀ مدیریتی](#۱-خلاصه-مدیریتی)
2. [عکس زنده‌ی تولید (Live Production Snapshot)](#۲-عکس-زنده-تولید)
3. [فهری‌گیری Git و ریپوها](#۳-فهری-گیری-git-و-ریپوها)
4. [کشف سازندۀ Schema 1.1](#۴-کشف-سازنده-schema-11)
5. [فهری‌گیری اسکیمای دیتابیس](#۵-فهری-گیری-اسکیمای-دیتابیس)
6. [مقایسۀ اسکیمای کورپس 1.0 در برابر 1.1](#۶-مقایسه-اسکیمای-کورپس)
7. [خاستگاه داده (Data Lineage)](#۷-خاستگاه-داده)
8. [پوشش URLهای GitHub](#۸-پوشش-urlهای-github)
9. [پوشش URLهای IranSeda](#۹-پوشش-urlهای-iranseda)
10. [سازگاری برون‌آیی افزایشی](#۱۰-سازگاری-برون-آیی-افزایشی)
11. [معماری RAG (بازرسی ۱۰ لایه‌ای)](#۱۱-معماری-rag)
12. [وضعیت Hugging Face — BLOCKED](#۱۲-وضعیت-hugging-face)
13. [یکپارچگی Class B (قرنطینۀ 1,147)](#۱۳-یکپارچگی-class-b)
14. [معماری پیشنهادی نهایی](#۱۴-معماری-پیشنهادی-نهایی)
15. [ریسک‌ها و بدهی فنی](#۱۵-ریسک‌ها-و-بدهی-فنی)
16. [نقشه‌ی اجرایی پیشنهادی فاز ۹ (P9-1 … P9-8)](#۱۶-نقشه-اجرای-پیشنهادی-فاز-۹)
17. [معیارهای پذیرش کل فاز (A1–A10)](#۱۷-معیارهای-پذیرش-کل-فاز)
18. [وابستگی‌های مسدود (Blocked Dependencies)](#۱۸-وابستگی‌های-مسدود)
19. [اقدامات دقیق بعدی (سه گام نخست)](#۱۹-اقدامات-دقیق-بعدی)
20. [سرنخ‌های Git: commit و push](#۲۰-سرنخ‌های-git-commit-و-push)

---

## ۱. خلاصۀ مدیریتی

**حکم کلی (Verdict):** معماری فعلی **سالم و جداشده (decoupled)** است، اما «زیرساخت یکپارچگی» هنوز در مرحله‌ی کارِ دستی است. برون‌آیی کورپس 1.1 امروز **فقط با دست** (CLI از یک worktree موقت در `/tmp`) انجام می‌شود، بدون cron، بدون قفل بین‌فرآیندی، و بدون اتصال خودکار به RAG. جمع‌بندی ST-05 و ST-07: ادغام همه‌چیز در **یک سازندۀ single-writer با ۶ تغییر جراحی (بدون تغییر schema، بدون نوشتار DB، بدون جدول جدید) FEASIBLE است** — نه ساختن مکانیزم تازه، بلکه **بازسازی** قطعاتی که هرکدام جداگانه اثبات شده‌اند.

**۵ مهم‌ترین واقعیت‌ها:**

| # | واقعیت | مرجع |
|---|---|---|
| 1 | کورپس زنده: **9,747 رکورد** (schema 1.1، یکتایی record_id **100٪**) + **1,147 قرنطینه** (Class B) + ۲ sidecar (`rag_linkage.jsonl` 10,894 سطر / `asset_manifest.jsonl` 39,447 سطر)؛ خروجی **atomic** با checksum و ۳ اسلات `previous/` — اما **سازندۀ 1.1 در worktree موقت `/tmp/saber_stage4_wt`** با برون‌آیی **دستی** (SSH از `172.22.6.30`، پنجرۀ 02:26–03:13 UTC 2026-11-06) و `export_enabled=false` | ST-01/02 |
| 2 | **اجرای کد 1.0 روی کورپس زنده‌ی 1.1 مخرب است:** 9,747 خط را با subset ~1,572 خط **replace** می‌کند + دگرنسخه‌ی schema + ردشدن توسط validator 1.0 — بدون archive/rollback | ST-05 (Q1) |
| 3 | ریشه‌ی Class B (1,147) **کاملاً شناسایی شده**: 27 جفت URL تکراری در `radio_programs` (legacy منقضی 2025-11-19 + بازسازی همان روز 16:31؛ **بدون UNIQUE روی url**) + `uq_session_program_link UNIQUE(program_id, link)` → 2 ردیف برای یک `(ch,e)`. **۵ گزینه‌ی حل مستند شده؛ تصمیم = DEFERRED به PM؛ قرنطینه دست‌نخورده** | ST-03 |
| 4 | سرویس RAG **زنده و کار می‌کند** (تست زنده: HTTP 200، 5.91s، score 0.8108؛ نقل‌مراجعه **4 از 7**) — اما: **357 جلسه‌ی کهنه** (DB 10,544 در برابر corpus 10,901)، `audio_url` **0٪**، نوع لینک **summary** در API نیست (درحالی‌که داده‌اش 58.7٪ در DB هست)، **mismatch پیش‌فرض variant** (UI روی 4b / API روی 06b)، و **تضاد تاریخ ≈2.5 ماهه** (فایل‌نوم در برابر EPG) | ST-06 |
| 5 | **Hugging Face = BLOCKED** (دیتاست وجود ندارد، `HF_TOKEN` خالی، کتابخانه‌ها نصب نیستند، حقوق **RTS NOT VERIFIED** — سیاست private-first)؛ **audio mp3 = 0/126** در هیچ درخت Git (headend timeout)؛ **دیسک 80٪** (291G آزاد از 1.5T) | ST-06/04/01 |

**فاز ۹ چه خواهد کرد (به‌اختصار):** یک سازندۀ single-writer «یک run، یک staging، یک promote، یک قفل» با cron `30 */6 * * *` + full هفتگی (پاک‌شدن backlog فعلی **1,572** رکورد در ≤24 ساعت)؛ قرارداد رسمی schema 1.1 + K1–K22؛ تعمیر URLها (44 اِست P3-only + 4 کهنه + 261 blob غیر-canonical + عادی‌سازی episode)؛ sync زنجیره‌شده به Neo4j (357→0) و 2–3 نوع لینک تازه در API؛ پایش گرافانا. **P9-6 (HF) قابل تعویق به فاز ۱۰** است چون درهای خارجی (حقوق + توکن) باز نیستند.

**مسیر انتقایی:** `P9-1 → P9-2 → P9-5 → P9-7 → P9-8(بخش RAG)`؛ موازی‌شدنی: `P9-3 ∥ P9-4 ∥ P9-5` (هر سه پس از P9-2). جزئیات: بخش‌های ۱۴ و ۱۶.

---

## ۲. عکس زنده‌ی تولید

> منبع: `ST-01_live_snapshot.md` — بازرسی زنده در بازۀ **2026-11-06 19:38:26–19:42:38 UTC** روی سرور `llm` (`172.20.1.53`)، فقط‌خوان.

### ۲.۱ خدمات و زمان‌بندی

| مولفه | وضعیت (مبنا: خروجی زنده) |
|---|---|
| `iranseda-dashboard.service` | `active`/`enabled`، port **8990**، `MainPID=1048231`، `NRestarts=4406`، از 2026-11-02T18:00:17Z در حال اجرا |
| cron کاربر `saber` | `*/30 * * * * refresh_site.sh` و `15,45 * * * * run_pipeline.sh` — **هیچ cron برای corpus/RAG** |
| crontab ریشه | **BLOCKED** (`sudo: a password is required`) — بررسی ریشه‌ای crontab ممکن نشد (بخش ۱۸) |
| `/etc/cron.d` | فقط `e2scrub_all`، `.placeholder`، `sysstat` |
| آخرین run موفق pipeline | 17:45:01→19:01:10 UTC (4,569s، **64 شکست دانلود**، `status=ok`)؛ ردیف‌های 654–680 در `pipeline_runs` |
| runهای شکست‌خورده‌ی site | id 526/527/528 (2026-11-04): `rebase failed (external push conflict?); push failed` |
| خطای جاری دانلود | `headend1.iranseda.ir` → `dial tcp 185.109.247.100:443: connect: connection timed out` |

### ۲.۲ کانتینرهای Docker و نوبت‌ها (Queues)

| مولفه | وضعیت |
|---|---|
| `iranseda-mysql` | `Up 10d`، healthy (`mysql:8.0`) |
| `iranseda-whisper-api` / `iranseda-whisper-worker` | `Up 10d` / `Up 3d` (restarts=0) |
| آخرین جلسات ASR | session **10901 DONE** 16:21:29Z؛ session 10900 FAILED (attempt 3، ffmpeg `Invalid data found`) → `failed_permanent` |
| نوبت جلسات | `subtitled` **9,361** / `pending_download` **1,480** / `failed_permanent` **58**؛ `pending_transcribe` 0؛ `transcribing` 0؛ retryable 0 |
| برنامه‌ها | **32 فعال از 59** (32 با خروجی) |

### ۲.۳ SRT و watermark

| شاخص | مقدار |
|---|---|
| SRT کل / امروز / دیروز / 7روز / 30روز | **15,214** / 6 / 3,450 (کپی انبوه) / 3,457 / 7,865 — نرخ تولید واقعی ≈ **1/روز** |
| تازه‌ترین SRT | `radio-maaref-05-08-15-18-00.srt` (mtime 16:21:28Z) |
| watermark sessions | `sessions_updated_at=2026-11-06T16:21:29` / `sessions_max_id=10,901` |
| watermark llm | `llm_finished_at=2026-10-11T11:30:01` / `llm_max_id=15,324` — **LLM از 2026-10-11 خنثی** (`llm_24h=0`) |
| سایر | `asr_24h=0`، `crop=22` |

### ۲.۴ دایرکتوری کورپس زنده `data/corpus/`

| فایل | اندازه | یادداشت |
|---|---|---|
| `corpus.jsonl` | **926,667,693 B** (≈926MB) | mtime Nov 6 02:59 |
| `quarantine.jsonl` | 79,145,066 B | 1,147 سطر |
| `rag_linkage.jsonl` | 12,226,280 B | 10,894 سطر |
| `asset_manifest.jsonl` | 32,624,442 B | 39,447 سطر |
| `manifest.json` | 3,392 B | `run_id=corpus-det-2026-11-05T00-53-14`، `exported_at=2026-11-05T00:53:14`، **9,747 ok / 0 invalid / 1,147 quarantined**، `mode=incremental-merge`، schema 1.1 |
| `incremental_state.json` | 296 B | `updated_at=2026-11-06 03:00:16`، watermark 02:45:49/10,896، `last_records_written=9,747` |
| `checksums.sha256` / `metrics.prom` | 239 / 1,727 B | — |
| **کل** | **≈3.8 GB** | **هیچ lock file موجود نیست** |

**دیسک:** 1.5T کل، 1.1T استفاده‌شده، **291G آزاد (80٪)** — هش 85٪ در P9-8.

**جمع‌بندی بخش ۲:** تولید SRT پایدار و سالم است (≈1 جلسه/روز، pipeline هر 30 دقیقه)، LLM از 2026-10-11 خنثی است، و کورپس زنده یک خروجی 1.1 معتبر دارد — اما **هیچ زنجیرۀ خودکاری** از DB به کورپس و از کورپس به RAG وجود ندارد (بخش‌های ۴ و ۷).

---

## ۳. فهری‌گیری Git و ریپوها

> منبع: `ST-01_live_snapshot.md` — خروجی `git ls-remote origin`، `git -C` روی سرور 53، و وضعیت workspace محلی (بازرسی 2026-11-06 ~19:40 UTC).

### ۳.۱ ریپوی اصلی GitHub: `saber13812002/iranseda-crawler-golang-`

> توجه: **خط تیره‌ی آخر نام ریپو واقعی است** (در همه‌ی URLها باید حفظ شود).

| Branch | SHA (برگه‌ی remote) | نقش |
|---|---|---|
| `download-db` (= HEAD remote) | `25935eab826bc4adc922f51e92703a2166eac1ae` | **شاخۀ انتشار** (33,469 فایل) — هدف این گزارش و commit‌های مستندات |
| `main` | `21e3a344a3a3c98ae4ef8925fd545d6487df8900` | — |
| `phase3-radio-rag-service` | `c144f3b1ca14ebb8c19057579cf297269f4764b1` | شاخۀ کد (39,865 فایل؛ سوپرست `download-db` + 6,396 فایل P3-only) |
| `radio-rag-step1-pilot` | `b4efa6d2be4f9b21218d18be45a0dc978a6db866` | — |
| `stage2-corpus-linkage` | `277ffa799a3a6ba280b20abfc3e67f9eff2376bd` | **کد سازندۀ 1.1** (worktree سرور) |

### ۳.۲ وضعیت سه نقطۀ کاری

| نقطه | محل | Branch @ SHA | وضعیت |
|---|---|---|---|
| workspace محلی | `iranseda` (Windows) | `download-db` @ `25935eab8` | هم‌گام با origin؛ ~60 فایل untracked (اسکریپت‌های `.corpus_*`، `.tmp_phase9/`، `corpus/` محلی 1.0) — **باید حفظ شوند و commit نشوند** |
| worktree محلی | `iranseda-corpus-wt` | `phase3-radio-rag-service` @ `9bd4c0bb2faf81ee27828ac2a526d5ff16d1937e` | **کهنه نسبت به remote** (remote واقعی `c144f3b1c`) |
| سرور 53 | `/home/saber/saberprojects/iranseda-crawler-golang-` | `phase3-radio-rag-service` @ `c144f3b1c` | 114 untracked، 0 tracked-dirty؛ **17 commit auto-refresh** از Stage 4 (`a1b9a003a` 11-06 11:30 → `c144f3b1c` 19:30)؛ `git diff 9bd4c0bb2..HEAD -- corpus/ tests/corpus/` **خالی** |
| worktree سرور | `/tmp/saber_stage4_wt` | `stage2-corpus-linkage` @ `277ffa799` | **سازندۀ 1.1** — موقت، در `/tmp` (ST-02) |

### ۳.۳ ریپوی RAG (مستقل) و سایر

- ریپوی RAG: `git.ai.ismc.ir/rag/radio-rag-service.git` → checkout `/home/saber/saberprojects/radio-rag-service`، branch `stage5-citations` @ `71d94d10f5bee04a54c74ae82bdd436f5c815ac6` (بخش ۱۱).
- commit کد کورپس Stage 4: `9bd4c0bb2` = 6 فایل، +1,236/−111 (config 13، database 100، exporter 564، incremental 217، scheduler 34، tests 419) — روی شاخۀ `phase3`.
- سایر checkouts روی 53 (برای ردّ مصرف‌کنندگی RAG): `ai-dump-builder`، `csghub-deployment`، `frontend`، `graph-rag`، `langgraph-neo4j-qa`، `p04_1_evidence`، `p04_staging`، `qa-knowledge-graph-pipeline`، `rag-portal`، `serverstatus`، `sonar`، `sources-portal`، `taghrirqa`، `taghrir-rag`، `tyk-install`.
- `/home/saber/saberprojects/iranseda/` (بدون خط تیره) **ریپو Git نیست** — فقط اسکن شد و رد شد.

### ۳.۴ انحراف‌های ثبت‌شده (دِرماندۀ تمیزکاری)

| # | انحراف | شدت |
|---|---|---|
| 1 | `origin/phase3-radio-rag-service` محلی کهنه (`9bd4c0bb2` در برابر `c144f3b1c` واقعی) | کم — فقط `fetch` |
| 2 | remote یتیم `remotes/53/phase3` (remote «53» حذف شده؛ HEAD آن `e7c9a67ac`) | کم — prune |
| 3 | worktree موقت سرور `/tmp/saber_stage4_wt` (سازندۀ 1.1 در `/tmp`) | **میان** — موضوع P9-1 |
| 4 | 114 فایل untracked روی سرور 53 | کم — نیاز به طبقه‌بندی |
| 5 | 261 blob متفاوت `.srt` بین شاخه‌ها + 44 اِست P3-only + 4 blob کهنه | **میان** — موضوع P9-4 (بخش ۸) |

---

## ۴. کشف سازندۀ Schema 1.1

> منبع: `ST-02_builder_lineage.md` — پروب‌های A–G در بازۀ 2026-11-06 20:23–21:55 UTC + بازسازی پنجرۀ اجرا 02:24–03:15 UTC.

### ۴.۱ جدول خاستگاه (Lineage Table)

| مولفه | مقدار اثبات‌شده |
|---|---|
| کد سازندۀ 1.1 | بسته‌ی `corpus/` در **worktree** `/tmp/saber_stage4_wt` (سرور 53) |
| Branch / HEAD | `stage2-corpus-linkage` @ `277ffa799a3a6ba280b20abfc3e67f9eff2376bd` |
| Commits سازندۀ 1.1 | `d93754c27` (03:43:37) → `3b9b2c7a1` (tests) → `79cebd46d` (report) → `31548e6ab` → `e3fb6f79b` → `277ffa799` (10:03:38، push شده به origin) |
| HEAD ریپوی اصلی سرور | `b3f521322` (phase3) — **فقط کد 1.0** |
| محیط اجرا | کد از worktree، venv از ریپوی اصلی، I/O روی دایرکتوری زنده‌ی `data/corpus/` |
| **Trigger** | **دستی** — کاربر `saber` از طریق SSH از `172.22.6.30` (tailscale)، پنجرۀ **02:26–03:13 UTC 2026-11-06** |
| cron/timer/at/daemon | **ندارد**: هر 17 systemd-timer سرور استاندارد OS؛ journal بازۀ 03:00–03:15 فقط polling `/metrics`؛ `export_enabled=false` در manifest زنده |
| دستورات اجراشده | `python -m corpus.cli incremental --pin --assets` و `python -m corpus.cli rag-linkage` (دو CLI جدا، دو زمان نوشتار) |

### ۴.۲ پنجرۀ اجرا (Timeline، UTC 2026-11-06)

| زمان | رخداد |
|---|---|
| 02:04 | backup کورپس قبلی (9,731، sha `0cdddca2…`) |
| 02:24–02:27 | پروب‌ها + **pinned run1** (9,746 خط، 133.5s، slot -3، `exported_at` با فاصله‌ی خالی — معیوب) |
| 02:34–02:36 | **pinned run2** (9,746 خط، 132.1s، slot -4 — بایت‌های صحیح) |
| 02:50–02:51 | rag-linkage **run1** — 0 doc_id (race: 9,746 خطِ پیش‌افزودن را خواند) |
| 02:58:58 | pre-snapshot |
| 02:59:33–03:00:16 | **incremental merge زنده**: 7 update + 1 append (sid=10896) → **9,747** |
| 03:02:48 | آزمون subsequence-preserving: **PASS** |
| 03:07–03:08 | stage5 Neo4j: SET 20 کلید K1–K22 |
| 03:12:32–03:13:15 | rag-linkage **run2**: 4,148 doc_id (corpus 9,747 / quarantine 1,147 / db sessions 10,894 / llm rows 13,603 / Neo4j radio 4,148 doc_id منحصربه‌فرد / `git ls-tree -r download-db` = 37,747 مسیر) |
| 03:43–03:50 | commitها | 10:03 | push `277ffa799` |

### ۴.۳ پاسخ ۹ پرسش کلیدی (Q1–Q9)

| # | پرسش | پاسخ (با شواهد) |
|---|---|---|
| Q1 | کدام کد اجرا شد؟ | کد 1.1 worktree + venv ریپوی اصلی + I/O روی دایرکتوری زنده |
| Q2 | `rag_linkage.jsonl` را چه کسی ساخت؟ | `rag_linkage.main` از `cli.py:148` (دستور `rag-linkage`) |
| Q3 | sidecarها توسط چه کسی نوشته شدند؟ | **همان** main writer (فرآیند `rag-linkage`) |
| Q4 | `rag-linkage` چه می‌خواند؟ | 5 جدول MySQL (10,894 / 59 / 13,603 / 1 / 22) + اسکن `downloads/` (42,155 فایل / 24,674 stem / 0 خطا) + Neo4j `radio` فقط‌خوان (fail-closed `_CYPHER_WRITE_TOKENS`؛ fallback `doc_id = <stem>__s{session_id}`، `mapped_from: db_derived`) + `git ls-tree -r download-db` |
| Q5 | **اتصال خودکار RAG وجود دارد؟** | **خیر** — grep همه‌ی مراجع `radio-rag-service` در 6 رِپوی RAG + اسکن `/proc/*/fd` = خالی |
| Q6 | «به‌روزرسانی 03:00» چه چیزی بود؟ | **هیچ trigger خودکاری** — همان پنجرۀ 45 دقیقۀ دستی |
| Q7 | نوشتار هم‌زمان در پنجره؟ | خیر — اجراها پشت‌سرهم؛ اسکن fd خالی |
| Q8 | ناهمغری‌ها (races) | ۴ مورد — جدول ۴.۴ |
| Q9 | آیا هر فایل یک writer منطقی دارد؟ | بله (ولی نه با قفل) |

### ۴.۴ چهار ناهمگرثگی اثبات‌شده

| # | race | شواهد |
|---|---|---|
| 1 | **CLI هیچ قفلی ندارد** — قفل `data/corpus/.state.lock` فقط در حلقۀ scheduler گرفته می‌شود، نه در `corpus.cli incremental` | `scheduler.py:35-54` (`_acquire_lock`) |
| 2 | `rag-linkage` حین merge، corpus زنده را می‌خواند | run1 خط‌های **9,746** را پیش از append خواند → 0 doc_id |
| 3 | run1/run2 غیرتعیینی: `exported_at` با فاصله در برابر `T` → بایت‌های متفاوت | run1 معیوب، run2 لازم شد |
| 4 | چرخش ۳-اسلاتی `previous/` اسلات -1 را **همان روز** که archive run1 در همان تاریخ بود حذف کرد | `_prune_previous` (exporter.py 435-442) |

**نتیجه‌ی ST-02 (3 اصل):** (a) کد 1.1 باید به شاخۀ اصلی/پایدار برسد + CI؛ (b) اتصال RAG باید طراحی و پیاده شود؛ (c) پیش از هر خودکارشدن: **قفل بین‌فرآیندی + run_id منحصربه‌فرد + archive قوی‌تر**. این سه دقیقاً همان هسته‌ی P9-5 است (بخش ۱۶).

---

## ۵. فهری‌گیری اسکیمای دیتابیس

> منبع: `ST-03_db_classb.md` — بازرسی 2026-11-06 23:08–23:46 UTC. **MySQL 8.0.46**، DB `radio` @ `127.0.0.1:3308`، کاربر `n8nuser`. guard فقط‌خوان در `corpus/config.py` + `corpus/database.py` (فقط `SELECT`/`SHOW`/`DESCRIBE`/`DESC`/`WITH` پذیرفته می‌شود).

### ۵.۱ ۱۸ جدول (تعداد + تازه‌ترین زمانی + producer)

| # | جدول | ردیف‌ها | تازه‌ترین ts | producer (کد) |
|---|---|---|---|---|
| 1 | `radio_program_sessions` | **10,903** (در لحظه‌ی A6: 10,905 — crawl زنده) | `updated_at` 2026-11-06 22:27:31 | `crawler/scan.go:216` + `download_db.go:113,226` |
| 2 | `radio_programs` | **59** | created 2026-10-28 19:50:05 | `crawler/crawler.py:87` + `dashboard/logic.py:1802` + `scripts/backfill_program_times.py:137` |
| 3 | `llm_output` | **13,603** | `finished_at` 2026-10-11 11:30:01 | `dashboard/llm_jobs.py:1387,1516` |
| 4 | `llm_job` | 1,099 | — | `llm_jobs.py:1482,1679` |
| 5 | `pipeline_runs` | 690 (pipeline=248 / site=440) | created 2026-11-06 23:00:10 | **در ریپو نیست** (n8n/orchestrator) |
| 6 | `publication_task` | 343 | — | `dashboard/reporter.py:230` |
| 7 | `program_settings` | 32 | — | `scripts/discover_new.py:67,161` (UNIQUE `program_id`) |
| 8 | `crop_detection` | 22 (needs_review=20، cropped=2) | — | `llm_jobs.py:1013` (UNIQUE `session_id`) |
| 9 | `program_discovery` | 5 | — | `dashboard/logic.py:1813` (UNIQUE `m`) |
| 10 | `pipeline_steps` | 6 (seed) | — | — |
| 11 | `program_score` | 1 | — | — |
| 12 | `prompts` | 4 (seed) | — | — |
| 13 | `asr_output` | 1 | — | `dashboard/roshan_pilot.py:245` (uq_asr UNIQUE(`session_id`,`provider`,`pipeline_version`,`audio_sha256`)) |
| 14–18 | `programs`، `subtitles`، `downloaded_files`، `radio_program_session_files`، `backfill_list` | **0** (خالی) | — | — |

**محدودیت‌های کلیدی:** `uq_session_program_link UNIQUE(program_id, link)` در sessions ← **ریشه‌ی Class B**؛ `uq_out UNIQUE(session_id, job_type, model)` در `llm_output`؛ `radio_programs` **فقط PRIMARY** — **هیچ UNIQUE روی `url` یا `(radio_id,m)` ندارد** ← ریشه‌ی 27 جفت تکراری. تنها FK فیزیکی در کل schema: `subtitles.program_id → programs.id` (هر دو جدول خالی). همه‌ی joinهای یتیم = **0**.

**job typeهای `llm_output`:** correct_subtitles 4,245 / correct_text 4,212 / summary 4,212 / full_text 933 / qa 1.

### ۵.۲ نگاشت ۱۵ نیاز کورپس به دیتابیس

| # | نیاز کورپس | منبع در DB | وضعیت |
|---|---|---|---|
| 1 | نام برنامه | `radio_programs.name` | ✅ (نیاز به TRIM — نمونه‌ی `" پرسمان اعتقادی\n\n\t"`) |
| 2 | شناسه‌ی پایدار برنامه | `radio_programs.id` + `(ch,m)` از `url` → `program_uid = iranseda:prog:ch{ch}:m{m}` | ✅ (با احتیاط: 27 جفت تکراری) |
| 3 | **presenter (برنامه‌رانی)** | **هیچ جدولی** | ❌ **MISSING** — `speakers.items=[]` با `missing_reason: "no verified source table in database (stage-1 finding #9)"` |
| 4 | زمان پخش | بدون ستون — مشتق از `filename` + `radio_programs.time/start` | ⚠️ |
| 5 | تاریخ پخش | بدون ستون — فقط جلالیِ `filename` (`JJ-MM-DD-HH-MM`)؛ **هرگز `created_at`** | ⚠️ |
| 6 | y/m/d | `corpus/jalali.py` (jdatetime 6.1.1) | ⚠️ |
| 7 | **عنوان اپیزود** | بدون ستون — فقط `llm_output.content` با `job_type='summary'` (4,212 ردیف، ساختار‌یافته نیست) | ❌ |
| 8 | لینک آرشیو | `radio_program_sessions.link` (`…epgarchivePart/?VALID=TRUE&ch=<ch>&e=<e>`) | ✅ |
| 9 | شناسه‌ی کانال | `ch` از `link` + `radio_id` | ⚠️ |
| 10 | شناسه‌ی EPG | `e` از `link` | ⚠️ |
| 11 | مسیر raw SRT/TXT | فقط روی دیسک: `downloads/<stem>.srt` با کلید `srt_filename` | ⚠️ |
| 12 | متن اصلاح‌شده | `llm_output.content/content_en` (correct_text/full_text) + `file_relpath` | ✅ |
| 13 | مسیر raw SRT | `radio_program_sessions.srt_filename` | ✅ |
| 14 | SRT اصلاح‌شده | `llm_output.file_relpath` (correct_subtitles؛ محتوا در `srt_content`) | ✅ |
| 15 | audio | `sessions.filename` (mp4) + `link` → `audio.url` | ✅ (اما فایل mp3 در دسترس نیست — بخش ۹) |

### ۵.۳ نمونه‌های ماسک‌شده (برای بازسازی)

| ردیف | مقادیر (حساسیت: عمومی — بدون رمز) |
|---|---|
| `radio_program_sessions` id=**6217** | `program_id=31`، `link=…?VALID=TRUE&ch=14&e=153278467`، `filename=radio-maaref-04-09-05-16-00.mp4` / `.srt`، `status=subtitled`، `created_at=2026-10-22 21:34:06` |
| `radio_programs` id=**60** | `name=«شفا»`، `url=…/Program/?VALID=TRUE&ch=14&m=044168`، `time_description=«چهارشنبه 6 آبان 1405 ساعت 14:50 به مدت 10 دقیقه»`، `radio=رادیو معارف`، `radio_id=14`، `is_legacy=0` |

**جمع‌بندی بخش ۵:** DB برای 13 از 15 نیاز، منبع کافی دارد؛ 2 نیاز (presenter، episode title) **ساختگی** هستند و باید additive در mapper (P9-3) حل شوند — نه با نوشتار DB.

---

## ۶. مقایسۀ اسکیمای کورپس

> منبع: `ST-02_builder_lineage.md` (Part B) + `STAGE_3/STAGE_4` — کورپس زنده در لحظه‌ی پروب A (2026-11-06 20:23 UTC).

### ۶.۱ فیلدهای additive در 1.1 (چیزی حذف نشده است)

| فیلد 1.1 | نمونه | 1.0 |
|---|---|---|
| `session_uid` (+ `session_uid_status`) | `iranseda:ch14:e152507883` | — (تازه) |
| `program_uid` (+ `program_uid_status`) | `iranseda:prog:ch14:m044116` | — (تازه) |
| بلوک `linkage` | `{linkage_version, timezone, links[{type: episode\|day_archive\|time_slot\|program_page, url, url_normalized, status, reason}], air_date_status, validity, day_of_week, quarantined}` | — (تازه) |
| `broadcast.{timezone, validity{status,reasons}, day_of_week}` | — | — (تازه) |
| کلیدهای تازه‌ی manifest + ۲ فایل sidecar | `rag_linkage.jsonl`، `asset_manifest.jsonl` | — (تازه) |
| `audio.local_exists` | فیلد اسکن دیسک | **وجود دارد** (تنها تفاوت نمای 1.0: 257 رکورد در پنجرۀ Stage 4 تغییر وضعیت داد) |

**نتیجه‌ی کلیدی:** نمای 1.0 بر روی خروجی 1.1 **بایت-به-بایت یکسان** است به‌جز `audio.local_exists`. در مقابل، mapper 1.0 رشته‌ی `"1.0"` را سخت‌کد کرده (`mapper.py:474`) و validator 1.0 هر رکوردی با `schema_version != "1.0"` را **رد** می‌کند (`validator.py:88`) → اجرای 1.0 روی کورپس 1.1 = **دگرنسخه‌ی مخرب** (بخش ۱۰).

### ۶.۲ فهری‌گیری فایل‌به-فایل کورپس زنده (با SHA)

| فایل | بایت | خط | mtime (UTC 11-06) | SHA256 |
|---|---|---|---|---|
| `corpus.jsonl` | 926,667,693 | **9,747** | 02:59:30.912 | `753fb9deff885d33473e453e8006a9e77a87126ae2c21c9b2eeedd398d9196fb` |
| `quarantine.jsonl` | 79,145,066 | **1,147** | — | `ff07659990f8e04543f8e47cd2fb6839acb2b1f791d942ddce235a561a1208c1` |
| `stats.json` | 21,052 | — | — | `f29f0dfc…` |
| `manifest.json` | 3,392 | — | 03:00:16.110 | `d5a53f7d6425a08c3c0d8ce3de6ba68e92ec98e6476355ca3f927c38f29887f8` |
| `checksums.sha256` | 239 | — | — | — |
| `metrics.prom` | 1,727 | — | — | — |
| `incremental_state.json` | 296 | — | — | — |
| `rag_linkage.jsonl` | 12,226,280 | **10,894** | 03:13:15.490 | `05caa88dfa6afc965d7a36be6f63f5c8f118da66f2727cbc4b72c68492c0ebd8` |
| `asset_manifest.jsonl` | 32,624,442 | **39,447** | 03:13:15.846 | `8a43dca52f7f06494b4113fb1156a364dd6809f80a8ff319231c1a32d24f99c5` |
| `reconcile_report.json` | 291 | — | 2026-11-04 (کهنه) | — |
| `class_b_investigation.jsonl` | 2,796,439 | 1,148 | 2026-11-04 21:39 (کهنه) | — |
| `invalid.jsonl` | **غایب** | — | — | `invalid_file: null` |

**اسلات‌های `previous/`:** `-2` = `corpus-det-2026-11-05T00-53-14` (full، 9,731، 125.8s، 11-05 02:00)؛ `-3` = full 9,746 (133.5s، 02:26:54 — run1)؛ `-4` = full 9,746 (132.1s، 02:36:15 — run2)؛ **`-1` حذف شده** (race #4 جدول ۴.۴).

### ۶.۳ `K_ASSET_KEYS` (rag_linkage.py 59-67)

| asset در corpus | کلید K در sidecar |
|---|---|
| `raw_srt` | `raw_srt_url` |
| `corrected_srt` | `corrected_srt_url` |
| `full_txt` | `full_text_url` |
| `corrected_txt` | `corrected_text_url` |
| `summary_fa` | `summary_url` |
| `summary_en` | `summary_en_url` |
| `audio` | `audio_url` |
| `raw_txt` | **فاقد کلید K** (شکاف — بخش ۸) |

### ۶.۴ شاخص‌های کیفیت (سنجش روی 9,747 رکورد زنده)

| شاخص | مقدار |
|---|---|
| یکتایی `record_id` | **9,747/9,747** (0 تکراری) |
| joinهای نقطه‌ای (خط 0/2000/5000/8000/9746) | همه سبز: (sid=3,pid=1) «بر كرانه نور»، (2003,18)، (5003,1)، (8793,50)، (10896,53) |
| `legacy_program_duplicate_merged` (stats) | 9,457 |
| program_id منحصربه‌فرد | 58 (corpus) / 59 (DB) — `program_ids_all` می‌تواند چندعضوی باشد (مثلاً `[1,29]`) |
| `audio.local_exists=true` | 2,650 |
| spot-check اِست‌ها (200) | 160 موجود / 40 غایب = **دقیقاً همان رکوردهای `exists_on_disk:false`** (همه audio/`​.mp3`) |
| doc_id در `rag_linkage` | 10,568 سطر دارند (4,148 Neo4j + 6,420 `db_derived`)، **326 بدون** |
| `air_date_status` | unverified **9,347** / none **1,442** / impossible **105** |
| record_idهای `rag_linkage` در corpus | 9,747/9,747 |
| مجموعه‌ی کلیدها | `rag_linkage`: 15 منحصربه‌فرد؛ `asset_manifest`: 1 در 39,447 سطر |
| پسوند اِست‌ها | `.txt` 19,916 / `.srt` 8,963 / `.mp4` 7,588 / `.mp3` 2,980 |

---

## ۷. خاستگاه داده (Data Lineage)

زنجیرۀ کامل از منبع تا UI، با **محل دقیق هر handoff** و شکاف‌های خودکاری:

```
 [1 IranSeda]          [2 DB]                [3–5 Metadata/ASR/LLM]      [6–7 Builder+Export]           [8–9 Validation+Sidecars]
 iranseda.ir          MySQL radio          scan/discover/download       corpus/ 1.1 (worktree)          validate → promote
 headend1 (timeout)   18 tables            llm_output (خنثی از 10-11)   incremental --pin --assets      rag-linkage (دستی جدا!)
      │                   │                        │                           │                              │
      └── crawl 15,45 ────┴── SRT/TXT/LLM ─────────┴────── read-only (n8nuser) ─┴───────────────┬─────────────────┘
                                                                                               │
                                                    ┌──────────────────────────────────────────┘
                                                    v
 [10 HF] GATED/BLOCKED              [11 Neo4j Ingestion]            [12 Retrieval]        [13 UI]
 publisher.py (هرگز اجرا نشده)      neo4j_linkage.py (دستی stage5)  radio_api 8043         radio_frontend 8044
 corpus↔GitHub↔IranSeda             79,350 chunks، K1–K22 SET       KNN+RRF                172.20.1.53:8044
```

### ۷.۱ جدول handoffها و شکاف‌ها

| handoff | وضعیت امروز | مکانیزم | شکاف |
|---|---|---|---|
| IranSeda → DB | خودکار | cron `15,45 run_pipeline.sh` (flock) | headend timeout (64 شکست/run) |
| DB → builder | خودکار در هر run | `watermark_clause` فقط‌خوان | `llm.finished_at` در شرط نیست (خوابیده — بخش ۱۰) |
| builder → `data/corpus/` | **دستی** | CLI `incremental --pin --assets` از worktree `/tmp` | بدون قفل CLI، بدون cron، `export_enabled=false` |
| corpus → sidecarها | **دستی (CLI دوم)** | `rag-linkage` | **race اثبات‌شده** (می‌خواند حین merge) + بیرون از اتمیک‌دومین |
| sidecar → Neo4j | **دستی** | `corpus/neo4j_linkage.py` (1,047 خط، stage5) | **357 جلسه‌ی کهنه** (10,544 در برابر 10,901) |
| corpus → HF | **هرگز اجرا نشده** | `corpus/publisher.py` | BLOCKED (حقوق + توکن) — بخش ۱۲ |
| Neo4j → کاربر | خودکار (درخواستی) | `radio_api` KNN/RRF | 4/7 نقل‌مراجعه؛ variant mismatch — بخش ۱۱ |

**مهم:** کورپس **مشتق و قابل بازسازی کامل** است (از DB + `downloads/` — بخش ۱۴)؛ بنابراین هیچ step شکسته‌ای دیتا را از بین نمی‌برد، فقط تازگی/اتصال را.

### ۷.۲ مثال ردیابی سر-به-سر (record خط صفر کورپس زنده)

| لایه | مقدار اثبات‌شده |
|---|---|
| منبع (IranSeda) | `link = …/epgarchivePart/?VALID=TRUE&ch=14&e=152507883` |
| DB | `radio_program_sessions.id=3`، `program_id=1` (برنامه «بر كرانه نور»، رادیو معارف) |
| builder | `record_id = iranseda:ch14:e152507883` = `session_uid`؛ `program_uid = iranseda:prog:ch14:m{m}` |
| فایل | خط **0** `data/corpus/corpus.jsonl` (sha256 کل فایل `753fb9de…`) |
| sidecar | `rag_linkage.jsonl`: `doc_id = <stem>__s3`؛ `asset_manifest.jsonl`: ردیف‌های C1..C14 با sha256/size/`local_exists` |
| RAG | گره‌های Chunk `…__s3::subtitle_window::N` در `radio` و `radio-4b` (هر دو 79,350 chunk) → `radio_api` → `:8044` |
| GitHub | URLهای raw در `rag_linkage` (فقط برای اِست‌های منتشرشده روی `download-db`) — **خودِ رکورد کورپس URL ندارد** (بخش ۸) |

---

## ۸. پوشش URLهای GitHub

> منبع: `ST-04_url_linkage.md` — بازرسی ~00:44–01:10 UTC 2026-11-07. **نمونه: 126 رکورد از 30 برنامه** (120 رکورد هسته با گام ثابت 81 روی `session_id` + 6 لبه؛ 119 در ch14 + 7 در ch18؛ شامل 5 نشانگر Class B). انضباط: فقط GET، timeout 20s، فاصله ≥0.5s؛ 131+4 درخواست GitHub؛ هر دو میزبان (سرور 53 + محلی) HTTP 200.

### ۸.۱ شاخه‌ی انتشار و درخت‌ها

| مورد | مقدار |
|---|---|
| **شاخه‌ی انتشار** | `download-db` (HEAD remote) |
| درخت `download-db` | **33,469** فایل |
| درخت `phase3-radio-rag-service` | **39,865** فایل |
| اثبات سوپرست | 0 فایل فقط‌در-`download-db`؛ **6,396 فایل فقط‌در-phase3** |
| اختلاف blob کل‌ریپو | **261 فایل `.srt`** با محتوای متفاوت بین دو شاخه |
| الگوهای مسیر | raw SRT: `downloads/<srt_filename>`؛ raw TXT: `downloads/<stem>.txt`؛ اصلاح‌شده: `downloads/cleaned/<stem>.correct.srt/.txt`؛ full: `downloads/cleaned/<stem>.full.txt`؛ summary: `downloads/cleaned/<stem>.summary.txt` |
| قالب URL | `https://raw.githubusercontent.com/saber13812002/iranseda-crawler-golang-/<branch>/<relpath>` (خط تیره‌ی آخر نام ریپو واقعی است) |

### ۸.۲ نتایج A (136 ردیف record×asset → 131 درخواست dedup)

| آزمون | نتیجه |
|---|---|
| **A1–A2 زنده بودن** | **136/136 HTTP 200 — صفر 404** (11 رکورد×5 اِست + 14×4 روی `download-db` + 3×5 روی phase3 + 5×2 raw روی A3) |
| **A3 SHA256 در برابر corpus** | **32/38 مطابق؛ 6 عدم‌مطابقت = 4 فایل raw_srt منحصربه‌فرد** |
| blob sha1 | 136/136 مطابق با درخت `download-db` |

**4 فایل `raw_srt` کهنه (STALE) روی `download-db`:**

| فایل | corpus/phase3 | `download-db` |
|---|---|---|
| `radio-maaref-04-01-27-02-00.srt` | `c1c966a3…` | `d09e4b00…` |
| `radio-maaref-97-12-28-20-30.srt` | `e710718f…` | `c40860f1…` |
| `radio-maaref-97-01-10-22-30.srt` | `b3ec1867…` | `33410da4…` |
| `radio-maaref-04-03-01-02-00.srt` | `f3897051…` | `39a2bf63…` |

برای هر ۴ مورد: محتوای phase3 == corpus → یعنی **`download-db` کهنه است** (پشت phase3 مانده)، نه corpus.

**A4 عضوی بودن (نمونه‌ی 126):**

| asset | رکوردها | هر دو شاخه | فقط phase3 | هیچ‌کدام | متفاوت |
|---|---|---|---|---|---|
| raw_srt | 118 | 74 | **44** | 0 | 4 (کهنه) |
| raw_txt | 118 | 74 | **44** | 0 | 0 |
| summary | 56 | 56 | 0 | 0 | 0 |
| corrected_txt | 56 | 56 | 0 | 0 | 0 |
| corrected_srt | 56 | 56 | 0 | 0 | 0 |
| full_txt | 11 | 11 | 0 | 0 | 0 |

**جمع‌بندی:** روی شاخه‌ی انتشار، **44+44 اِست raw (SRT/TXT) و 4 blob کهنه** وجود ندارند/کهنه‌اند؛ کل‌ریپو **261 blob `.srt` غیر-canonical** دارد. رفع‌شدن همه = P9-4.

---

## ۹. پوشش URLهای IranSeda

> منبع: `ST-04_url_linkage.md` (بخش B2). 106 درخواست IranSeda روی ۴ خانوادۀ URL؛ **0 ناهنجاری ساخت**: 120/120 URLهای ساخته‌شده دقیقا‌ً با `corpus linkage.links` یکسان بودند.

### ۹.۱ چهار خانوادۀ URL و وضعیت (نمونه‌ی 30 برنامه)

| خانواده | قالب | نتیجه |
|---|---|---|
| program_page | `https://radio.iranseda.ir/Program/?VALID=TRUE&ch={ch}&m={m}` | **30/30 معتبر** (`m_id` در 29 مورد در بدنه، نام در title) |
| day_archive | `…/timeArchive/?…&ch={ch}&d={d}` — `d` = **میلادی M/D/YYYY بدون صفر** از `broadcast.gregorian_date` | **24/30** (7 no_date + 5 impossible گم؛ 3 مورد HTTP-تست‌شده از بین گم‌ها = no_date: `e152837312`، `e152821909`، `e152872896`) |
| time_slot | `…/timeArchivePart/?…&ch={ch}&ti={ti}&d={d}` — `ti` = `broadcast.gregorian_time` (HH:MM) | **23/30** (نامعتبر: `e152946466` ti=02:00 d=6/24/2025 رندر نشد + 3 impossible) |
| episode | `…/epgarchivePart/?…&ch={ch}&e={e}` (e از رکورد، `ek_source=link`) | **14/30 معتبر، 16 نامعتبر** |

**اثبات OQ-1 (قانون فرمت تاریخ):** `d=17/8/1403` (شکل جلالی) → HTTP 200 اما بدنه `Conversion failed to value for argument of type java.util.Date` → **سایت فقط M/D/YYYY میلادی می‌پذیرد**. هر URL جلالی‌شکل = 200 فریبنده.

### ۹.۲ ریشه‌ی 16 URL episode نامعتبر

| نوع | تعداد | ریشه و راه‌حل |
|---|---|---|
| `title_mismatch` | **10** | صفحه‌ی درست سرویس می‌شود (e_id دو بار در player embed) ولی املای سایت با corpus فرق دارد: «برکرانه نور» در برابر «بر كرانه نور»، «پرسمان- تاریخی» در برابر «پرسمان تاریخی»، «امیر جانها» در برابر «امیر جان ها»، «امیرمؤمنان/امیر مومنان» در برابر «امیر مؤمنان» → **حل: عادی‌سازی عنوان** (P9-4) |
| `id_mismatch` | **6** | HTTP 200 اما بدنه خالی، بدون e_id: `e152809853`، `e152860343`، `e152902166` (دارای تاریخ) + `e152837312`، `e152821909`، `e152872896` (بدون تاریخ) |

### ۹.۳ پوشش C-1 (نمونه‌ی 126 رکورد)

| نوع | V/T (اعتبار/تأیید) | UNVER | missing | invalid | STALE |
|---|---|---|---|---|---|
| program_page | 30 (HTTP) | 96 | — | — | — |
| day_archive | 24 | 90 | 12 | — | — |
| time_slot | 23 | 90 | 12 | 1 | — |
| episode | 14 | 96 | — | **16** | — |
| raw_srt | 70 | — | 52 (P3-only 44) | — | **4** |
| corrected_srt | 56/56 | — | — | — | — |
| full_txt | 11/11 | — | — | — | — |
| corrected_txt | 56/56 | — | — | — | — |
| summary | 56/56 | — | — | — | — |
| raw_txt | 74 | — | 52 (P3-only 44) | — | — |
| **audio** | **0** | — | — | — | — |

- **C-2:** 17 رکورد با ≥1 URL نامعتبر؛ 115 رکورد با ≥1 ناقص؛ **0 رکورد با همه V/T**؛ 11 رکورد با ≥1 سالم و بدون نقص.
- **C-3:** جدول برنامه‌به‌برنامه برای 30 برنامه در `.tmp_phase9/st04_c_tables.md`.

### ۹.۴ audio: 0/126

- `audio.url` در همه‌ی 126 رکورد = **URL صفحۀ epgarchivePart** (نه mp3).
- **0 فایل mp3 در هر دو درخت GitHub** (33,469 + 39,865 فایل اسکن شدند).
- خطای headend (عین متن): `Error while downloading: Get "https://headend1.iranseda.ir/DLFile/?VALID=TRUE&vid=2795816_201": dial tcp 185.109.247.100:443: connect: connection timed out`.
- خود سایت IranSeda قابل دسترس است (200 از هر دو میزبان) — مشکل فقط در headend است.

### ۹.۵ شکاف‌های C-4/C-5 (خروجی برای فاز ۹)

| # | شکاف |
|---|---|
| 1 | **GitHub URLها در رکوردهای corpus نیستند** — فقط در sidecar `rag_linkage.jsonl` و فقط برای اِست‌های `published` (شاخه از env `GITHUB_BRANCH`) → مصرف‌کنندۀ RAG باید join کند |
| 2 | **episode 16/30 نامعتبر = بزرگ‌ترین شکست زنجیرۀ اتصال** |
| 3 | `download-db` برای 4 از 261 raw_srt کهنه است |
| 4 | 44/118 اِست raw فقط روی phase3 (در branch انتشار نیستند) |
| 5 | `raw_txt` کلید K ندارد (شمارش از K8 به K10 می‌پرد) |
| 6 | audio = فقط URL صفحه (نه mp3) |
| 7 | no_date/impossible در نمونه: 7+5 (2118–2120؛ مثلا sid 238 «امیر مؤمنان» 1498-12-18 → gregorian **2120**-03-08)؛ کل کورپس: **1,442 + 105 = 1,547 رکورد بدون تاریخ معتبر** |

---

## ۱۰. سازگاری برون‌آیی افزایشی

> منبع: `ST-05_incremental_compat.md` — بازرسی 2026-11-07 01:45–01:55 UTC؛ 1.0 خوانده‌شده از workspace محلی، 1.1 از طریق `cat` روی سرور از `/tmp/saber_stage4_wt`.

### ۱۰.۱ وضعیت زنده‌ی `incremental_state.json` (متن کامل)

```json
{"updated_at":"2026-11-06 03:00:16",
 "watermark":{"sessions_updated_at":"2026-11-06T02:45:49","sessions_max_id":10896,
              "llm_finished_at":"2026-10-11T11:30:01","llm_max_id":15324},
 "last_run_id":"corpus-det-2026-11-05T00-53-14","last_records_written":9747}
```

اسلات‌های `previous/` در لحظه‌ی بازرسی: `-2` (schema 1.0، 9,731، Nov 5 01:59، wm 2026-11-05T00:53:14/10,880، 42,368 فایل)؛ `-3`/`-4` (1.1، 9,746، تولید 02:26:54/02:36:15، 10,893 sessions)؛ `-1` پاک‌شده. `checksums.sha256` دقیقاً 3 ورودی (corpus/quarantine/stats؛ `invalid.jsonl` غایب). `reconcile_report.json` کهنه (Nov 4، 9,721).

### ۱۰.۲ جدول 11 مکانیزم (1.0 در برابر 1.1)

| # | مکانیزم | 1.0 | 1.1 | ریسک/یافته |
|---|---|---|---|---|
| 1 | تشخیص تغییر + `--pin` | watermark `(updated_at IS NULL) OR updated_at >= wm−12h OR id > max_id` (فقط sessions) | همان + `--pin` که `exported_at/run_id` را از manifest زنده یخ می‌زند → no-op بایت-یکسان | `llm.finished_at` در شرط نیست |
| 2 | سیگنال `session.updated_at` | یکسان | یکسان | DB الان: max_updated_at 2026-11-07 01:49:56، max_id 10,908، کل 10,906، NULL 0 → **بسته‌ی بعدی = 1,572 رکورد (≈14.4٪)**؛ همپوشانی 12h → rescan هر بار + بازمحاسبه‌ی sha256 دیسک |
| 3 | `llm.finished_at` | در wm ردیابی (192-209) اما **در WHERE نه** (211-238) | همان | **هر 13,603 ردیف llm دارای `finished_at > session.updated_at` است**؛ 0 تکمیل پس از wm ذخیره‌شده (2026-10-11) → **ساختاری شکسته، فعلاً خوابیده**؛ خروجی LLM تازه روی session بی‌تغییر برای incremental نامرئی می‌ماند |
| 4 | ASR (1 ردیف) | بارگذاری per-batch | یکسان | — |
| 5 | crop (22) | یکسان | یکسان | — |
| 6 | امضای دیسک (~42k فایل) | اسکن در هر run | اسکن در هر run | **خطوط merge‌شده‌ی دست‌نخورده، path/size/sha256 کهنه نگه می‌دارند** (ST-04: 261 متفاوت، 4 کهنه) → گسست لینک فوری |
| 7 | ذخیره/بازیابی watermark | `incremental_state.json` | ساختار یکسان | 12h برای sessions معقول؛ معادل برای llm نیست |
| 8 | قفل | فقط pidfile در scheduler (هر دو نسخه یکسان) | همان | **CLI هیچ قفلی ندارد**؛ race مشاهده‌شده: rag-linkage run1 9,746 خطِ پیش‌افزودن را خواند (ST-02) |
| 9 | reconcile | byte-identical (incremental.py 87-126، scheduler.py 67-80) | یکسان | گزارش زنده کهنه (Nov 4، 9,721)؛ شواهد cron ندارد |
| 10 | promote اتمیک | tmp+`os.replace` تک‌فایل، بدون archive | staging→validate→archive→promote→checksums→prune (`RETENTION=3`) | **دومین اتمیک = فقط مجموعه‌ی corpus — linkage نیست** |
| 11 | archive/rollback | ندارد (overwrite در جای خود) | ۳ اسلات | اسلات‌ها فقط corpus/manifest/quarantine/stats (بدون checksums و linkage)؛ `_LIVE_RE`/`_CHECKSUM_NAMES`، rag_linkage/asset_manifest را **نمی‌شکنند** → **ریسک فوری: sidecarها بدون archive، بدون checksum، بدون rollback** |

### ۱۰.۳ هفت حکم Q1–Q7

| # | حکم | خلاصه‌ی استدلال |
|---|---|---|
| Q1 | **1.1 SAFE / 1.0 BROKEN+DESTRUCTIVE** | 1.1 corpus زنده را بایت-به-بایت نگه می‌دارد (merge `[merge_new_lines.get(rid, raw) for rid, raw in st["order"]]` + append؛ upsert روی id همان؛ تصادف→quarantine؛ `--pin` no-op مشاهده‌شده: 8 sessions، +7/+1، 53.5s). 1.0 روی زنده‌ی 1.1: `corpus.jsonl` را **بدون merge/archive** replace می‌کند (9,747 → ~1,572) + mapper سخت‌کد `"1.0"` (`mapper.py:474`) → دگرنسخه + رد توسط validator (`validator.py:88`) → **از دست دادن فاجعه‌بار؛ 1.0 هرگز نباید روی دایرکتوری زنده اجرا شود** |
| Q2 | sidecarها | incremental دست نمی‌زند (در `_LIVE_RE` نیستند، merge نمی‌خواند، در `_CHECKSUM_NAMES` نیستند) ولی **AT RISK — بی‌حفاظت** → خزش خاموش (race در ST-02 اثبات شد) |
| Q3 | تازگی LLM | **AT RISK** (تأخیر ساختاری، فعلاً خوابیده) |
| Q4 | گسست لینک | link rot بدون سازوکار بی‌اعتبارسازی (cache اعتبارسنجی فقط ورودی rag_linkage؛ غیبت → لینک 'eligible' می‌ماند) |
| Q5 | انحراف | نه بایت-گم: (1) merge هرگز حذف نمی‌کند → zombie؛ (2) جابه‌جایی legacy (27 جفت) → 2 خط برای یک session؛ (3) تغییر فرمول record_id → mass append + orphan + mass quarantine؛ (4) حذف فایل دیسکی → امضای مرده |
| Q6 | full ≠ incremental | merge provenance/disk/1.1 قدیمی نگه می‌دارد؛ merge نیازمند `shard_lines==0`؛ provenance/run_id متفاوت مگر `--pin` → **full دوره‌ای لازم است** |
| Q7 | سازندۀ تکی | **FEASIBLE** — بسته‌ی ۸-گامی «بازسازی، نه مکانیزم تازه» (بخش ۱۴) |

**حکم نهایی ST-05:** worktree 1.1 (`stage2-corpus-linkage` @ `277ffa799`) به‌عنوان **تنها ناشر** حفظ شود؛ `corpus/` محلی 1.0 هرگز روی دایرکتوری زنده اجرا نشود.

---

## ۱۱. معماری RAG (بازرسی ۱۰ لایه‌ای)

> منبع: `ST-06_rag_hf.md` — بازرسی ~02:14–02:47 UTC 2026-11-07. بودجه: 2 درخواست API (health + 1 chat)، 16 کوئری Neo4j فقط‌خوان، 3 GET عمومی HF. رازها ماسک شدند (`NEO4J_PASSWORD`، `LITELLM_API_KEY`، `RAG_SERVICE_TOKEN`، `HF_TOKEN` = placeholder خالی 0-بایتی).

### ۱۱.۱ هویت و استقرار

| مورد | مقدار |
|---|---|
| ریپو | `git.ai.ismc.ir/rag/radio-rag-service.git` — **ریپوی مستقل** (زیر ریپوی crawler نیست) |
| checkout / branch / HEAD | `/home/saber/saberprojects/radio-rag-service` / `stage5-citations` / `71d94d10f5bee04a54c74ae82bdd436f5c815ac6` |
| کد | `api.py` 875 خط FastAPI؛ frontend `index.html` 82 / `app.js` 248 / `style.css` |
| کانتینرها | `radio_api` (image `mrbaqeri/qa_lang_neo4j_mesbah:1.0.0`، **8043→8003**، Up 15h) + `radio_frontend` (nginx:alpine، **8044→80**، Up 41h؛ `nginx.conf:27-36` را `/api/` به radio_api:8003 می‌راند) |
| Neo4j | `neo4j_db` (neo4j:2025.10.1-enterprise، bolt 7687)؛ bind-mount `api.py → /app/app/api.py` |
| LLM | LiteLLM `http://172.30.0.133:4000/v1` (health live)، مدل تولیدی `qwen38` |
| دامنه | `radio.ai.ismc.ir` **BLOCKED** (نیاز به root/BT-panel روی 52؛ بدون vhost/cert)؛ URL تولید: **`http://172.20.1.53:8044`** |

### ۱۱.۲ جدول 10 لایه

| لایه | وضعیت | شواهد کلیدی |
|---|---|---|
| **L1 corpus→RAG** | **PARTIAL** | دو مرحله‌ی **دستی**، بدون auto-sync: (a) bulk phase3: `radio-rag/chunk.py` + `import_radio_neo4j.py` (188 خط) → 76,543 chunks/4,002 docs (2026-10-22)؛ (b) stage5: `corpus/neo4j_linkage.py` (1,047 خط) — SET افزایشی 20 کلید روی گره‌های Chunk زنده (batch ≤900، idempotent، dry-run اجباری، snapshot+rollback)؛ apply تولید 2026-11-06: **79,350 chunks / 4,148 docs / 1,187,841 کلید، 0 تضاد، post-audit 7/7**. RAG `data/corpus/*.jsonl` را **نمی‌خواند** (ST-02 Q5). تازگی: max session در DB = **10,544** در برابر corpus **10,901** → **357 جلسه‌ی کهنه** |
| **L2 chunking** | EXISTS | `chunk.py`: پنجره‌های 300s نرم روی بلوک‌های متوالی SRT، `MAX_CHUNK_CHARS=800`، `MIN_CHUNK_CHARS=200` (merge)، هرگز بلوک SRT را نمی‌شکند (`parse_srt` 72-109)؛ `chunk_id = "<doc_id>::subtitle_window::N"` + یک summary chunk/اپیزود؛ `doc_id = <stem>__s<session_id>`؛ نمونه: `radio-varzesh-04-03-26-04-30__s1956::subtitle_window::0` (0:00:00–0:01:56) |
| **L3 embedding** | EXISTS | `embed()` (api.py:100-109) از طریق LiteLLM `/embeddings`؛ وکتور = property روی گره‌ی Chunk؛ `vector_index_chunk` ONLINE 100٪ VECTOR `node:Chunk [embedding]` vector-3.0؛ `radio-4b` هم online با همان 79,350؛ VARIANTS (api.py:56-61): `06b` پیش‌فرض (1024-dim)، `4b` (2560-dim)، `rrf` (k=60)؛ **پیش‌فرض frontend روی 4b** (`<option value="4b" selected>`) |
| **L4 metadata** | EXISTS (نامتقارن) | n=79,350: K1 record_id **100٪**، K3 session_uid 100٪، K4 program_id 100٪، K20 air_date_status 100٪؛ K7 program_page_url / K11 episode_url / K12 day_archive_url / K13 timeslot_archive_url **76.3٪** (60,575)؛ K15 corrected_srt_url **59.5٪** (47,254)؛ K18 summary_url **58.7٪** (46,544)؛ K14 raw_srt_url **22.2٪** (17,644)؛ K16 full_text_url **21.1٪** (16,721)؛ **K19 audio_url 0٪ (0)**؛ کلیدهای phase3 (program_name، air_persian، air_gregorian، air_time، start_hms، end_hms، citation، session_id، channel، chunk_type) 100٪؛ **K9 کلاً غایب** (در ROW_TO_PROP نیست)؛ **18,775 (23.7٪) chunk بدون program_page_url** (UI اسلات تاریخ را رانده می‌کند — app.js:63) |
| **L5 citations** | EXISTS | نمونه‌ی کامل گره: `radio-varzesh-04-03-26-04-30__s1956` (محوطة گفتگو، `program_uid=iranseda:prog:ch18:m081100`، air 1403-10-06/2024-12-26 03:00، citation `"<program>, air <FA> (<GR>), from H:MM:SS to H:MM:SS"` — chunk.py:124-136، 4 URL GitHub raw (download-db)، `audio_url=NULL`، `air_date_status=unverified`، `quarantined=FALSE`) |
| **L6 retrieval** | EXISTS (تک‌محور) | **فقط وکتور — بدون BM25/fulltext/hybrid/فلتر متادیتا**: `RETRIEVAL_CYPHER` (api.py:116-148) از `db.index.vector.queryNodes`، `TOP_K=5` (api.py:46)، `MIN_SCORE=0.25` (api.py:47)، ORDER BY score؛ `retrieve()` 159-176 → `dedup_sources` 368 (simulcast/re-ASR 327-366)؛ `retrieve_rrf` 179-213 (دو variant موازی + RRF k=60 روی chunk_id)؛ خروجی خالی → «این موضوع در آرشیو رادیو معارف یافت نشد.» (588-591) |
| **L7 links** | EXISTS (با شکاف) | `_links_for` (api.py:410-441): (1) `source_text` — نخستین معتبر از زنجیرۀ `full_text_url → corrected_text_url → raw_srt_url → corrected_srt_url` (422-427)؛ (2) `episode`؛ (3) `program_page`؛ (4) `day_archive`+`time_slot_archive` فقط اگر `air_date_status != "impossible"` (434-437)؛ (5) `quarantined==true` → **هیچ لینکی** (420). `_url_link` 400-409 فقط http(s). **یافته‌ی کلیدی: نوع لینک `summary` نیست** درحالی‌که `summary_url` روی 58.7٪ گره‌ها هست |
| **L8 metadata disclosure** | EXISTS | هر source: program_name، air_date FA+GR، air_gregorian، time، channel، session_id، chunk_id، chunk_type، citation، score، text[:400]، session_uid، air_date_status، quarantined، links[] (480-510)؛ `SYSTEM_PROMPT` 314-323 (فارسی، فقط از منابع، [n] inline، تاریخ ساختگی ممنوع، «نامشخص» برای گم)؛ نمونه‌ی `/api/programs`: گنج سعادت 390 docs، بر بال سخن 367، زمزم احکام 351 |
| **L9 audio** | **NOT FOUND** | `audio_url` 0/79,350؛ هیچ mp3/ogg/wav در هیچ‌جا؛ نزدیک‌ترین چیز = صفحۀ EPG (player embed) |
| **L10 UI** | EXISTS | `:8044` nginx؛ `app.js` → `POST /api/chat/stream` (SSE)؛ پیش‌فرض variant **4b**؛ `renderSources` 57-64 (اسلات تاریخ برحسب air_date_status: impossible→«تاریخ نامعتبر»، none/خالی→اسلات حذف، در غیر این‌حال air_date یا «نامشخص» — 61-64)؛ `renderLinks` 45-54 (`<a target="_blank">`، فیلتر `^https?://`)؛ quarantined → بدون لینک/بج (79-80)؛ برچسب 7 مرحله‌ای busy؛ AbortController؛ timeout 5 دقیقه؛ رویداد SSE `sources` **پیش** از تولید (620-626) |

### ۱۱.۳ تست زنده‌ی تکرارپذیر (Part 3)

- هدف: `radio-maaref-05-07-13-06-00__s10499` «بر كرانه نور» (موضوع: تعویّل قرآن در مقابل تفسیر؛ در DB تأیید شد).
- `POST http://127.0.0.1:8043/api/chat` با `{"message": "بر اساس آرشیو رادیو معارف، تعویّل قرآن به چه معناست و تفاوت آن با تفسیر علمی چیست؟", "variant": "06b"}`
- نتیجه: 2026-11-07T02:36:45Z→02:36:51Z، **HTTP 200، 5.91s، score=0.8108**، 4 source همه «بر كرانه نور»: s5293 (0.8108)، s5292×2 (0.796/0.7922)، **s10499 هدف (0.7940) ✓**

**جدول 7 هدف نقل‌مراجعه (نتیجه: 4 کامل، 2 جزئی، 1 گم):**

| # | هدف | وضعیت | لایه‌ی شکسته |
|---|---|---|---|
| 1 | نام برنامه | ✅ | — |
| 2 | تاریخ+زمان | ⚠️ REACHED BUT CONTRADICTORY | UI: `1405-05-07 (2026-07-29) 06:00` درحالی‌که corpus همان uid: `jalali=1405-07-11, gregorian=2026-10-03` (source=filename)؛ لینک‌های آرشیو `d=10/3/2026` و `d=10/5/2026` (تاریخ‌های EPG) → **تضاد ≈2.5 ماهه**؛ `air_date_status=unverified` — شکست: Corpus Builder (broadcast از filename نه EPG) + RAG Ingestion (filename date → `air_persian`)؛ **زمان (hms) درست است** ✅ |
| 3 | متن کامل | ✅ | — (3 از 4 source؛ ST-04 A2: 136/136=200) |
| 4 | SRT | ⚠️ جزئی | 1 از 4 source؛ پوشش raw 22.2٪/corrected 59.5٪ — شکست: 44/118 اِست P3-only → 404 |
| 5 | summary | ❌ | `summary_url` در DB 58.7٪ و session هدف دارد ولی `_links_for` (api.py:410-441) + `_LINK_LABELS` (385-399) **نوع لینک summary ندارند** — شکست: RAG `api.py` (ارزان‌ترین شکاف) |
| 6 | لینک GitHub | ✅ | همه `source_text` روی `raw.githubusercontent.com/…/download-db/…` |
| 7 | لینک‌های آرشیو IranSeda | ✅ | هر 4 source: episode + program_page + day_archive + time_slot_archive (همه `radio.iranseda.ir`) |

---

## ۱۲. وضعیت Hugging Face — BLOCKED

> منبع: `ST-06_rag_hf.md` (Part 4) — شواهد 9-گانه‌ی «یافت نشد/مسدود».

| # | شواهد | یافته |
|---|---|---|
| 1 | نام دیتاست در کد: `corpus/publisher.py:64` | `iranseda-radio-corpus`، version 1.0، license = `"rights-not-verified (publish PRIVATE only)"` |
| 2 | `ls …/data/corpus/hf/` روی سرور | **NOT FOUND** — bundle هرگز ساخته (یا پاک) نشده |
| 3 | `HF_TOKEN` در `.env.example` ریپوی `qa-knowledge-graph-pipeline` | placeholder **خالی (len=0)**؛ هیچ .env/محیط shell/`~/.bashrc` دیگر HF ندارد |
| 4 | `datasets` / `huggingface_hub` | **نصب نیستند** |
| 5 | HF public API: `GET /api/datasets?author=saber13812002` | `[]` (HTTP 200) — دیتاست عمومی وجود ندارد |
| 6 | `GET /api/datasets/…/iranseda-radio-corpus` | `401 Invalid username or password` |
| 7 | بررسی توکن | `NO_USABLE_TOKEN` |
| 8 | `grep -rli huggingface` در همه‌ی رِپوهای RAG | خالی؛ تنها مرجع `corpus/publisher.py` |
| 9 | سیاست | **PUBLIC publish = BLOCKED — RIGHTS NOT VERIFIED** (`publisher.py:113, 170-174`)؛ حتی با توکن، فقط **private** مجاز |

**وضعیت فعلی `publisher.py`:** فقط bundle محلی (`prepare()` 37-131 → README + `dataset_info.json` + `publish_status.json`)؛ هرگز upload اجرا نشده. چیدمان v1.0: record_id، episode_key، broadcast (jalali+gregorian)، audio.url، transcripts.originals، transcripts.llm_outputs[]، speakers (خالی + دلیل)، crop، pipeline_state، provenance، quality (publisher.py:76-87، 148-163). **انتشار افزایشی در v1.0 تعریف نشده** (یک‌باره‌ای؛ نیازمند طراحی فاز ۹ — P9-6).

**حکم:** HF = **BLOCKED** با دو درِ خارجی (حق‌المحتوا + توکن) — قابل تعویق به فاز ۱۰ (بخش ۱۶، P9-6).

---

## ۱۳. یکپارچگی Class B (قرنطینۀ 1,147)

> منبع: `ST-03_db_classb.md` + `STAGE_3_FULL_EXPORT_REPORT.md`. سیاست فعلی: **`PERMANENT_UNTIL_IDENTITY_PROVEN`** — قرنطینه دست‌نخورده، **هیچ auto-merge‌ای بدون تأیید PM نیست**.

### ۱۳.۱ اعداد دقیق

| شاخص | مقدار |
|---|---|
| ردیف‌های قرنطینه | **دقیقا 1,147** (همه schema 1.1)، reason = `identity collision (duplicate record_id)`، `quarantined_at=2026-11-05T00:53:14` |
| یکتایی | quarantine: 1,147 record_id/session_id/(rid,sid) منحصربه‌فرد؛ corpus: 9,747 یکتا، 0 تکراری؛ **هر record_id قرنطینه دقیقاً یک بار در corpus (برنده)**؛ تقاطع session_idهای قرنطینه با corpus = **0** |
| هویت | **9,747 + 1,147 = 10,894 = `source_db_row_count`** (sessions 10,897–10,907 بعد از watermark ساخته شدند = crawl زنده، نه شکاف) |
| پراکندگی | 1,147 روی **17 program_id بازنده** (42=پارسایان 194، 31=پرسمان اعتقادی 145، 40=مکارم خوبان 117، …) |
| `rag_linkage` | 10,894 سطر = 1,147 `quarantined=true` + 294 `doc_id_missing` |
| `invalid.jsonl` | **وجود ندارد** (FileNotFoundError) — همه‌ی 1,147 سابقاً-invalid = Class B (100٪ — STAGE_3) |

### ۱۳.۲ ریشه‌ی دقیق (با شواهد)

1. **27 URL با 2 ردیف** در `radio_programs`: ردیف‌های legacy (created 2025-05، `legacy_expires_at=2025-11-19`) + ردیف‌های بازسازی‌شده **2025-11-19 16:31** (دقیقاً لحظه‌ی انقضا) — مایگریشن برنامه‌ها را دوبل کرد و **به دلیل نبود UNIQUE روی `url`** هر دو ماندند. نمونه: `m=045101` → ids 3 و 31 هر دو «پرسمان اعتقادی»؛ `m=047506` → ids 10 و 38 هر دو «امیر مؤمنان».
2. فرمول `record_id_for` (`corpus/database.py:263-272`) = فقط `(ch,e)` → دو ردیف session با همان `(ch,e)` تحت دو برنامه → record_id یکسان → collision → quarantine.
3. **مثال اثبات‌شده گروه `e=153278467` (ch14):** sid=5038 pid=3 (legacy، created 2025-11-29) + sid=6217 pid=31 (جدید، created 2026-10-22) — link و filename یکسان → هر دو `iranseda:ch14:e153278467`؛ exporter **اولی (5038، سمت legacy)** را نگه می‌دارد و 6217 را قرنطینه می‌کند (`database_refs.program_ids_all=[3,31]`، هش `legacy_program_duplicate_merged`).
4. **مثال گروه `e=139510046`:** sid=240 pid=10 + sid=6948 pid=38 — filename یکسان `radio-maaref-97-01-10-22-30.mp4`، سرتای SRT یکسان (sha `b3ec1867…`)، یکی srt_filename NULL دارد.
5. آمار تصادف: **1,147 گروه (ch,e)، همه دقیقاً دوعضوی، همه بین-برنامه‌ای (n_prog=2)، 1,096 تک‌فایلی، 2,294 session**؛ `has_m=0` روی هر 10,903 ردیف sessions؛ دسته‌بندی: `same_episode_multiple_references`=1,096 + `different_programs_shared_archive_reference`=51؛ از 1,115 گروهی که هر دو عضو SRT دارند: **1,113 sha256 یکسان، 2 متفاوت**.

### ۱۳.۳ برنامه‌های درگیر

**35 برنامه، 2,294 session.** جفت‌های اصلی:

| برنامه | pid legacy | pid جدید | session‌ها |
|---|---|---|---|
| پارسایان | 15 | 42 | 194/194 |
| پرسمان اعتقادی | 3 | 31 | 141/145 |
| مکارم خوبان | 13 | 40 | 117/117 |
| پرسمان قرآنی | 7 | 35 | 79/79 |
| برای بیداری | 21 | 48 | 75/75 |
| پرسمان انقلاب | 5 | 33 | 73/73 |
| پرسمان تاریخی | 6 | 34 | 73/73 |
| محوطه گفتگو | 23 | 50 | 70/70 |
| + 15 جفت دیگر | | | (جدول کامل در ST-03) |

اختلاف 4 رکورد (141 در برابر 145) = 4 لینک فقط تحت pid جدید → تصادف **دوسویه**.

### ۱۳.۴ پنج گزینه‌ی حل (مستند شده — **هیچ تصمیمی گرفته نشده**)

| # | گزینه | فایده | ریسک/محدودیت |
|---|---|---|---|
| ① | **ادغام ریشه‌ای 27 جفت در DB** (remap `sessions.program_id` + re-export) | تنها گزینه‌ای که هویت record_id + تعلق صحیح برنامه را نجات می‌دهد — **توصیه‌ی تحلیلی ST-03/07** | UPDATE/DELETE پرتخ؛ نیاز به backup + پنجرۀ نگهداری + نقشه‌ی remap کامل + اثبات uq پس از remap |
| ② | تغییر فرمول record_id (ch+e+program_uid یا +session_id) | حل کد | همه‌ی doc_id/fingerprint/کوئری‌ها باطل می‌شوند؛ 51 گروه آرشیو مشترک را با `m` نمی‌توان جداسازی کرد |
| ③ | حفظ هر دو به‌عنوان رکورد جدا + `doc_id=session_id` در RAG | **صفر نوشتار DB**؛ recall ≈×1.06 | 1,113 SRT بایت-یکسان → نیاز به dedup در بازیابی |
| ④ | وضعیت موجود + بازبینی دستی 2 گروه SRT-متفاوت + 51 گروه آرشیو مشترک | کمینه‌کار | ~1,094 به‌عنوان «تکراری مضر» برنده می‌ماند |
| ⑤ | جابه‌جایی برنده از legacy به ردیف غیر-legacy (استفاده از `is_legacy` + program_uid) | تعلق برنامه صحیح بدون merge | 4 fingerprint کورپس تغییر می‌کند؛ 1,147 باقی می‌ماند |

ترکیب‌پذیری: ① مستقل از ②/③/⑤؛ ④ = «صبر + کمینه‌بازبینی». **مسیر پیشنهادی این گزارش:** ① به‌عنوان گیت‌شده (P9-3d) + fallback ③ (صفر-ریسک).

### ۱۳.۵ جدول شناسه‌های جایگزین

| شناسه | تمایز | هزینه |
|---|---|---|
| `session_id` (PK) | **کامل** (تمایز 100٪) | از دست دادن معنای «همان اپیزود» (simulcast/re-ASR) |
| `(program_id, link)` | یکتا در DB | وابسته به کیفیت pid (ریشه‌ی مشکل همین است) |
| `program_uid` (ch+m) | جزئی | 27 جفت تکراری |
| `(ch, e)` | **همان کلید تصادف** | — |
| timestamp پخش | در 1,096/1,147 یکسان | فام |
| sha256 SRT | در 1,113/1,115 یکسان | فام |

**تصمیم: DEFERRED به PM** (بخش ۱۸، درِ #3). قرنطینه 1,147 دست‌نخورده باقی می‌ماند.

---

## ۱۴. معماری پیشنهادی نهایی (بر پایه‌ی ST-07)

> منبع: `ST-07_architecture_roadmap.md` — طرح/راهبر **بدون** کد و تغییر. سه زیرسیستم (تولید SRT: مراحل 1–5؛ کورپس: 6–9؛ RAG: 10–13) فقط با **منبع‌های مشترک خواندنی** (MySQL، `downloads/`، Neo4j، دیسک) در تعامل‌اند.

### ۱۴.۱ زنجیرۀ ۱۳ مرحله‌ای

```
 [1 IranSeda Source]      [2 Production DB]            [3 Session/Program
 (iranseda.ir, headend1)  (MySQL radio, docker:3308)   Metadata (identity+dates)
          |                        |                          |
          v                        v                          |
 [4 ASR/SRT/TXT]      [5 LLM Correction]        <-----------+
 (whisper worker)     (llm_output/llm_job)
          |                        |
          v                        v
 [6 Unified Corpus Builder]  (سازندۀ تکی — قلب فاز ۹؛ single-writer)
          |
          v
 [7 Incremental Export]  -->  [8 Validation]  -->  [9 Manifest & Asset Linkage]
 (watermark merge)          (schema 1.1 gate)    (rag_linkage K1-K22 + asset C1..C14)
          |                                                     |
          v                                                     v
 [10 Hugging Face Dataset] (GATED: rights+token)   [11 RAG Ingestion (Neo4j)]
 (publisher.py, private)                            (neo4j_linkage, 79,350 chunks)
                                                                |
                                                                v
                                [12 Retrieval & Citation]  -->  [13 RAG UI]
                                (radio_api 8043, KNN+RRF)     (radio_frontend 8044)
```

### ۱۴.۲ هشت مرز جداسازی (کورپس هرگز نباید تولید SRT را آزار دهد)

| # | منبع مشترک | سمت تولید SRT | سمت کورپس/RAG | مکانیزم جداسازی |
|---|---|---|---|---|
| 1 | MySQL `radio` (127.0.0.1:3308) | نوشتار (pipeline 15/45) | **فقط خواندن** | guard در `corpus/database.py`: هر SQL غیر از SELECT/SHOW/DESCRIBE **رد**؛ کاربر `n8nuser` بدون حق نوشتار |
| 2 | `downloads/` (اِست‌های خام) | نوشتار SRT/TXT/mp3 | **فقط خواندن امضا** (sha256/size/existence) | کورپس فقط در `data/corpus/` می‌نویسد |
| 3 | Neo4j `neo4j_db` | chunk/embedding (ingestion جدا) | **فقط SET idempotent کلیدهای K روی گره‌های Chunk** | `neo4j_linkage.py` هرگز embedding/رابطه/گره‌ی غیر-Chunk نمی‌نویسد؛ dry-run پیش‌فرض + snapshot/rollback |
| 4 | دیسک (80٪، 291G) | `downloads/` + سیت | `data/corpus/` | staging ایزوله (`.staging.<run_id>`)؛ `PREVIOUS_RETENTION=3` (exporter.py 247) → سقف حجم ≈ 4×926MB؛ هش 85٪ در P9-8 |
| 5 | Git (ریپوی اصلی) | auto-refresh سرور (17 بار از Stage 4) | **worktree جدا** → پس از P9-1 به مسیر پایدار | درخت کاری مشترک نیست؛ push به شاخه‌ی مجزا |
| 6 | cron / قفل | `15,45 run_pipeline.sh` (flock) + `*/30 refresh_site.sh` | **cron جدا + pidfile جدا** | run سازنده در `30 */6` → 15 دقیقه فاصله از 15/45؛ pidfile سازنده (الگوی `_acquire_lock`، scheduler.py 35-54) |
| 7 | فرآیند/کانتینر | docker: mysql، whisper-worker/api، dashboard | فرآیند python مجزا | سازنده در whisper-worker/dashboard **نیست**؛ gate `export_enabled` جدا |
| 8 | dashboard (systemd، 8990) | سرویس زنده | فقط **خواندن** متریک‌ها + پنل گرافانا | سرویس دست‌نخورده؛ فقط پنل/فایل افزودنی (P9-8) |

**آزمون جداسازی (P9-5/P9-8):** در 7 run خودکار — صفر تغییر در `downloads/` (مجموعه‌ی mtime+sha)، صفر نوشتار DB (audit MySQL)، صفر تأخیر pipeline SRT.

### ۱۴.۳ طراحی single-writer: «یک run، یک staging، یک promote، یک قفل»

> بر پایه‌ی ST-05 Q7 (FEASIBLE) — **بازسازی، نه مکانیزم تازه**؛ همه‌ی قطعات در 1.1 وجود دارند.

```
 scripts/corpus_cron.sh  (cron: 30 */6 * * *  و  30 3 * * 0)
          |
 [0] acquire pidfile lock   (الگوی _acquire_lock از scheduler.py 35-54؛ stale-pid detection)
          |
 [1] watermark: sessions(updated_at+max_id)  +  llm(finished_at+max_id)   <-- P9-5
          |
 [2] staging dir واحد:  .staging.<run_id>   (run_id منحصربه‌فرد در هر run)
      corpus.jsonl (merge): _run_inner 494-823 (seen_ids 560-564,
        collision->quarantine 624-647, upsert 648-653, assembly 674-695, manifest 739-789)
      + quarantine + stats + incremental_state
          |
 [3] rag_linkage.main() 541-703 — اما _read_corpus_records 258-282
      حالا corpus.jsonl را از STAGING می‌خواند (نه زنده)   <-- race حذف می‌شود
      -> rag_linkage.jsonl + asset_manifest.jsonl
          |
 [4] _validate_staged 291-379 — حالا همه‌ی فایل‌ها را می‌بیند
      (_LIVE_RE 65-66 و _CHECKSUM_NAMES 70-71 گسترش: +2 فایل linkage)  <-- fail-closed gate
          |
 [5] promote تکی:  _archive_live 381-414 (PREVIOUS_RETENTION=3) -> os.replace _promote 416-420
      -> _write_checksums 422-433 -> _prune_previous 435-442
          |
 [6] (در همان قفل) sync Neo4j: neo4j_linkage.py — فایل‌های PROMOTEشده را می‌خواند
      (idempotent SET، dry-run+snapshot)                              <-- 357 -> 0
          |
 [7] release lock ;  log + metrics
  شکست در هر مرحله -> هیچ promote‌ای -> کورپس زنده‌ی قبلی سالم
```

**شش تغییر جراحی (همه additive، روی کد 1.1):**

| # | تغییر | مکان |
|---|---|---|
| 1 | `_LIVE_RE` + `_CHECKSUM_NAMES` += 2 فایل linkage | exporter.py:65-71 |
| 2 | `watermark_clause` += `llm.finished_at >= %s OR llm.id > %d` | database.py:211-238 (+ `high_watermark` 192-209) |
| 3 | `rag_linkage._read_corpus_records` مسیر staged را می‌پذیرد | rag_linkage.py:258-282 |
| 4 | دستور یکپارچۀ `corpus.cli run` + pidfile روی همه‌ی دستورات state-changing | cli.py (الگو: scheduler.py 35-54) |
| 5 | `run_id` منحصربه‌فرد در هر run (`--pin` فقط برای تست/مقایسه) | exporter.py |
| 6 | **بدون** تغییر schema، **بدون** نوشتار DB، **بدون** جدول جدید، **بدون** تغییر reconcile | — |

**خاصیت‌های تضمین‌شده:** Idempotent (no-op بایت-یکسان)؛ بازتکرار امن (upsert+fingerprint، هرگز replace)؛ Fail-closed (خطا → بدون promote)؛ حذف race (تنها خوانندۀ linkage = خروجی staged همان run)؛ دومین اتمیک هم‌سطح برای هر ۸ فایل (corpus، quarantine، stats، manifest، checksums، incremental_state، rag_linkage، asset_manifest).

### ۱۴.۴ زمان‌بندی اجرا (با توجیه داده‌ی واقعی)

| cron | وظیفه | توجیه |
|---|---|---|
| `30 */6 * * *` | run یکپارچۀ سازنده (incremental + linkage + validation + promote + Neo4j sync) | بسته‌ی بعدی اندازه‌گیری‌شده = **1,572 (≈14.4٪ از 10,906)** → backlog در ≤24h (4 run) پاک می‌شود؛ تولید پایا ~۱/روز + LLM خنثی → اکثر runها no-op ارزان (2 کوئری)؛ ساعت 30 = 15 دقیقه فاصله از 15/45 |
| `30 3 * * 0` (شنبه 03:30) | **full-export** (drift reset) + `reconcile()` | full ≠ incremental؛ خطوط دست‌نخورده کهنه می‌شوند → سقف کهنه‌شدگی = 7 روز؛ هم‌راستا با الگوی مستند `0 3 * * 0` در docstring `scheduler.py` |
| (دستی، اختیاری) | `corpus.cli publish` (bundle HF) | فقط وقتی درهای P9-6 باز شوند؛ بدون cron |

**بدون تغییر (حیاتی):** `*/30 * * * * refresh_site.sh` و `15,45 * * * * run_pipeline.sh`.
**پیش از فعال‌سازی:** 3 run سایه‌ای + آزمون جداسازی → سپس cron (P9-5).

**هشت مورد غیرقابل‌لمس:** (1) pipeline تولید SRT (`run_pipeline.sh` + 15/45 + زنجیرۀ `scan.go → discover_new.py → download_db.go`)؛ (2) whisper worker/api؛ (3) سرویس dashboard (8990)؛ (4) اسکیمای MySQL تا **گیت Class B**؛ (5) رکوردهای 9,747 موجود (additive-only)؛ (6) داده‌های chunk/embedding در Neo4j؛ (7) `refresh_site.sh` (*/30)؛ (8) هیچ عمل مخرب (بدون حذف فیزیکی، بدون overwrite خارج از staging، بدون نوشتار DB غیر-گیت).

---

## ۱۵. ریسک‌ها و بدهی فنی

> منبع: `ST-07_architecture_roadmap.md` §3.1 + `ST-05_incremental_compatibility.md`. شدت‌ها بر اساس «احتمال × اثر روی 9,747 رکورد و pipeline زنده‌ی SRT».

### ۱۵.۱ پنج ریسک برتر

| # | ریسک | شدت | شواهد | تخفیف (مخفف: mitigation) |
|---|---|---|---|---|
| R1 | **دگرنسخۀ مخرب (destructive regression):** اجرای کد 1.0 روی کورپس زنده‌ی 1.1 کل 9,747 خط را با subset ≈1,572 خط **replace** + دگرنسخۀ schema + ردشدن توسط validator 1.0 — بدون archive/rollback | **حیاتی** | ST-05 Q1؛ `mapper.py:474` ("1.0" hardcoded)؛ `validator.py:88` | guard نسخه در `corpus/schema.py` (P9-1)؛ آزمون byte-identical در CI؛ push فقط به `corpus-1.1` (نه main SRT)؛ rollback = full-rebuild (کورپس قابل بازسازی از DB) |
| R2 | **هویت حل‌نشده‌ی Class B:** 1,147 قرنطینه + 27 جفت URL تکراری؛ تصمیم غلط (auto-merge یا حذف) 9,747 رکورد زنده را آلوده می‌کند | **بالا** | ST-03/01؛ `uq_session_program_link`؛ بدون UNIQUE روی `radio_programs.url` | قرنطینه **FROZEN** تا تصویب PM (بدون auto-merge)؛ گزینه‌ی ①ِ ST-03 با گیت (backup + dry-run 27 جفت)؛ fallback = گزینه‌ی ③ (صفر نوشتار DB) |
| R3 | **نشت watermark LLM:** `llm.finished_at` در تشخیص افزایشی نیست؛ اگر LLM دوباره فعال شود، completions تازه **گم** می‌شوند (دورمانت از 2026-10-11) | **بالا** | ST-05؛ `watermark_clause` (database.py 211-238) فقط `sessions` را می‌بیند | P9-5: افزودن `llm.finished_at >= %s OR llm.id > %d` + آزمون واحد؛ full-export هفتگی نشت را به سقف 7 روز محدود می‌کند |
| R4 | **فشار دیسک + واگرایی ریپو:** دیسک 80٪ (291G آزاد)، 261 blob غیر-canonical، 33,469 فایل، 44 اِست P3-only | **متوسط** | ST-01/04؛ `PREVIOUS_RETENTION=3` (exporter.py 247) | `PREVIOUS_RETENTION=3` حجم کورپس را به ≈4×926MB محدود می‌کند؛ هش 85٪ (P9-8)؛ canonical blob + republish گروهی (P9-4) |
| R5 | **شکاف اعتماد RAG:** 357 جلسه‌ی کهنه، audio 0٪، mismatch variant (UI 4b / API 06b)، نقل‌مراجعه 4/7، تضاد تاریخ ≈2.5 ماهه | **بالا** | ST-06 | sync زنجیره‌شده (P9-5/P9-7: 357→0)؛ K-coverage در CI (P9-8)؛ یکپارچه‌سازی variant روی 06b؛ audio صادقانه (null+reason)؛ تاریخ فقط با `air_date_status` |

### ۱۵.۲ بدهی فنی ثبت‌شده (تفکیک از ریسک‌ها)

| # | بدهی | شدت | جایی که حل می‌شود |
|---|---|---|---|
| T1 | برون‌آیی دستی از worktree موقت `/tmp/saber_stage4_wt` (پنجرۀ 02:24–03:15 UTC 2026-11-06)، `export_enabled=false`، بدون cron | بالا | P9-1 (runbook) + P9-5 (cron) |
| T2 | هیچ cron برای corpus/RAG؛ هیچ pidfile بین runهای دستی | بالا | P9-5 |
| T3 | `reconcile_report.json` کهنه (2026-11-04) — reconcile با run فعلی هم‌مراتب نیست | متوسط | P9-5 (reconcile هفتگی زنجیره‌شده) |
| T4 | ≈114 فایل untracked روی سرور (اسکریپت‌های probe/stage، `asr_test_report.md`) — آلودگی درخت کاری | پایین | P9-1 (runbook: درخت تمیز) |
| T5 | واگرایی Git: orphan `remotes/53/phase3` و `origin/phase3` کهنه در local؛ 44 اِست فقط-P3؛ 261 blob غیر-canonical | متوسط | P9-4 (republish + canonical) |
| T6 | LLM pipeline دورمانت از 2026-10-11 (watermark llm ثابت) — تشخیص افزایشی آن را نمی‌بیند | بالا (خوابیده) | P9-5 (R3) |
| T7 | فیلد `presenter` در هیچ جدولی منبع ندارد — شکاف محصولی | پایین | **قابل تعویق** (تصمیم محصول) |
| T8 | 1,547 رکورد بدون تاریخ معتبر (none/impossible 2118–2120) — بدون EPG حل‌ناپذیر | متوسط | برچسب صادقانه در P9-3(b)؛ حل کامل **قابل تعویق** |
| T9 | 326 رکورد بدون `doc_id`؛ K9 در هیچ رکوردی موجود نیست؛ `raw_txt` کلید K ندارد | متوسط | P9-2 (قرارداد) + P9-7 (CI K-coverage) |
| T10 | headend audio timeout (`dial tcp 185.109.247.100:443`) → mp3 در هیچ جایی موجود نیست | بالاتر از کنترل | بخش ۱۸ (دربۀ عملیاتی) |
| T11 | دامنه‌ی `radio.ai.ismc.ir` BLOCKED (فقط IP `172.20.1.53:8044` کار می‌کند) | پایین | **قابل تعویق** (ops/شبکه روی سرور 52) |

---

## ۱۶. نقشۀ اجرایی پیشنهادی فاز ۹ (P9-1 … P9-8)

> منبع: `ST-07_architecture_roadmap.md` §2.1–§2.3. هر قدم با حداقل: هدف / وابستگی‌ها / فایل‌های کلیدی / معیار پذیرش / rollback.

### ۱۶.۰ گراف وابستگی و مسیر انتقایی

```
 P9-1 --> P9-2 --> { P9-3  |  P9-4  |  P9-5 } --> P9-7 --> P9-8 (بخش RAG)
                    \_______________________________________/
 P9-6 (HF) ---- موازی هر زمان که درهای خارجی (حقوق + توکن) باز شدند  [قابل تعویق به فاز ۱۰]
 P9-8 (بخش builder) ---- بلافاصله بعد از P9-5
```

- **مسیر انتقایی:** `P9-1 → P9-2 → P9-5 → P9-7 → P9-8(بخش RAG)`
- **تداخل فایل:** P9-3 و P9-4 هر دو `corpus/mapper.py` را لمس می‌کنند → ترتیب merge: **P9-3 (فیلدها) سپس P9-4 (linkage)** یا rebase با review مشترک.

### ۱۶.۱ P9-1 — ترفیع سازندۀ 1.1 به شاخۀ پایدار + نگهبان نسخه

| بُعد | محتوا |
|---|---|
| هدف | 4 commit سازندۀ 1.1 (`d93754c27`, `3b9b2c7a1`, `79cebd46d`, `277ffa799`) را به شاخۀ پایدار **`corpus-1.1`** ترقی دادن؛ guard در `corpus/schema.py` که `schema_version=1.1` را assert و **هر run 1.0 روی کورپس 1.1 را رد** کند (خنثی‌سازی R1)؛ runbook در `docs/CORPUS_BUILDER_RUNBOOK.md`؛ حذف وابستگی به `/tmp` |
| وابستگی‌ها | هیچ — نقطۀ آغاز |
| فایل‌های کلیدی | `corpus/schema.py`، `corpus/mapper.py:474` (ساختۀ guard)، `docs/CORPUS_BUILDER_RUNBOOK.md` |
| آزمون‌ها | byte-identical بودن نمای 1.0 (به‌جز `audio.local_exists`)؛ یکتایی 9747/9747؛ آزمون guard-fail (run 1.0 رد شود)؛ no-op با `--pin` |
| معیار پذیرش | سازنده از شاخۀ پایدار بدون حضور دست اجرا شود؛ runbook merge شده؛ guard فعال و آزمون‌شده |
| rollback | revert + fallback به worktree (guard کورپس زنده را دست نمی‌زند) |
| push | فقط `corpus-1.1` — **نه** main SRT (جلوگیری از تداخل با auto-refresh سیت 17 بار/دوره) |

### ۱۶.۲ P9-2 — قرارداد رسمی schema 1.1

| بُعد | محتوا |
|---|---|
| هدف | `schemas/iranseda-corpus-v1.1.schema.json` + `docs/CORPUS_SCHEMA_CONTRACT.md` (جدول K1–K22 با پوشش اندازه‌گیری‌شده از ST-06، مالکیت، قانون additive-only) + گسترش validator به sidecarها + به‌روزرسانی `REQUIRED_TOP_COVERAGE` (schema.py 53-60) |
| وابستگی‌ها | P9-1 |
| معیار پذیرش | 9,747 رکورد + 10,894 سطر linkage **100٪** پاس؛ K-coverage در CI زنده |
| rollback | revert (additive است؛ هیچ داده‌ای دست نمی‌خورد) |

### ۱۶.۳ P9-3 — تکمیل متادیتا (+ گیت Class B)

| بُعد | محتوا |
|---|---|
| هدف | (a) `episode_title` additive با `source=llm:summary`؛ (b) date sweep: filename JJ-MM-DD-HH-MM در برابر EPG → برچسب verified/unverified، ذخیرۀ هر دو، **هرگز fabrication**؛ (c) فیلد `presenter` + `missing_reason` (تخمین ممنوع) — **محل (c) قابل تعویق**؛ (d) **Class B گیت‌شده**: گزینه‌ی ① ST-03 (merge ریشۀ 27 جفت legacy) با ۵ شرط: (i) تصویب PM (ii) migration تاریخ‌دار `migrations/2026-11-xx_program_legacy_dedup.sql` (iii) backup کامل `radio_programs` (iv) dry-run با گزارش 27 جفت (v) 1,147 رکورد توسط **خود سازنده** re-trial (collision→quarantine 624-647) — **بدون auto-merge**؛ fallback = گزینه‌ی ③ (صفر نوشتار DB) |
| وابستگی‌ها | P9-2 (موازی با P9-4/P9-5) |
| commitها | ۲ (sweep متادیتا؛ migration گیت‌شده با تگ `GATED`) |
| معیار پذیرش | برچسب `air_date_status` روی 100٪ رکوردها؛ در صورت باز شدن گیت: 1,147→0 با صفر دست‌کاری دستی |
| rollback | revert sweep (additive)؛ rollback migration از backup + re-quarantine |

### ۱۶.۴ P9-4 — تعمیر پیوند URLها

| بُعد | محتوا |
|---|---|
| هدف | (1) republish `download-db` از `phase3` → 0 P3-only (44) + 0 stale (4)؛ (2) 261 blob → canonical = sha256 روی دیسک زنده؛ (3) عادی‌سازی episode 14/30 → هدف ≥28/30 (یا مستندسازی)؛ (4) **audio صادقانه:** `audio.url`=صفحه‌ی epgarchivePart، `local_exists=false`، `reason=headend_unavailable`، صفر URL mp3 جعلی؛ (5) طبقه‌بندی 1,547 رکورد (none/impossible 2118–2120)؛ (6) حفظ قانون: رکوردهای کورپس URL GitHub ندارند (فقط sidecar)؛ `d` = میلادی M/D/YYYY |
| وابستگی‌ها | P9-2 (موازی با P9-3/P9-5) |
| commitها | ۳ |
| push | `download-db` + `phase3` — در بیرون از پنجرۀ 15/45 |
| معیار پذیرش | A6 سبز: 0 P3-only + 0 stale + 0 غیر-canonical + 0 mp3 جعلی |
| rollback | revert republish (branch‌های جدا، بدون اثر روی DB) |

### ۱۶.۵ P9-5 — سازندۀ single-writer (قلب فاز ۹)

| بُعد | محتوا |
|---|---|
| هدف | اجرای دقیق §۱۴.۳: ۶ تغییر جراحی (1) `_LIVE_RE`+`_CHECKSUM_NAMES` += 2 فایل linkage (exporter.py:65-71) (2) `llm.finished_at` در `watermark_clause` (database.py:211-238) (3) `_read_corpus_records` مسیر staged (rag_linkage.py:258-282) (4) pidfile روی همه‌ی دستورات state-changing (5) دستور یکپارچۀ `corpus.cli run` + sync Neo4j (6) بدون تغییر schema/نوشتار DB/جدول جدید + `scripts/corpus_cron.sh` + `export_enabled=true` + cronها |
| وابستگی‌ها | P9-1, P9-2 |
| آزمون‌ها (a–g) | no-op بایت-یکسان؛ upsert +7/+1؛ collision حفظ 1,147؛ fail-closed؛ rollback از اسلات previous؛ contention؛ جداسازی (صفر تغییر `downloads/`، صفر نوشتار DB) |
| معیار پذیرش | **7 run خودکار پیاپی با صفر خطای قفل + صفر خطای checksum**؛ backlog 1,572→0 در ≤24h؛ checksum+previous+rollback برای linkage؛ آزمون جداسازی سبز |
| rollback | غیرفعال‌کردن cron (یک خط) + revert؛ کورپس قابل بازسازی → ریسک داده صفر |
| commitها | ۲ |

### ۱۶.۶ P9-6 — انتشار Hugging Face (GATED) — **قابل تعویق به فاز ۱۰**

| بُعد | محتوا |
|---|---|
| هدف | پس از باز شدن درهای خارجی: (1) تأیید حقوق توسط PM/حقوقی (2) توکن HF واقعی scope-دار در env (نه repo) → نصب `datasets`+`huggingface_hub` در env ایزوله؛ گسترش `publisher.py` (37-131) از local bundle به upload **private** با fallback؛ layout: `corpus.jsonl.gz` + `rag_linkage` + `asset_manifest` + README provenance + LICENSE placeholder (حقوق تأییدنشده → فقط private) |
| وابستگی‌ها | P9-4 + P9-5 + **2 دربۀ خارجی** |
| آزمون‌ها | اعتبارسنجی bundle؛ round-trip private با checksum؛ آزمون حریم (جستجوی author می‌ماند `[]`) |
| اجرا | دستی، on-demand — **بدون cron** |
| rollback | متوقف‌کردن/حذف دیتاست private (داده‌ی محلی دست نمی‌خورد) |

### ۱۶.۷ P9-7 — RAG end-to-end (زنجیره‌شدگی + خطای اعتماد)

| بُعد | محتوا |
|---|---|
| هدف | (1) زنجیره‌کردن `neo4j_linkage.py` (1,047 سطر) به انتهای run سازنده (همان قفل، پس از promote)؛ (2) **نوع لینک summary** در `_links_for` (api.py:410-441) + `_LINK_LABELS` (385-399) — داده از قبل در Neo4j است (58.7٪)، فقط type ندارد (ارزان‌ترین شکاف)؛ (3) متادیتای صادقانۀ audio (null+reason) تا زنده‌شدن headend؛ (4) یکپارچگی تاریخ: یک فیلد + `air_date_status`، هرگز `created_at`؛ (5) یکپارچه‌سازی variant: پیش‌فرض UI → **06b** (هم‌سان API)، 4b فقط صریح؛ (6) 357 stale→0 در اولین run زنجیره‌شده |
| وابستگی‌ها | P9-5 |
| commitها | ۲ در ۲ ریپو (radio-rag-service: api.py+UI؛ iranseda: sync زنجیره‌شده) |
| deploy | restart `radio_api` + `radio_frontend`؛ اولین sync خارج اوج |
| معیار پذیرش | A4+A5+A7 سبز (357→0؛ ≥6/7 نقل‌مراجعه؛ صفر تاریخ جعلی) |
| rollback | revert + snapshot Neo4j (بدون re-embed) |

### ۱۶.۸ P9-8 — پایش و گزارش‌دهی

| بُعد | محتوا |
|---|---|
| هدف | (1) پنل‌های گرافانا در `dashboard/grafana/` (additive): watermark lag، backlog، quarantine (ثابت 1,147 تا گیت Class B)، **دیسک 80٪ → هش 85٪**، جدول K-coverage، latency/200-rate API؛ (2) اسکریپت K-coverage در CI (جدول خودکار K1–K22، fail در regress مثل corrected_srt < 59.5٪، fail در URL mp3 جعلی)؛ (3) stale-detector (`max(session)` DB در برابر corpus + lag >24h → هش)؛ (4) گزارش هفتگی خودکار (الگوی `dashboard/reporter.py`) |
| وابستگی‌ها | P9-5 (بخش builder)؛ بخش RAG بعد از P9-7 |
| معیار پذیرش | متریک‌ها زنده؛ ≥1 گزارش هفتگی خودکار؛ صفر هش کاذب بعد از یک هفته پایداری |
| rollback | حذف پنل/اسکریپت (additive است) |

### ۱۶.۹ شش مورد صریحاً قابل تعویق (مستند برای PM)

| # | مورد | چرا قابل تعویق |
|---|---|---|
| 1 | کل P9-6 (HF) | درهای خارجی (حقوق + توکن) باز نیستند |
| 2 | migration Class B در P9-3(d) | تا تصویب PM؛ fallback ③ ریسک را می‌بندد |
| 3 | فیلد `presenter` | هیچ منبعی در هیچ جدولی — تصمیم محصول |
| 4 | حل کامل 1,547 رکورد بدون‌تاریخ | تاریخی/بدون EPG — فقط برچسب صادقانه ممکن است |
| 5 | استراتژی dual-model (4b) / یکپارچگی کامل مدل | 4b به‌عنوان گزینه‌ی صریح می‌ماند |
| 6 | بازکردن دامنه‌ی `radio.ai.ismc.ir` | ops/شبکه روی سرور 52 (root/BT-panel) — خارج از دایرۀ کد |

---

## ۱۷. معیارهای پذیرش کل فاز (A1–A10)

> منبع: `ST-07_architecture_roadmap.md` §3.3 — هر معیار با **مقدار شروع اندازه‌گیری‌شده** در لحظه‌ی بازرسی.

| ID | معیار | مقدار شروع (اندازه‌گیری‌شده) | هدف | مرجع |
|---|---|---|---|---|
| A1 | هویت: record_id یکتا 100٪؛ 1,147 قرنطینه تا تصویب PM | 9,747/9,747 یکتا + 1,147 قرنطینه | 100٪ یکتا؛ قرنطینه یا 0 (پس گیت) یا FROZEN مستند | ST-02/01 |
| A2 | اتمیک کامل: sidecarها checksum + 3 اسلات + rollback هم‌سطح corpus.jsonl | خارج از دوران اتمیک + race (ST-05) | 8 فایل، 1 promote، fail-closed | ST-05 |
| A3 | تازگی کورپس: backlog 1,572→0 در ≤24h از فعال‌شدن cron؛ lag watermark ≤24h | 1,572 (≈14.4٪ از 10,906) | 0 | ST-05 |
| A4 | تازگی RAG: 357 stale→0 (حداکثر session در DB ≥ corpus) | 10,544 در برابر 10,901 (357 عقب) | 0 | ST-06 |
| A5 | نقل‌مراجعه: تست زنده ≥6/7 (هدف 7/7)؛ لینک summary روی همه‌ی chunkهایی که `summary_url` دارند | 4/7؛ 58.7٪ chunkها summary دارند | 7/7 + 100٪ | ST-06 |
| A6 | صداقت linkage: صفر URL audio جعلی (null+reason)؛ `download-db`: 0 P3-only + 0 stale + 0 غیر-canonical | 0/126 mp3؛ 44+4+261 | 0/0/0/0 | ST-04 |
| A7 | صداقت تاریخ: صفر fabrication؛ 100٪ رکورد `air_date_status` معتبر (فقط verified از تطبیق EPG)؛ تاریخ UI همیشه با status | unverified 9,347 / none 1,442 / impossible 105 + تضاد 2.5 ماهه | 100٪ برچسب‌دار؛ صفر جعلی | ST-02/06 |
| A8 | اتوماسیون: 7 run cron پیاپی بدون خطای قفل/checksum | فقط دستی (ST-02) | 7/7 خودکار | ST-02 |
| A9 | شفافیت: گرافانا (watermark/backlog/quarantine/disk/K-coverage) + ≥1 گزارش هفتگی خودکار | هیچ | زنده | ST-01 |
| A10 | هدف محصول: گزارش link-coverage ثابت‌کنندۀ اینکه هر session → program → episode/day/timeslot/program_page → raw/corrected/summary (+audio صادقانه) با sha256/URL پایدار ردیابی‌پذیر است | جدول K-coverage (ST-06) | 100٪ ردیابی‌پذیر | ST-06 |

**تعریف «انجام» (Definition of Done):** سبزبودن A1–A10 + درهای باز (حقوق HF، migration Class B) به‌صورت رسمی مستند و تحویل فاز ۱۰ شوند — نه بی‌سروصدا رها.

---

## ۱۸. وابستگی‌های مسدود (Blocked Dependencies)

| # | مسدودکننده | شهادت (از بازرسی زنده) | عمل رفع مسدودی | کی | اثر در صورت حل‌نشدن |
|---|---|---|---|---|---|
| B1 | **حقوق محتوا + توکن HF** | `HF_TOKEN` خالی در env سرور؛ کتابخانه‌ها نصب نیستند؛ سیاست «RTS NOT VERIFIED» در ST-06؛ هیچ دیتاستی در HF وجود ندارد | (1) PM/حقوقی تأیید کند که انتشار (private) مجاز است (2) توکن HF واقعی scope-دار در env سرور (نه در repo) | PM + ops | P9-6 کامل به فاز ۱۰ منتقل می‌شود؛ بقیۀ فاز ۹ بلاک نمی‌شود |
| B2 | **crontab ریشه** | `sudo: a password is required` — crontab ریشه قابل بازرسی نبود؛ `/etc/cron.d` فقط e2scrub/.placeholder/sysstat | دسترسی sudo موقت یا بررسی دستی `crontab -l -u root` توسط admin | ops | عدم‌اطمینان: ممکن است cron پنهان دیگری cronهای ما را تداخل بدهد؛ ریسک متوسط |
| B3 | **تصمیم Class B** | 1,147 قرنطینه + 27 جفت URL تکراری؛ بدون UNIQUE روی `radio_programs.url` (ST-03 §5) | PM یکی از ۵ گزینه‌ی §۱۳ را تصویب/رد کند (پیشنهاد: گزینه‌ی ① گیت‌شده؛ fallback ③) | **PM** | بدون تصویب: 1,147 FROZEN می‌ماند (صحیح اما ناقص)؛ گزینه‌ی ③ ریسک را می‌بندد |
| B4 | **دسترس‌پذیری audio (headend)** | `dial tcp 185.109.247.100:443: i/o timeout` — mp3 0/126 در هیچ درخت (ST-04) | ops: زنده‌کردن/جایگزینی سرور headend (خارج از ریپو) | ops/تحویل‌دهندۀ upstream | audio برای همیشه null+reason می‌ماند (صادقانه)؛ هدف A5 audio بلاک |
| B5 | **منبع اعتبارسنجی تاریخ** | تضاد ≈2.5 ماهه بین filename JJ-MM-DD و EPG (ST-06)؛ 9,347 رکورد unverified | سیاست «EPG مرجع» تصویب شود + نمونه‌ی EPG برای sweep (P9-3b) | PM (سیاست) | تا تصویب: همه تاریخ‌ها unverified برچسب می‌گیرند (صادقانه) — fabrication صفر |
| (مرتبط) | دامنه‌ی `radio.ai.ismc.ir` BLOCKED | فقط `http://172.20.1.53:8044` پاسخ می‌دهد (ST-06) | DNS/آب‌برگ روی سرور 52 (root/BT-panel) | ops | کاربر نهایی فقط با IP می‌بیند؛ بلاک فنی نیست |

---

## ۱۹. اقدامات دقیق بعدی (سه گام نخست، به ترتیب)

> هر سه گام **فقط روی ریپوی کد** است و به هیچ‌کدام از درهای B1–B5 وابسته نیست.

### گام ۱ — P9-1: خنثی‌سازی ریسک حیاتی (R1)

1. ساخت شاخۀ `corpus-1.1` از worktree فعلی سازنده؛ ترقی 4 commit: `d93754c27`, `3b9b2c7a1`, `79cebd46d`, `277ffa799`.
2. افزودن guard نسخه به `corpus/schema.py`: assert `schema_version == "1.1"`؛ هر run که `1.0` را اعلام کند **قبل از اولین نوشتار** stop شود.
3. نگارش `docs/CORPUS_BUILDER_RUNBOOK.md` (چطور بدون `/tmp` و بدون دست run شود).
4. آزمون‌ها: (a) نمای 1.0 بایت-یکسان با کورپس زنده (به‌جز `audio.local_exists`)؛ (b) یکتایی record_id 9747/9747؛ (c) guard-fail: run 1.0 رد شود؛ (d) `--pin` = no-op.
5. push فقط به `corpus-1.1`. **چرا نخست:** تا قبل از این guard، هر run تصادفی 1.0 می‌تواند 9,747 رکورد را با ≈1,572 replace کند (R1).

### گام ۲ — P9-2: قرارداد schema (بنای B برای P9-3/4/5)

1. نگارش `schemas/iranseda-corpus-v1.1.schema.json` + `docs/CORPUS_SCHEMA_CONTRACT.md` با جدول K1–K22 (پوشش اندازه‌گیری‌شده از ST-06، مالک، قانون additive-only).
2. گسترش validator به `rag_linkage.jsonl`/`asset_manifest.jsonl` + به‌روزرسانی `REQUIRED_TOP_COVERAGE` (schema.py 53-60).
3. معیار پذیرش: 9,747 + 10,894 سطر = **100٪ پاس**.

### گام ۳ — P9-5: شروع سازندۀ single-writer (قلب فاز ۹)

1. اجرای ۶ تغییر جراحی §۱۴.۳ روی کد 1.1: `exporter.py:65-71` (+2 linkage در `_LIVE_RE`/`_CHECKSUM_NAMES`)، `database.py:211-238` (clause llm)، `rag_linkage.py:258-282` (مسیر staged)، `cli.py` (دستور `run` یکپارچه + pidfile)، `run_id` منحصربه‌فرد، بدون تغییر schema/DB.
2. نگارش `scripts/corpus_cron.sh` + 3 run **سایه‌ای** (بدون cron) + آزمون جداسازی (صفر تغییر `downloads/`، صفر نوشتار DB، صفر تأخیر pipeline).
3. فعال‌سازی: `export_enabled=true` + cron `30 */6 * * *` و `30 3 * * 0` — در ساعت‌های فاصله از 15/45.
4. معیار پذیرش: **7 run خودکار پیاپی، صفر خطای قفل/checksum؛ backlog 1,572→0 در ≤24h**.

**موازی با گام‌ها (بدون کد):** درخواست رسمی تصمیم Class B از PM (بخش ۱۳) — رفع B3 بلافاصله P9-3(d) را آزاد می‌کند؛ تا آن زمان گزینه‌ی ③ (صفر نوشتار DB) ریسک را می‌بندد.

---

## ۲۰. سرنخ‌های Git: commit و push

> پیش‌از-عمل: شاخه‌ی `download-db` در `25935eab826bc4adc922f51e92703a2166eac1ae` (هم‌سان `origin/download-db`)؛ staging خالی؛ ~65 فایل untracked موجود **حفظ و** خارج از این commitها.

| سرنخ | مقدار |
|---|---|
| commit پیشین روی `download-db` | `25935eab826bc4adc922f51e92703a2166eac1ae` |
| commit 1 (این گزارش) | `5fc7555252cca1ce1817bbac1973d4e1fbc797c7` |
| پیام commit 1 | `docs(corpus): Phase 9 discovery & architecture audit report` |
| خروجی `git push origin download-db` | `25935eab8..5fc755525  download-db -> download-db` (fast-forward، exit 0) |
| `git ls-remote origin download-db` (بعد از commit 1) | `5fc7555252cca1ce1817bbac1973d4e1fbc797c7  refs/heads/download-db` — **برابر با commit 1 ✓** |
| commit 2 (ثبت سرنخ‌های push در این بخش — الگوی STAGE_4 §14 / STAGE_1 §13) | همان commitی که این سطرها را ثبت می‌کند؛ SHA آن = HEAD نهایی remote (در payload تکمیل مأموریت و `git log -1` ثبت شده) |
| پیام commit 2 | `docs(corpus): phase 9 report — record verified push evidence in section 20` |
| `git ls-remote origin download-db` (نهایی) | برابر SHA commit 2 (fast-forward دوم؛ در payload تکمیل مأموریت ثبت شده) |
| لینک مستقیم GitHub | `https://github.com/saber13812002/iranseda-crawler-golang-/blob/download-db/reports/corpus/PHASE_9_DISCOVERY_AND_ARCHITECTURE_AUDIT.md` |
| اثبات «فقط گزارش committed شده» (commit 1) | `git show --stat 5fc755525...` → `1 file changed, 1026 insertions(+)` — فقط `reports/corpus/PHASE_9_DISCOVERY_AND_ARCHITECTURE_AUDIT.md` ✓ |
| اثبات (commit 2) | `git show --stat` commit 2 → فقط همان یک مسیر (در payload تکمیل مأموریت ثبت شده) |

> **تأیید نهایی:** SHA روی remote باید با SHA محلی commit 2 برابر باشد (fast-forward، بدون force).
