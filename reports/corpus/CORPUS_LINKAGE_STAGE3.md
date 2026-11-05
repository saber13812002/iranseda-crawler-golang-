# Stage 3 — IranSeda Corpus Asset Verification (5-way)

**Date:** 2026-11-05 (UTC) · **Status:** COMPLETE (no BLOCKED items)
**Owning repo:** `git@github.com:saber13812002/iranseda-crawler-golang-.git`
**Branch:** `stage2-corpus-linkage` — Stage 3 commits stacked on the Stage 2 tip `61f7970e8ed32c7b8fdf1eee8398bd584cee908f` (no new branch)
**Commits:** `f24ad75fc0cef9994144111154ab5e5dfa4ec1bb` (module+CLI) · `063aa7a5cdb8fcd7130b0b8323c54ef167e0df88` (tests) · `4b421e689d5d78c7022f35ea8676559be3e087c5` (report+data) · `ab61e71155fd120ff75c8de7dd847f97d96152c4` (metadata backfill) · `0be5909f2bdfd8591248d0c9768f8d8f8155272e` (records the backfill SHA) · +1 commit (branch HEAD: post-note, see §9)
**Push:** `origin stage2-corpus-linkage` → pushed, fast-forward, no force (output in §8)

> Companion spec: [`CORPUS_LINKAGE_SPEC.md`](../../docs/corpus/CORPUS_LINKAGE_SPEC.md)
> (Stages 0–2 delivered earlier; this is Stage 3, Tasks A–D.)

---

## 1. Scope & hard constraints (all honored)

- **NO** production deploys, **NO** running-service changes, **NO** DB writes
  (all SQL was `SELECT`-only via the read-only `corpus.database.Database`),
  **NO** re-export/re-index/re-embedding.
- All work inside the git worktree `/tmp/saber_stage3_wt` attached to the
  existing branch `stage2-corpus-linkage`; the main worktree was touched
  **read-only** (pre/post HEAD identical:
  `c855312cfa5c2845a23def1f9e661c6ac30442a7` at the Task C window; see §9).
- Bounded HTTP to the asset host only: **≤ 2 workers, hard budget 300,
  15 s per-request cap, URL dedup, resumable per-URL cache** (§7).
- **R7:** GitHub user/repo parsed at runtime from the real `git remote`;
  branch read at runtime from production `.env` `GITHUB_BRANCH`;
  URL generation **aborts (exit 2)** if any of the three is missing —
  nothing hardcoded.
- No secrets, tokens, or `.env` content committed anywhere.

## 2. Open questions resolved (Task A)

| OQ | Question | Resolution | Evidence |
|----|----------|------------|----------|
| OQ-4 | Host/group/namespace for asset URLs (C5/C6) | The production remote is **GitHub** (`git@github.com:saber13812002/iranseda-crawler-golang-.git`), not the GitLab host assumed in spec §5.2 — **documented spec discrepancy** (same pattern as Stage 2 OQ-1). User/repo are parsed from the real remote at runtime and the branch from `.env` `GITHUB_BRANCH` (`download-db`); raw/blob URL builders abort (exit 2) without them (R7) | run JSON `run.github` = `{user: saber13812002, repo: iranseda-crawler-golang-, branch: download-db}`; `assets.parse_github_remote` / `_require_branch` + `test_url_builder_aborts_without_branch_r7` |
| OQ-5 | Full stem-family enumeration gate | F1∪F2 grammar (canonical `radio-<program>-dd-mm-…` + legacy underscore) is the only gate: 22/24 sampled sessions classify `canonical`; the 2 filename-less sessions → `stem_family=none` → **no date emitted**; a server-side `git ls-tree` classification of `origin/download-db`'s whole tree found the canonical family dominant; the grammar was **not** extended with unverified families (R5) | run JSON `summary.stem_family`; probe `_work/stage3_git_probe2.sh` (workspace) |
| OQ-6 | `download-db` ↔ working-tree parity | Operational branch (main worktree checkout) = **`phase3-radio-rag-service`** (not `download-db`). Sample parity: on-disk 61/86 · in asset branch 54 · in operational branch 58. The only asset-branch gap is 4 `raw_srt` files (on disk + operational, never pushed to `download-db`); **audio is in neither branch** (§4.4.1). On-disk presence alone never yields a URL (R5) | run JSON `git_tree` + per-type counts; probe `_work/stage3_git_probe2.sh` (per-branch tree SHAs) |
| OQ-10 | Raw-SRT location pattern | Raw SRT = `downloads/<stem>.srt` (top level, **not** `cleaned/`); corrected artifacts = `downloads/cleaned/<stem>.correct.{srt,txt}`; summaries = `downloads/cleaned/<stem>.summary{,.en}.txt`. **Stored-path-first** stands: DB `srt_filename` / LLM `file_relpath` are used verbatim when present; pattern relpaths are derived only for canonical stems | per-asset `relpath` fields in the run JSON; probe `_work/stage3_find_downloads.sh` |

Not closed (deliberately): OQ-9 (out of scope), OQ-12 (Stage 4 sizing).

## 3. Deliverable module (Task B)

New files in the owning repo (module+CLI in commit `f24ad75fc0cef9994144111154ab5e5dfa4ec1bb`, tests in
`063aa7a5cdb8fcd7130b0b8323c54ef167e0df88`):

| File | Purpose |
|------|---------|
| [`corpus/assets.py`](../../corpus/assets.py) | asset registry + 5-way verifier + bounded HTTP + large-file fingerprint probes |
| [`corpus/scan_assets.py`](../../corpus/scan_assets.py) | CLI: DB selection → registry → 5-way verification → JSON report |
| [`tests/corpus/test_assets.py`](../../tests/corpus/test_assets.py) | 46 **offline** unit tests (fake fetch/git, no network) |

### 3.1 `corpus/assets.py`

- **`build_registry(sessions, llm_rows, github, …)`** — audio from
  `filename` → `downloads/<basename>`; raw SRT from `srt_filename` (only
  when non-null) → `downloads/<basename>`; LLM rows verbatim by
  `file_relpath` (`correct_subtitles`→`corrected_srt`, `correct_text`→
  `corrected_txt`, `summary`→`summary_fa`, `full_text`→`full_txt`);
  `summary_en` pattern asset at `downloads/cleaned/<stem>.summary.en.txt`
  **only for canonical stems**; duplicate relpath → latest row wins;
  quarantine (spec §10.1) flags every asset of a quarantined session.
- **5-way checks:**
  1. **C9 on-disk** (`check_disk`) — presence, `size_bytes`, `sha256`;
     files above `DEFAULT_SHA_CAP` (30 MB) get a bounded
     `{head_sha256, tail_sha256, size_bytes}` fingerprint (1 MB chunks)
     instead of a full-body hash.
  2. **C10 git-tree** (`check_git_tree`) — `git ls-tree` on
     `origin/<GITHUB_BRANCH>` for the exact relpath.
  3. **C12 publishing commit** — `git log -1` on the relpath
     (`publishing_commit_sha`, `produced_at`, `processing_version`).
  4. **Operational-branch parity** (OQ-6) — same check against the
     operational ref (default: main worktree's checked-out branch).
  5. **HTTP raw URL + sha256** (`verify_http`) — see below.
  - **C11 `published`** = f(C9, C10, quarantine); recomputed after each
    stage; legitimately `None` until the git stage has run (pipeline
    incomplete). **C5/C6 URLs are exposed only when `published` (R5).**
- **Bounded HTTP:** URL-deduped plan, hard `max_requests` budget,
  `workers ≤ 2`, `timeout` hard-capped at 15 s, resumable per-URL JSON
  cache (`<out>.http_cache.json`). For large on-disk files
  (fingerprint present) the body is **never** fully downloaded —
  `fp_range_fetch` issues at most **two Range GETs** (head/tail 1 MB)
  and compares against the stored fingerprint (`fp_match` /
  `fp_mismatch`); files without a fingerprint above the cap are
  `skipped_large`.

### 3.2 `corpus/scan_assets.py` (CLI)

Args: `--root`, `--repo`, `--downloads-dir` (base for asset relpaths;
default `<root>` — relpaths start with `downloads/`), `--out` (required),
`--session-ids`, `--stem-prefixes`, `--stratified N`, `--timeout 15`,
`--max-requests`, `--workers 2`, `--no-http`. Flow: R7 github load
(abort exit 2 on missing user/repo/branch) → read-only `git fetch origin`
→ read-only DB selection (explicit ids ∪ stem prefixes ∪ deterministic
index-interpolated stratified picks, ≥5 programs enforced; `IN` lists
expanded to explicit placeholders) → `build_registry` →
`check_disk(sha_cap_bytes=DEFAULT_SHA_CAP)` →
`check_git_tree(operational_ref)` → `verify_http(cache)` → JSON via
tmp+replace.

### 3.3 Tests

46 offline tests (injected fake fetch / fake git; zero network):
filename classification (canonical, suffix, legacy underscore, copy,
numbered, 3-digit tail, invalid date/time, non-radio), `session_uid`,
raw/blob URL templates, **R7 aborts** (no branch / no identity),
registry (mission A assets, no summary_en for unparsed stems, LLM
pass-through / no-relpath skip / orphan ignore, duplicate-latest-wins,
quarantine flagging, C5/C6 hidden until published), `check_disk`
(C9/C8/C7, relpath sanitization, fingerprint), `check_git_tree`
(C10/C12/operational, published recomputation), `verify_http` (sha
match, 404, mismatch, `skipped_large`, budget skip, **resumable
cache**, fetch-exception recording, shared-filename dedup, worker cap
via barrier, status filter), `fp_range_fetch` (match, tail mismatch,
size mismatch, 404), **large→fp probe routing with no full download**,
no-fingerprint fallback, `five_way_row` shape/URL rule, `summarize`,
`parse_github_remote` (https/ssh/non-GitHub rejection).

- **Laptop (Python 3.13.7, Windows):** corpus suite **83/83**
  (46 new + 37 Stage 2).
- **53 venv (Python 3.12.3, Linux):** full corpus suite **173/173**
  (90 pre-existing + 46 new + 37 Stage 2) + `py_compile` + import smoke
  in the worktree.

## 4. Live validation (Task C)

Selection: explicit mission sessions **5793, 10569** (mission A) and
**5290, 7040** (mission B) + **20 stratified** (deterministic index
interpolation; 18 distinct programs) = **24 sessions / 86 assets**
(20 distinct stems, Jalali 1403-01 … 1405-08). **Mission C**
(`ch=14, e=154148409`) has **no matching DB session** (Task A
read-only probe) → expected absence, recorded here, not a failure.

Final run: 2026-11-05T22:15:49Z → 22:16:19Z (30.3 s), 82 distinct-URL
requests (budget 300), 2 workers, 15 s cap, 0 HTTP errors. Full
per-asset evidence (SHAs, commit SHAs, sizes, timestamps) in
[`stage3_asset_verification.json`](stage3_asset_verification.json).

### 4.1 Final coverage matrix (86 assets)

| Asset type | Total | On disk | In asset branch | In operational branch | HTTP 200 | HTTP 404 | sha256 match | Status |
|------------|------:|--------:|----------------:|----------------------:|---------:|---------:|-------------:|--------|
| audio | 22 | 3 | 0 | 0 | 0 | 22 | — | missing ×19, not_published ×3 |
| corrected_srt | 11 | 11 | 11 | 11 | 11 | 0 | **11/11** | published ×11 |
| corrected_txt | 10 | 10 | 10 | 10 | 10 | 0 | **10/10** | published ×10 |
| summary_en | 22 | 16 | 16 | 16 | 16 | 6 | **16/16** | published ×16, missing ×6 |
| summary_fa | 10 | 10 | 10 | 10 | 10 | 0 | **10/10** | published ×10 |
| full_txt | 3 | 3 | 3 | 3 | 3 | 0 | **3/3** | published ×3 |
| raw_srt | 8 | 8 | 4 | 8 | 4 | 4 | **4/4** | published ×4, not_published ×4 |
| **Total** | **86** | **61** | **54** | **58** | **54** | **32** | **53/53, 0 mismatch** | |

The HTTP columns are **asset-level** (86 rows). At the URL level 4
relpaths are shared by two mission sibling sessions (the two `.mp4`
audio pairs 5793/10569 + 5290/7040, and the two
`summary.en.txt` pairs), so the deduped request set is **82 URLs =
53×200 + 29×404** — exactly matching `http_stats`
(`requests_used=82`, `http_200=53`, `http_404=29`).

Zero sha mismatches, zero errors/timeouts. Fingerprint probes: 0 (no
on-disk file in the sample exceeded the 30 MB cap; the 3 on-disk
audios are 14.4–14.9 MB — the fp path is covered by offline tests only).

### 4.2 Mission A (`radio-maaref-05-07-19-13-30`) — sessions 5793, 10569 (program 37)

- **5793** (`e=154067181`): 4 assets. `corrected_srt`
  sha256 `779f054b1aa1…` (34,708 B) and `raw_srt` sha256
  `3c364d30a890…` (34,564 B) both fully 5-way verified — published,
  on disk, in both branches, HTTP 200, sha match; shared publishing
  commit `d8ddc51a4564fc11547161114bc0dd96ef87e3f6` (produced
  2026-10-11, `qwen38-nothinking`). `audio` + `summary_en` absent:
  404 on `download-db`, not on disk.
- **10569** (`e=154133207`): `audio` + `summary_en` absent (404).

### 4.3 Mission B (`radio-maaref-05-03-10-05-30`) — sessions 5290, 7040

- **5290** (`e=153642040`, program 11): 7 assets, 5 fully 5-way
  verified (published + on disk + both branches + HTTP 200 + sha match):

  | Asset | sha256 (first 12) | Size | Publishing commit | Produced |
  |-------|-------------------|------:|-------------------|----------|
  | corrected_srt | `b3892b84c4d4…` | 28,404 | `fecdfaae61c9ed37…` | 2026-10-10 |
  | corrected_txt | `19014a63d10c…` | 19,343 | `384045077e9609bd…` | 2026-10-08 |
  | full_txt | `d64f100cbf68…` | 23,162 | `a1b52a78cfbe0269…` | 2026-10-07 |
  | raw_srt | `e683c93059a4…` | 28,444 | `4c65666bd584c7bc…` | 2026-10-06 |
  | summary_en / summary_fa | `804c3c7ff647…` / `2782d6c5208c…` | 813 / 1,386 | `2e3eacadd819ab95…` | 2026-10-07 |

  `audio` (`…10-05-30.mp4`) 404 — see finding 1.
- **7040** (`e=153642041`, `srt_filename` NULL): `summary_en` verified
  (shares session 5290's relpath — one deduped URL); `audio` 404.

### 4.4 Findings (data findings, not tooling defects)

1. **Raw audio is never pushed to `download-db`:** 0/22 audio assets in
   the asset branch (and 0/22 in the operational branch); all 22 raw
   URLs 404. The 3 on-disk audios (14.4–14.9 MB) are local-only. By
   policy (C10 false) the registry correctly leaves every audio asset
   `missing`/`not_published` — no C5/C6 URL is ever emitted for audio.
2. **4 `raw_srt` are `not_published`:** on disk and present in the
   operational branch, but absent from `download-db` (raw-SRTs were
   pushed before the pipeline started committing them). Correctly
   held back from URL emission (R5); their 404s confirm the branch
   state.
3. **6 `summary_en` missing** (sessions 5793, 6880, 8026, 9173, 9746,
   10569): the pattern asset exists nowhere — the pipeline simply did
   not produce an English summary for those stems (16/22 produced).
4. **The DB is live-growing:** the stratified id set shifted by +1
   between two probe runs (max id ≥ 10,890); selection is
   deterministic at run time, and this run is a point-in-time snapshot.
5. **2 filename-less sessions** (10319, 10892) → no stem, no date
   emitted (R5) — the gate works as designed.

## 5. Coverage statement (what this proves, what it doesn't)

- **Proven (on this sample, 2026-11-05):** the 5-way verifier runs
  end-to-end against live production data; **53/53 fetched bodies
  sha256-match** their local files (0 mismatches); C9/C10/C12 and
  operational-branch parity are all measurable and mutually
  consistent; URL discipline (published-only exposure, R5) held for
  every asset; mission A/B assets are verified with full publishing
  provenance (commit SHA + produced_at + processing version).
- **Not proven / out of scope:** extrapolation to the full ~10,890
  session corpus (per-asset results only); any audio URL publication
  (none exists on the branch); mission C (no DB session — expected
  absence); the large-file fingerprint probe over the real network
  (no on-disk sample file exceeded 30 MB — covered by offline tests
  only); Stage 4+ work (linkage import, RAG citation embedding,
  deploys).

## 6. BLOCKED items

**None.** Every Task A/B/C/D objective completed within budget and
constraints.

## 7. Request budget (politeness)

| Bucket | Requests (raw-asset URLs) |
|--------|---------:|
| Task A probes (git protocol + SELECT-only SQL) | 0 |
| Task C intermediate run (built initial per-URL cache) | 85 |
| Task C final run (82 distinct URLs; stale cache purged first) | 82 |
| **Total** | **167 / 300 budget per run** |

≤ 2 workers, 15 s timeout cap, URL dedup, resumable per-URL cache,
asset host (`raw.githubusercontent.com`) only.

## 8. Git (Task D)

- Worked in the git worktree `/tmp/saber_stage3_wt` attached to the
  **existing** branch `stage2-corpus-linkage` (no `-b`); the main
  worktree was read-only: pre/post HEAD both
  `1585c1aa29f88f51903f5e6dc955c7397928a7` (a production
  refresh-loop commit landed during the day; see §9).
- Commits (5, Stage 2 convention — the last two are metadata
  backfills):
  1. `f24ad75fc0cef9994144111154ab5e5dfa4ec1bb` — `corpus/assets.py` + `corpus/scan_assets.py`
  2. `063aa7a5cdb8fcd7130b0b8323c54ef167e0df88` — `tests/corpus/test_assets.py`
  3. `4b421e689d5d78c7022f35ea8676559be3e087c5` — `reports/corpus/CORPUS_LINKAGE_STAGE3.md` +
     `reports/corpus/stage3_asset_verification.json`
  4. `ab61e71155fd120ff75c8de7dd847f97d96152c4` — backfill of the commit SHAs and push output into
     this report
  5. branch HEAD (this commit) — records the backfill commit SHA above
- Push #1 (after commit 3): `git push origin
  stage2-corpus-linkage` — fast-forward from the Stage 2 tip,
  **no force**. Output below. Push #2 (after commit 5) advanced the
  ref to branch HEAD; origin was verified in sync via
  `git ls-remote`.

```
To github.com:saber13812002/iranseda-crawler-golang-.git
   61f7970e8..4b421e689  stage2-corpus-linkage -> stage2-corpus-linkage
```

### What did NOT change in production

- No deploy, no service restart, no running crawler/RAG job touched.
- No writes to any database (`radio` db untouched; probes were
  `SELECT` only).
- No re-export, no SRT/TXT regeneration, no re-index, no config
  change; no new files or modifications in the main worktree (pre/post
  HEAD identical; pre-existing untracked noise untouched).
- The committed history lives solely on `stage2-corpus-linkage`;
  `phase3-radio-rag-service` (operational) is unchanged.
- No secrets/`.env`/tokens in any committed path; the per-URL HTTP
  cache (`stage3_asset_verification.json.http_cache.json`) was left
  untracked in the worktree.

## 9. Post-note — production auto-refresh drift (recorded post-commit)

Between the Task C run (22:15Z; main worktree at
`c855312cfa5c2845a23def1f9e661c6ac30442a7`) and the Task D commit run
(22:38Z), the production hourly refresh loop committed `1585c1aa29f88f51903f5e6dc955c7397928a77a`
(`auto: refresh site + subtitles (2026-11-05_22:30)`, 2026-11-05 22:30:04 +0000) to `phase3-radio-rag-service`. The Task D run itself was
pre/post identical (`1585c1aa29f88f51903f5e6dc955c7397928a7` → same):
the refresh commit landed **before** the run started, not during it.
No statement in §1/§8 changes in substance: the main worktree was
read-only throughout, and the Stage 3 commits live solely on
`stage2-corpus-linkage`.
