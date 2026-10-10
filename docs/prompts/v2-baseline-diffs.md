# v2 baseline — 20-file diff archive (STEP 9B, pre-tuning)

Baseline `correct_text_v2` (3 hard-rule prompt, temp 0.2) vs the original SRT,
same 20 files as the STEP 9B QA. Captured **before** the STEP 9B.2
conservative-tuning re-run, so the new run can be A/B'd against it.

**Method:** each original block text (`' '.join(lines)` after `srt_parse`) is
compared index-for-index against the same block in the baseline
`.correct.v2.srt`. A block counts as **changed** if its text differs
byte-for-byte. Timestamps were verified identical (ts_match 20/20 in 009).

## Headline

| metric | value |
|---|---|
| files | 20 |
| total blocks | 3129 |
| total changed blocks | 957 |
| overall change (changed/total blocks) | 30.6% |
| **average per-file change rate** | 32.1% |
| min / max per-file change rate | 15.3% / 54.5% |

(Matches the 009 QA: avg 33.2% / max 54.5% / min 15.3% — reproduced here.)

## Per-file

| stem | blocks | changed | rate |
|---|---|---|---|
| 04-08-05-02-00 | 156 | 51 | 32.7% |
| 04-08-06-02-00 | 169 | 57 | 33.7% |
| 04-08-12-02-00 | 192 | 43 | 22.4% |
| 04-08-13-02-00 | 227 | 53 | 23.3% |
| 04-08-19-02-00 | 112 | 52 | 46.4% |
| 04-08-20-02-00 | 190 | 29 | 15.3% |
| 04-08-26-02-00 | 198 | 54 | 27.3% |
| 04-08-26-22-00 | 99 | 54 | 54.5% |
| 04-08-27-02-00 | 133 | 50 | 37.6% |
| 04-08-27-22-00 | 146 | 62 | 42.5% |
| 04-09-03-02-00 | 125 | 44 | 35.2% |
| 04-09-03-22-00 | 160 | 54 | 33.8% |
| 05-07-17-23-30 | 156 | 63 | 40.4% |
| 05-07-18-01-30 | 176 | 30 | 17.0% |
| 05-07-18-03-00 | 163 | 43 | 26.4% |
| 05-07-18-03-30 | 91 | 25 | 27.5% |
| 05-07-18-06-00 | 114 | 44 | 38.6% |
| 05-07-18-07-30 | 199 | 46 | 23.1% |
| 05-07-18-09-00 | 113 | 38 | 33.6% |
| 05-07-18-13-30 | 210 | 65 | 31.0% |

## What the change rate is made of (why 33% is too high)

Reading the 957 edits, they fall into three classes. The conservative corrector
(STEP 9B.2) must fix class 1 and leave classes 2-3 alone:

1. **Genuine ASR errors** (the ones to keep fixing) — real words spelled wrong /
   homophones, e.g. `انوان`→`عنوان`, `اردوگا`→`اردوگاه`, `عصارت`→`اسارت`,
   `تراوت`→`طراوت`, `سپسی`→`سپاسی`, `پنجامه مهما`→`پنجم آبانماه`,
   `معمول‌نظمه`→`افتخار`.
2. **Hamza/`‌ً`-placement normalization** — `تقریبا‌ً`→`تقریباً`, `اسلامم`→`اسلام`,
   `بهترین` re-spacing, `ان‌شاءالله`→`انشاالله`. Not a real error; changes byte
   count but no meaning.
3. **Added punctuation / resegmentation** — the model inserts commas and full stops
   and re-splits a sentence across blocks (e.g. `... بود، به این شکمه` adds a comma).
   Pure style.

Class 1 is the useful minority; classes 2-3 inflate the rate. STEP 9B.2 lowers
temperature and tightens the prompt to suppress 2 and 3 (keep original byte-identical)
while still catching 1.

## All 957 changed blocks

Full per-block diff (stem / block-index / original / fixed) is in the companion file
`v2-baseline-edits.txt` (one line each: stem, block-index, original, fixed — tab-separated).

