# v2 labeled obvious-ASR-error set (STEP 9B.2.1)

Ground-truth set of **obvious** ASR errors used to measure **recall** of the
conservative corrector (STEP 9B.2). Built **without any LLM** — each label was
picked by hand from the original (uncorrected) SRT of the same 20 files and is
verifiable from the surrounding context / standard religious-and-geographical
vocabulary.

**Format** per label: `stem` (file), `block` (1-based SRT block index as it
appears in the file), `original` (the wrong ASR token/phrase, verbatim from the
original SRT), `expected` (the correct form), and why it is obvious.

**Stems** are the 20 QA files (full filename `radio-maaref-<stem>.srt`):
04-08-05-02-00, 04-08-06-02-00, 04-08-12-02-00, 04-08-13-02-00, 04-08-19-02-00,
04-08-20-02-00, 04-08-26-02-00, 04-08-26-22-00, 04-08-27-02-00, 04-08-27-22-00,
04-09-03-02-00, 04-09-03-22-00, 05-07-17-23-30, 05-07-18-01-30, 05-07-18-03-00,
05-07-18-03-30, 05-07-18-06-00, 05-07-18-07-30, 05-07-18-09-00, 05-07-18-13-30.

**Recall scoring rule** (applied in STEP 9B.2.4): a labeled error counts as
**fixed** by the new v2 when, in the v2 output block at that (stem, block), the
`original` substring is **no longer present** AND the `expected` substring
**is present**. (Substring-level, so a block where the model fixed this word but
left the rest untouched still counts as fixed.)

---

| # | stem | block | original | expected | why obvious |
|---|---|---|---|---|---|
| 1 | 04-08-05-02-00 | 22 | انوان | عنوان | «انوان» is not a word; «عنوان» (title) fits «عنوان سخن ما روایات کافی» |
| 2 | 04-08-05-02-00 | 23 | انوان | عنوان | same homophone: «عنوان این باب است، باب‌الانصافه» |
| 3 | 04-08-26-02-00 | 44 | انوان | عنوان | title of the talk |
| 4 | 04-09-03-02-00 | 35 | انوان | عنوان | «عنوان سخن ماروایات کافی» |
| 5 | 04-08-05-02-00 | 2 | اردوگا | اردوگاه | «اردوگا» is not a word; اردوگاه = military camp (context: POW camp) |
| 6 | 04-08-12-02-00 | 13 | اردوگا | اردوگاه | «در اردوگای اسر» → اردوگاه |
| 7 | 04-08-27-02-00 | 17 | اردوگا | اردوگاه | «در اردوگا بود» → اردوگاه |
| 8 | 04-08-26-22-00 | 63 | اردوگا | اردوگاه | «رسیدیم، اردوگای موسل یک» → اردوگاه |
| 9 | 04-08-13-02-00 | 14 | عصارت | اسارت | «عصارت» is a misspelling of اسارت (captivity); context is POWs |
| 10 | 04-08-13-02-00 | 52 | عصارت | اسارت | «زمستان عصارت» → اسارت |
| 11 | 04-08-27-22-00 | 95 | عصارت | اسارت | «زند در زندان یعنی عصارت» → اسارت |
| 12 | 04-08-13-02-00 | 50 | عصارت | اسارت | «در اردوگاه عصارت، نماز زبان ایمان بود» |
| 13 | 04-08-19-02-00 | 16 | عصرا | اسرا | «عصرا» (evening) is wrong here; the prisoners = اسرا |
| 14 | 04-08-20-02-00 | 2 | عصرای | اسرای | prisoners of Op. Khybar = اسرای |
| 15 | 04-08-20-02-00 | 25 | عصرا | اسرا | «قرآن برای عصرا کارکردی فوق‌العاده» |
| 16 | 04-08-20-02-00 | 27 | عصر را | اسرا را | «هوییت انسانی و ایمانی عصر را را» |
| 17 | 04-08-26-22-00 | 25 | عصرا | اسرا | «برای عصرا وضع شده» |
| 18 | 04-09-03-02-00 | 24 | حصارت | اسارت | حصارت→اسارت |
| 19 | 04-08-27-22-00 | 79 | احصارت | اسارت | احصارت→اسارت |
| 20 | 04-08-27-22-00 | 44 | عصارت | اسارت | «به عصارت نیروی بعث عراق درآمدند» |
| 21 | 04-08-27-22-00 | 46 | موزوران | بعثیان | Ba'ath forces = بعثیان (context: brainwashing POWs) |
| 22 | 04-08-27-02-00 | 23 | عرق | عراق | Tikrit is in Iraq → عراق |
| 23 | 04-08-27-02-00 | 3 | عرق | عراق | «آسمان عرق را ندیده بودیم» |
| 24 | 04-08-27-02-00 | 5 | عرقی | عراقی | «افسر عرقی از نگهبان عرقی پرسید» |
| 25 | 04-08-26-22-00 | 49 | عرق | عراق | «افراد دریجه بالای عرق آمدند» |
| 26 | 04-08-27-22-00 | 133 | عرق | عراق | «گرمای تابستان عرق در تکریت» |
| 27 | 04-08-06-02-00 | 64 | قوم | قم | «بنیان‌گذار حبزه‌ی علمی قوم» → science hub of Qom |
| 28 | 04-08-26-22-00 | 14 | قزه | قزوین | «دولت در قزه گفت... در قزه» → city Qazvin |
| 29 | 04-08-05-02-00 | 43 | صلام‌الله علی | صلّی‌الله علیه | standard blessing on the Imam = صلّی‌الله علیه |
| 30 | 05-07-18-07-30 | 179 | صلامالله علیه | صلّی‌الله علیه | same |
| 31 | 04-08-05-02-00 | 25 | سلامالله علی | صلّی‌الله علیه | «از امام سجاد سلامالله علی» |
| 32 | 04-08-26-22-00 | 11 | حجرت‌الاسلام | حجت‌الاسلام | clerical title = حجت‌الاسلام |
| 33 | 05-07-18-03-00 | 56 | حجرت‌الاسلام | حجت‌الاسلام | «توسط حجرت‌الاسلام بر مسلمین» |
| 34 | 04-08-06-02-00 | 45 | هجت‌الاسلام | حجت‌الاسلام | «از زبان هجت‌الاسلام المسلمین حسینی» |
| 35 | 05-07-17-23-30 | 105 | هجت | حجت | «یا هجت الله» → حجت |
| 36 | 05-07-18-03-30 | 21 | هجت‌الاسلام | حجت‌الاسلام | «هجت‌الاسلام و المسلمین زین‌العابدینی» |
| 37 | 05-07-17-23-30 | 135 | هجت‌ان | حجتان | dhikr of the Imams = حجتان |
| 38 | 05-07-18-03-00 | 106 | نحجی البلاغه | نهج‌البلاغه | Imam Ali's book = نهج‌البلاغه |
| 39 | 05-07-18-03-00 | 110 | نحجی البلاغه | نهج‌البلاغه | «نامهٔ نحجی البلاغه، نامهٔ چهل و یکم» |
| 40 | 04-08-19-02-00 | 75 | سدجا | سجاد | «دعای امام سدجا» → Imam Sajjad |
| 41 | 04-08-26-02-00 | 12 | انکبود | بقره | surah name = بقره (Baqarah ayah 65) |
| 42 | 04-08-26-22-00 | 68 | انکبود | بقره | «در سوره انکبود آیه شصت و پنج» |
| 43 | 04-09-03-02-00 | 38 | نهر | نساء | surah name = نساء (Nisa ayah 106) |
| 44 | 04-09-03-02-00 | 38 | آل امران | آل عمران | surah name = آل عمران (Al Imran ayah 28) |
| 45 | 04-08-27-02-00 | 73 | بغره | بقره | surah name = بقره (Baqarah ayah 83); «بقره» appears correctly elsewhere in the same file |
| 46 | 04-08-27-02-00 | 13 | محترات | محرمات | «امساک از محترات است» → what to abstain from = محرمات |
| 47 | 04-08-27-22-00 | 122 | محترات | محرمات | same |
| 48 | 04-08-05-02-00 | 27 | رمزان | رمضان | month name = رمضان |
| 49 | 04-08-27-22-00 | 134 | رمزان | رمضان | «اول ماه رمزان» |
| 50 | 04-09-03-22-00 | 113 | محوصی | محاصره | «در محوصی تاریک بودی ولی با کربلا» → siege = محاصره |

---

## Notes for the reviewer

- **Count: 50** (task asked for 50; all 50 are present and each is context-verifiable,
  so no "fewer than 50" fallback was needed).
- The dominant error families are: (a) **place names** (عراق/عراقی, قزوین, قم),
  (b) **religious honorifics & book/surah names** (صلّی‌الله علیه, حجت‌الاسلام,
  نهج‌البلاغه, سجاد, بقره, نساء, آل عمران), (c) **captivity vocabulary**
  (اسارت/اسرا, بعثیان), (d) **homophone misspellings** (عنوان, اردوگاه, محرمات,
  رمضان, محاصره).
- These are the errors a conservative corrector **should** still fix even when it
  is told to leave everything else byte-identical. If STEP 9B.2's conservatism
  drives recall on these toward zero, that is the trade-off to report.
- Several labels share a file but are on **different blocks** (deliberate), so
  per-block recall counting is unambiguous.
