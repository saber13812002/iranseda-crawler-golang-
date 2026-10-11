#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
postpass_v2.py — STEP 9B.3 — deterministic proper-noun post-pass for
correct_text_v2 (QA measurement tool; no LLM, no model spend, read-only
against downloads/).

What it does
------------
1. Loads dashboard/lexicon.json.
2. Reads the 20 original SRTs (downloads/radio-maaref-<stem>.srt) and the
   20 tuned v2 outputs (a directory of <stem>.correct.v2.srt — by default the
   repo's canonical downloads/cleaned copies; point --v2dir at a different
   run, e.g. a copy of the authoritative 53 output, to re-score that one).
3. Applies the post-pass to every v2 block:
     a) PROTECTED terms: verify the pass never touches a program/show name.
     b) SAFE non-word replacements: whole-token (and known suffixed-form)
        replacement, applied only when the token is a standalone ASR
        non-word.
     c) CONTEXT rules: wrong real-word tokens swapped only when the block
        contains a co-occurring disambiguating cue word.
   SRT structure (index/timestamps) is never touched.
4. Writes the post-passed SRTs to --out (default /tmp/v2_postpass).
5. Scores the 50 hand-labeled obvious errors (v2-labeled-errors.md) on BOTH
   the untouched v2 output and the post-passed output (identical substring
   scoring rule as 9B.2.4), prints the recall delta + every per-label state
   change, the new-replacement ledger (token -> count), and a regression
   spot-check (the 3 known 9B.2.4 regressions + protected-term survival).
6. Emits a unified diff of v2 -> post-passed per file.

Usage:
  python3 postpass_v2.py [--lexicon dashboard/lexicon.json]
                         [--v2dir downloads/cleaned] [--out <tempdir>]
                         [--diff-dir <tempdir>/diffs]

  Output goes to the OS temp dir by default — this tool NEVER writes into
  downloads/ or the repo working tree.

Exit code 0 always (it is a measurement tool, not a gate).
"""
import argparse
import difflib
import json
import os
import re
import sys
import tempfile
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOWNLOADS = os.path.join(ROOT, "downloads")

STEMS = [
    "04-08-05-02-00", "04-08-06-02-00", "04-08-12-02-00", "04-08-13-02-00",
    "04-08-19-02-00", "04-08-20-02-00", "04-08-26-02-00", "04-08-26-22-00",
    "04-08-27-02-00", "04-08-27-22-00", "04-09-03-02-00", "04-09-03-22-00",
    "05-07-17-23-30", "05-07-18-01-30", "05-07-18-03-00", "05-07-18-03-30",
    "05-07-18-06-00", "05-07-18-07-30", "05-07-18-09-00", "05-07-18-13-30",
]
FULL = ["radio-maaref-" + s for s in STEMS]

# The 50 labels from docs/prompts/v2-labeled-errors.md:
# (stem, block1, original, expected, family)
LABELS = [
    ("04-08-05-02-00", 22, "انوان", "عنوان", "عنوان"),
    ("04-08-05-02-00", 23, "انوان", "عنوان", "عنوان"),
    ("04-08-26-02-00", 44, "انوان", "عنوان", "عنوان"),
    ("04-09-03-02-00", 35, "انوان", "عنوان", "عنوان"),
    ("04-08-05-02-00", 2, "اردوگا", "اردوگاه", "اردوگاه"),
    ("04-08-12-02-00", 13, "اردوگا", "اردوگاه", "اردوگاه"),
    ("04-08-27-02-00", 17, "اردوگا", "اردوگاه", "اردوگاه"),
    ("04-08-26-22-00", 63, "اردوگا", "اردوگاه", "اردوگاه"),
    ("04-08-13-02-00", 14, "عصارت", "اسارت", "اسارت"),
    ("04-08-13-02-00", 52, "عصارت", "اسارت", "اسارت"),
    ("04-08-27-22-00", 95, "عصارت", "اسارت", "اسارت"),
    ("04-08-13-02-00", 50, "عصارت", "اسارت", "اسارت"),
    ("04-08-19-02-00", 16, "عصرا", "اسرا", "اسرا"),
    ("04-08-20-02-00", 2, "عصرای", "اسرای", "اسرا"),
    ("04-08-20-02-00", 25, "عصرا", "اسرا", "اسرا"),
    ("04-08-20-02-00", 27, "عصر را", "اسرا را", "اسرا"),
    ("04-08-26-22-00", 25, "عصرا", "اسرا", "اسرا"),
    ("04-09-03-02-00", 24, "حصارت", "اسارت", "اسارت"),
    ("04-08-27-22-00", 79, "احصارت", "اسارت", "اسارت"),
    ("04-08-27-22-00", 44, "عصارت", "اسارت", "اسارت"),
    ("04-08-27-22-00", 46, "موزوران", "بعثیان", "بعثیان"),
    ("04-08-27-02-00", 23, "عرق", "عراق", "عراق"),
    ("04-08-27-02-00", 3, "عرق", "عراق", "عراق"),
    ("04-08-27-02-00", 5, "عرقی", "عراقی", "عراق"),
    ("04-08-26-22-00", 49, "عرق", "عراق", "عراق"),
    ("04-08-27-22-00", 133, "عرق", "عراق", "عراق"),
    ("04-08-06-02-00", 64, "قوم", "قم", "قم"),
    ("04-08-26-22-00", 14, "قزه", "قزوین", "قزوین"),
    ("04-08-05-02-00", 43, "صلام‌الله علی", "صلّی‌الله علیه", "صلّی‌الله"),
    ("05-07-18-07-30", 179, "صلامالله علیه", "صلّی‌الله علیه", "صلّی‌الله"),
    ("04-08-05-02-00", 25, "سلامالله علی", "صلّی‌الله علیه", "صلّی‌الله"),
    ("04-08-26-22-00", 11, "حجرت‌الاسلام", "حجت‌الاسلام", "حجت"),
    ("05-07-18-03-00", 56, "حجرت‌الاسلام", "حجت‌الاسلام", "حجت"),
    ("04-08-06-02-00", 45, "هجت‌الاسلام", "حجت‌الاسلام", "حجت"),
    ("05-07-17-23-30", 105, "هجت", "حجت", "حجت"),
    ("05-07-18-03-30", 21, "هجت‌الاسلام", "حجت‌الاسلام", "حجت"),
    ("05-07-17-23-30", 135, "هجت‌ان", "حجتان", "حجت"),
    ("05-07-18-03-00", 106, "نحجی البلاغه", "نهج‌البلاغه", "نهج"),
    ("05-07-18-03-00", 110, "نحجی البلاغه", "نهج‌البلاغه", "نهج"),
    ("04-08-19-02-00", 75, "سدجا", "سجاد", "سجاد"),
    ("04-08-26-02-00", 12, "انکبود", "بقره", "بقره"),
    ("04-08-26-22-00", 68, "انکبود", "بقره", "بقره"),
    ("04-09-03-02-00", 38, "نهر", "نساء", "نساء"),
    ("04-09-03-02-00", 38, "آل امران", "آل عمران", "آل عمران"),
    ("04-08-27-02-00", 73, "بغره", "بقره", "بقره"),
    ("04-08-27-02-00", 13, "محترات", "محرمات", "محرمات"),
    ("04-08-27-22-00", 122, "محترات", "محرمات", "محرمات"),
    ("04-08-05-02-00", 27, "رمضان", "رمضان", "رمضان"),
    ("04-08-27-22-00", 134, "رمضان", "رمضان", "رمضان"),
    ("04-09-03-22-00", 113, "محوصی", "محاصره", "محاصره"),
]
# labels #48/#49 (رمضان) — the labeled file lists original «رمضان» but the
# ASR error is «رمزان»; keep the label file's own original text for scoring
# fidelity and fix the two rows below to the file's actual values.
for i, (st, b, o, e, f) in enumerate(LABELS):
    if (st, b) in (("04-08-05-02-00", 27), ("04-08-27-22-00", 134)):
        LABELS[i] = (st, b, "رمزان", "رمضان", "رمضان")

ZWNJ = "‌"
H2 = "ّ"  # shadda


def _norm_token(t):
    """Normalize a token for matching: strip ZWNJ + shadda so the pass also
    fires on the hamza-variant spellings ASR produces (e.g. صلّی‌الله vs
    صلی الله)."""
    return t.replace(ZWNJ, "").replace(H2, "")


def _norm_text(t):
    return t.replace(ZWNJ, "").replace(H2, "")


def word_present(text, s):
    """Whole-word presence: `s` must not be glued to a Persian letter on
    either side. This is what makes the documented A/B's 23/50 reproducible:
    اردوگا inside اردوگاه does NOT count as the wrong word still being there."""
    return re.search(r"(?<![؀-ۿ])" + re.escape(s) + r"(?![؀-ۿ])", text) is not None


def make_repl(wrong, right):
    """Compile the regex for one replacement. Whole-token match (Persian
    word chars on either side block it). A multi-word entry (with a space)
    matches with flexible whitespace."""
    ws = r"\s*" if " " in wrong else ""
    parts = [re.escape(w) for w in wrong.split(" ")]
    # allow the wrong form with/without ZWNJ+shadda variants: match on the
    # normalized form by building the pattern from normalized tokens but
    # consuming the raw run — simplest robust approach: match the exact
    # string OR its de-ZWNJ/de-shadda shadow via a character class.
    def flex(tok):
        chars = []
        for c in tok:
            if c == ZWNJ:
                chars.append("(" + c + ")?")
            elif c == H2:
                chars.append("(" + c + ")?")
            else:
                chars.append(re.escape(c))
        return "".join(chars)
    pat = (r"(?<!\w)" + ws.join(flex(p) for p in wrong.split(" ")) + r"(?!\w)")
    return re.compile(pat)


def apply_postpass(block_text, lex, ledger):
    """Apply context rules then safe non-word replacements to one block text.
    `ledger` maps wrong-token -> [count, right] (for the replacement audit).
    Returns the new text."""
    t = block_text
    # 1) context rules (wrong real-word -> right, only with cue co-occurrence)
    for rule in lex.get("context_rules", []):
        if any(cue in t for cue in rule["when_block_contains_any"]):
            pat = make_repl(rule["wrong"], rule["right"])
            t, n = pat.subn(rule["right"], t)
            if n:
                ledger.setdefault(rule["wrong"], [0, rule["right"]])[0] += n
    # 2) safe non-word replacements (value None = handled elsewhere / defer).
    # LONGEST-FIRST: e.g. هجت‌الاسلام must fire before its substring هجت,
    # because ZWNJ is not a \w char so a bare-prefix match would corrupt it.
    for wrong, right in sorted(lex.get("safe_nonword", {}).items(),
                               key=lambda kv: -len(kv[0])):
        if right is None:
            continue
        pat = make_repl(wrong, right)
        t, n = pat.subn(right, t)
        if n:
            ledger.setdefault(wrong, [0, right])[0] += n
    return t


def srt_blocks(path):
    """-> list of (index, ts, [text lines])."""
    out = []
    for raw in open(path, encoding="utf-8").read().strip().split("\n\n"):
        ls = [l for l in raw.split("\n") if l.strip() != ""]
        if len(ls) >= 2 and "-->" in ls[1]:
            out.append(ls)
    return out


def block_text(lines):
    return " ".join(l for l in lines[2:] if l.strip()).strip()


def rebuild_srt(blocks):
    return "\n\n".join("\n".join(b) for b in blocks) + "\n"


def score_labels(v2_paths, post_paths):
    """Score the 50 labels the 9B.2.4 way (original gone AND expected
    present). Returns (before_results, after_results) lists of dicts."""
    before, after = [], []
    for (stem, blk, orig, exp, fam) in LABELS:
        vpath = v2_paths[stem]
        ppath = post_paths[stem]
        vb = srt_blocks(vpath)[blk - 1]
        pb = srt_blocks(ppath)[blk - 1]
        assert vb[0] == pb[0] and vb[1] == pb[1], \
            f"structure drift {stem} blk {blk}"
        vt = block_text(vb)
        pt = block_text(pb)
        b = (orig not in vt) and (exp in vt)
        a = (orig not in pt) and (exp in pt)
        # whole-word convention (the one the 9B.2.4 A/B reported under): the
        # wrong form must not appear as a standalone word — so اردوگا inside
        # اردوگاه no longer counts as "still present".
        bw = (not word_present(vt, orig)) and (exp in vt)
        aw = (not word_present(pt, orig)) and (exp in pt)
        before.append({"stem": stem, "blk": blk, "orig": orig,
                       "exp": exp, "fam": fam, "ok": b, "okw": bw, "vtext": vt})
        after.append({"stem": stem, "blk": blk, "orig": orig,
                      "exp": exp, "fam": fam, "ok": a, "okw": aw, "ptext": pt})
    return before, after


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lexicon", default=os.path.join(HERE, "lexicon.json"))
    ap.add_argument("--v2dir", default=os.path.join(DOWNLOADS, "cleaned"),
                    help="dir with the <stem>.correct.v2.srt files to score "
                         "(default: repo downloads/cleaned)")
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(),
                                                  "v2_postpass"))
    ap.add_argument("--diff-dir",
                    default=os.path.join(tempfile.gettempdir(), "v2_postpass",
                                         "diffs"))
    args = ap.parse_args()

    lex = json.load(open(args.lexicon, encoding="utf-8"))
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.diff_dir, exist_ok=True)

    ledger = {}
    protected_hits = {}
    v2_paths, post_paths = {}, {}
    tot_blocks = tot_changed_pp = 0

    for stem in STEMS:
        v2_name = f"radio-maaref-{stem}.correct.v2.srt"
        v2_path = os.path.join(args.v2dir, v2_name)
        if not os.path.exists(v2_path):
            print(f"MISSING v2 input: {v2_path}")
            sys.exit(1)
        post_path = os.path.join(args.out, v2_name)
        blocks = srt_blocks(v2_path)
        # original (for protected-term survival check)
        orig_path = os.path.join(DOWNLOADS, f"radio-maaref-{stem}.srt")
        orig_text = open(orig_path, encoding="utf-8").read()
        v2_full = "\n".join(block_text(b) for b in blocks)
        post_blocks = []
        for b in blocks:
            bt = block_text(b)
            # protected-term survival: count before
            for p in lex.get("protected", []):
                if _norm_token(p) in _norm_text(bt):
                    protected_hits.setdefault(p, 0)
                    protected_hits[p] += bt.count(p)
            nb = apply_postpass(bt, lex, ledger)
            if nb != bt:
                tot_changed_pp += 1
            new_lines = [b[0], b[1]] + ([nb] if nb else [])
            post_blocks.append(new_lines)
        _write(post_path, rebuild_srt(post_blocks))
        v2_paths[stem] = v2_path
        post_paths[stem] = post_path
        tot_blocks += len(blocks)

    before, after = score_labels(v2_paths, post_paths)
    nb, na = sum(r["ok"] for r in before), sum(r["ok"] for r in after)
    nbw, naw = sum(r["okw"] for r in before), sum(r["okw"] for r in after)
    print("=" * 72)
    print(f"post-pass blocks changed: {tot_changed_pp} / {tot_blocks}")
    print("RECALL (strict substring — the rule stated in v2-labeled-errors.md):")
    print(f"    before (tuned v2): {nb}/50    after (+post-pass): {na}/50")
    print("RECALL (whole-word — the 9B.2.4 A/B convention that reported 23/50):")
    print(f"    before (tuned v2): {nbw}/50    after (+post-pass): {naw}/50")
    print("=" * 72)
    print("per-label transitions, strict [before->after] (word-boundary as [w:x>y]):")
    for r1, r2 in zip(before, after):
        mark = ""
        if not r1["ok"] and r2["ok"]:
            mark = "  <== +FIXED by post-pass"
        elif r1["ok"] and not r2["ok"]:
            mark = "  <== !! REGRESSION by post-pass"
        elif not r1["okw"] and r2["okw"]:
            mark = "  <== +FIXED (word-boundary)"
        b1, a1 = 'F' if r1["ok"] else '-', 'F' if r2["ok"] else '-'
        w1, w2 = 'F' if r1["okw"] else '-', 'F' if r2["okw"] else '-'
        print(f"  [{b1}->{a1}] [w:{w1}>{w2}] "
              f"{r1['stem']} blk={r1['blk']:3d} {r1['orig']}->{r1['exp']} "
              f"({r1['fam']}){mark}")

    fams = {}
    for r in after:
        fams.setdefault(r["fam"], [0, 0])
        fams[r["fam"]][1] += 1
        if r["ok"]:
            fams[r["fam"]][0] += 1
    print("\nrecall by family (after post-pass):")
    for f, (ok, tot) in sorted(fams.items(), key=lambda x: -x[1][1]):
        print(f"  {f:12s} {ok}/{tot}")

    print("\nreplacement ledger (wrong -> right [total count]):")
    for w, (n, r) in sorted(ledger.items(), key=lambda x: -x[1][0]):
        print(f"  {n:4d}  {w} -> {r}")

    print("\nprotected terms surviving in v2 output (must stay intact):")
    for p, n in sorted(protected_hits.items(), key=lambda x: -x[1]):
        print(f"  {n:3d}  {p}")

    # regression spot-checks from 9B.2.4:
    print("\nknown 9B.2.4 regression spot-checks:")
    checks = [
        ("04-08-06-02-00", 169, "پرسمان", "پرسبان"),
        ("04-08-13-02-00", 106, "عربه", "عروه"),
        ("04-08-13-02-00", 201, "ریایش", "ریاض"),
    ]
    for stem, blk, good, bad in checks:
        pt = block_text(srt_blocks(post_paths[stem])[blk - 1])
        state = "good" if good in pt else ("BAD" if bad in pt else "other")
        print(f"  {stem} blk={blk} {good} (vs {bad}): {state}   text={pt[:80]}")

    # diffs
    for stem in STEMS:
        v = open(v2_paths[stem], encoding="utf-8").read().splitlines()
        p = open(post_paths[stem], encoding="utf-8").read().splitlines()
        d = list(difflib.unified_diff(v, p,
                                      fromfile=f"v2/{stem}",
                                      tofile=f"postpass/{stem}", n=0))
        if d:
            with open(os.path.join(args.diff_dir, stem + ".diff"), "w",
                      encoding="utf-8") as fh:
                fh.write("\n".join(d) + "\n")
    ndiff = len(os.listdir(args.diff_dir))
    print(f"\nper-file diffs written: {ndiff} files in {args.diff_dir}")
    print(f"post-passed SRTs in {args.out}")


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main()
