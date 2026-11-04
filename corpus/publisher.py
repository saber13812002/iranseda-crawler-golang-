"""Hugging Face publisher — LOCAL PUBLISH BUNDLE ONLY (mission §7).

The production host has no `datasets`/`huggingface_hub` and no HF token
in the environment, so the publisher never uploads. It prepares an
upload-ready bundle and records the exact blocker:

  out_dir/hf/
    README.md               dataset card (private-first wording)
    dataset_info.json       rows, size, features, lineage
    publish_status.json     {"status": "BLOCKED", "reasons": [...]}
    corpus-*.jsonl          (symlinked/copy of the export shards)

Publish steps (documented in README.md, to be executed where a token
exists): create private repo -> push -> verify -> visibility stays
PRIVATE until rights verified (public = BLOCKED — RIGHTS NOT VERIFIED).
"""

import os
import json
import shutil
import datetime

from . import config as _config


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class Publisher(object):
    def __init__(self, cfg, log=print):
        self.cfg = cfg
        self.log = log
        self.hf_dir = os.path.join(cfg.out_dir, "hf")

    # ------------------------------------------------------------------
    def prepare(self, manifest):
        """Build the local publish bundle from a finished export."""
        os.makedirs(self.hf_dir, exist_ok=True)
        manifest_path = os.path.join(self.cfg.out_dir, "manifest.json")
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        stats_path = os.path.join(self.cfg.out_dir, "stats.json")
        stats = {}
        if os.path.exists(stats_path):
            with open(stats_path, encoding="utf-8") as f:
                stats = json.load(f)

        # copy/shard-link the corpus files into the bundle
        data_dir = os.path.join(self.hf_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        copied = []
        for rel in manifest.get("output_files", []):
            base = os.path.basename(rel)
            dst = os.path.join(data_dir, base)
            if not os.path.exists(dst):
                shutil.copy2(rel, dst)
            copied.append("data/" + base)

        size_bytes = sum(os.path.getsize(os.path.join(data_dir, os.path.basename(p)))
                         for p in manifest.get("output_files", []))

        info = {
            "dataset_name": "iranseda-radio-corpus",
            "version": "1.0",
            "license": "rights-not-verified (publish PRIVATE only)",
            "rows": manifest.get("records_written"),
            "bytes": size_bytes,
            "files": copied,
            "generated_at": _now_iso(),
            "lineage": {
                "run_id": manifest.get("run_id"),
                "exported_at": manifest.get("exported_at"),
                "db_counts_at_run": manifest.get("db_counts_at_run"),
            },
            "features": [
                "record_id", "episode_key", "broadcast (jalali + gregorian)",
                "audio.url", "transcripts.originals (srt/txt)",
                "transcripts.llm_outputs (all versions)", "speakers (none yet)",
                "crop", "pipeline_state", "provenance", "quality",
            ],
            "notes": [
                "Original ASR content and every corrected version are preserved separately.",
                "Persian text NFC-normalized; raw values recoverable via *_raw fields.",
                "No server-private paths, no credentials, no prompt text inlined.",
            ],
        }
        _atomic(os.path.join(self.hf_dir, "dataset_info.json"),
                json.dumps(info, indent=2, ensure_ascii=False))

        readme = self._readme(manifest, info)
        _atomic(os.path.join(self.hf_dir, "README.md"), readme)

        # ---- publish status (honest blocker recording) --------------
        reasons = []
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or ""
        try:
            import datasets  # noqa: F401
            have_datasets = True
        except ImportError:
            have_datasets = False
        try:
            import huggingface_hub  # noqa: F401
            have_hub = True
        except ImportError:
            have_hub = False
        if not have_datasets:
            reasons.append("python lib 'datasets' not installed on export host")
        if not have_hub:
            reasons.append("python lib 'huggingface_hub' not installed on export host")
        if not token:
            reasons.append("HF_TOKEN not present in environment (token must be env-only, never committed)")
        reasons.append("rights verification required before public visibility (public = BLOCKED — RIGHTS NOT VERIFIED)")
        status = {
            "status": "BLOCKED" if reasons else "READY",
            "publish_mode": "private-first",
            "blockers": reasons,
            "public_visibility": "BLOCKED — RIGHTS NOT VERIFIED",
            "next_steps": [
                "1. from a host with the libs + HF_TOKEN: huggingface_hub repo create --private",
                "2. upload data/*.jsonl + README.md + dataset_info.json",
                "3. verify row count matches manifest.records_written",
                "4. keep repo PRIVATE until rights are verified",
            ],
            "checked_at": _now_iso(),
        }
        _atomic(os.path.join(self.hf_dir, "publish_status.json"),
                json.dumps(status, indent=2, ensure_ascii=False))
        self.log("publisher: bundle at %s — status %s (%d blockers)"
                 % (self.hf_dir, status["status"], len(reasons)))
        return status

    # ------------------------------------------------------------------
    def _readme(self, manifest, info):
        return """# IranSeda Radio Corpus (v1.0)

A comprehensive, versioned corpus of **all** IranSeda radio episodes
(crawled from `https://radio.iranseda.ir`), including original ASR
transcripts and every LLM-corrected/derived version. Built for semantic
search, RAG, content analysis, and ML training.

## Contents

- `data/corpus*.jsonl` — one JSON object per episode (record).
- `dataset_info.json` — row/size/lineage metadata.
- `publish_status.json` — publish state (private-first policy).

## Fields (per record)

| Field | Meaning |
|-------|---------|
| `record_id` | stable identity: `iranseda:ch{ch}:e{e}` (EPG) or `iranseda:db{pid}:s{sid}` |
| `broadcast` | air date/time — Jalali + derived Gregorian (from canonical filename, never `created_at`) |
| `program` | program registry info (merged legacy+current rows) |
| `audio.url` | absolute audio/EPG URL on the public site |
| `transcripts.originals` | original ASR SRT + TXT (disk-derived, NFC, sha256) |
| `transcripts.llm_outputs[]` | corrected SRT/TXT, bilingual summary, full text, QA — all versions kept |
| `speakers` | currently none (no verified source; empty + reason, never guessed) |
| `crop` | per-session program-boundary crop window |
| `pipeline_state` | download/transcription status |
| `provenance` | DB rows + disk files that contributed |
| `quality` | explicit missing-data list + warnings |

## Normalization

Persian text is NFC-normalized with whitespace collapsed; zero-width
non-joiners (U+200C) are preserved. Original DB values are kept in
`*_raw` fields.

## Rights & visibility

**This repository MUST stay private until broadcast rights are
verified.** Public publication is blocked by policy
(BLOCKED — RIGHTS NOT VERIFIED).

## Lineage

- Run: `{run_id}` ({exported_at})
- Records: {rows}
- Source: IranSeda production DB (read-only) + pipeline artifact files
""".format(
            run_id=info["lineage"]["run_id"],
            exported_at=info["lineage"]["exported_at"],
            rows=info["rows"],
        )


def _atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(data)
    os.replace(tmp, path)
