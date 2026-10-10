# v2 TUNED — 20-file diff archive (STEP 9B.2.4, post-tuning)

Same 20 files, same comparison (new conservative `correct_text_v2` vs the
original SRT). This is the **after** side of the A/B against
`v2-baseline-diffs.md` (the pre-tuning baseline, temp 0.2).

**Change:** temperature 0.2 → **0.0** and the prompt tightened to
conservative mode (keep original byte-identical on uncertainty; no
colloquial→formal, no punctuation/hamza re-normalization, no restructure).
Method and hard constraints are identical to the baseline archive.

## A/B headline (baseline temp-0.2 → tuned temp-0.0)

| metric | baseline (0.2) | **tuned (0.0)** | delta |
|---|---|---|---|
| total blocks | 3129 | 3129 | — |
| total changed blocks | 957 | **376** | -581 |
| average per-file change rate | 33.2% | **12.5%** | -20.7 pp |
| max per-file change rate | 54.5% | **20.5%** | -34.0 pp |
| min per-file change rate | 15.3% | **4.2%** | -11.1 pp |
| blocks in == out | 20/20 | 20/20 | — |
| timestamps unchanged | 20/20 | 20/20 | — |
| original SRT MD5 unchanged | 20/20 | 20/20 | — |
| recall: obvious labeled errors fixed | n/a (baseline predates labels) | **23/50 (46%)** | — |

Reading: the change rate dropped **~61% of the edits** (957 → 376 changed blocks;
average per-file rate 33.2% → 12.5%) — the model now edits a small
minority of blocks, which is what a conservative corrector should do. The cost
is recall: of the 50 hand-labeled obvious ASR errors, only 23 (46%) were fixed —
it still catches high-context homophones (عنوان, اردوگاه, اسارت in clear
context, نهج‌البلاغه, سجاد, آل عمران, محاصره, رمضان) but now *holds* the
lower-context ones (عصرا→اسرا, عرق→عراق in «تکریت», صلامالله→صلّی‌الله, قوم→قم,
قزه→قزوین) rather than guessing. That is the intended conservatism trade-off, and
it is reported honestly, not hidden.

## Per-file (tuned)

| stem | blocks | changed | rate |
|---|---|---|---|
| 04-08-05-02-00 | 156 | 19 | 12.2% |
| 04-08-06-02-00 | 169 | 21 | 12.4% |
| 04-08-12-02-00 | 192 | 8 | 4.2% |
| 04-08-13-02-00 | 227 | 25 | 11.0% |
| 04-08-19-02-00 | 112 | 20 | 17.9% |
| 04-08-20-02-00 | 190 | 16 | 8.4% |
| 04-08-26-02-00 | 198 | 34 | 17.2% |
| 04-08-26-22-00 | 99 | 16 | 16.2% |
| 04-08-27-02-00 | 133 | 24 | 18.0% |
| 04-08-27-22-00 | 146 | 30 | 20.5% |
| 04-09-03-02-00 | 125 | 18 | 14.4% |
| 04-09-03-22-00 | 160 | 23 | 14.4% |
| 05-07-17-23-30 | 156 | 13 | 8.3% |
| 05-07-18-01-30 | 176 | 14 | 8.0% |
| 05-07-18-03-00 | 163 | 13 | 8.0% |
| 05-07-18-03-30 | 91 | 9 | 9.9% |
| 05-07-18-06-00 | 114 | 22 | 19.3% |
| 05-07-18-07-30 | 199 | 12 | 6.0% |
| 05-07-18-09-00 | 113 | 12 | 10.6% |
| 05-07-18-13-30 | 210 | 27 | 12.9% |

## Precision (spot-check of the 376 edits)

Each edit is one of three classes (auto-split by a hamza/ZWNJ/punctuation-normalized
compare, then hand-checked):

- **~129 cosmetic** (hamza/ta-marbuta/ZWNJ/punctuation/spacing only — e.g.
  `دقا‌ً`→`دقیقاً`). The baseline had far more of these; the temp-0.0 +
  explicit no-normalization rule cut them, but did not zero them.
- **~247 content** changes. The **majority are genuine ASR fixes**: `اردوبا`→
  `اردوگاه`, `اصارت`→`اسارت`, `پنجامه مهما`→`پنجم آبانماه`, `نهج‌البرابه`→
  `نهج‌البلاغه`, `مخمد`→`محمد`, `الیاف`/`القیف`→`الغیث`, `لبخم`→`لبخند`, `باغر`→
  `باقر`, `سدجا`→`سجاد`, `عصارت`→`اسارت`, `نحجی البلاغه`→`نهج‌البلاغه`, etc.
- **~3 regressions found** (the model 'corrected' a fine word into a wrong one):
  | file | block | was | became |
  |---|---|---|---|
  | 04-08-06-02-00 | 169 | پرسمان (show name, correct) | پرسبان (broken) |
  | 04-08-13-02-00 | 106 | عربه (Quranic Erebah, correct) | عروه (Awrah — wrong) |
  | 04-08-13-02-00 | 201 | ریایش (ASR for نیایش) | ریاض (a *different* wrong word) |

So even at low change-rate, precision is not 100%: the conservative editor still
occasionally swaps a word for a different real word. ~3 regressions in 3129 blocks
is rare, but it is the reason this stays a `.correct.v2` **artifact for diffing**
and is NOT wired into the bulk pipeline (per the STOP rule).

## All 376 changed blocks (tuned)

Full per-block diff (stem / block-index / original / fixed) is in the companion file
`v2-tuned-edits.txt`. Recall detail (all 50 labels, FIXED/NOT + the v2 text) is in
`docs/prompts/v2-labeled-errors.md` cross-referenced in 009 §9.2.

