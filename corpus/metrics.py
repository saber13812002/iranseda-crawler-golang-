"""Corpus metrics (mission §9) — 11 iranseda_corpus_* gauges/counters.

Computed from manifest.json + stats.json after each run and written as
Prometheus text format (data/corpus/metrics.prom) for the Grafana
pipeline dashboard. Server 52 (Grafana) is down, so deployment of the
dashboard panel stays BLOCKED — the text file is still written and is
scrape-ready.
"""

import os
import json
import datetime


METRIC_NAMES = (
    "iranseda_corpus_records_total",
    "iranseda_corpus_records_complete",
    "iranseda_corpus_records_with_broadcast",
    "iranseda_corpus_records_with_original_srt",
    "iranseda_corpus_records_with_original_txt",
    "iranseda_corpus_records_with_corrected_srt",
    "iranseda_corpus_records_with_corrected_txt",
    "iranseda_corpus_records_with_summary",
    "iranseda_corpus_records_with_full_text",
    "iranseda_corpus_export_duration_seconds",
    "iranseda_corpus_last_success_timestamp",
)


def _now_ts():
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp())


def compute(cfg, manifest=None):
    """Read manifest+stats and return {metric: value}."""
    out = {m: None for m in METRIC_NAMES}
    mp = os.path.join(cfg.out_dir, "manifest.json")
    sp = os.path.join(cfg.out_dir, "stats.json")
    if not os.path.exists(mp):
        return out
    with open(mp, encoding="utf-8") as f:
        manifest = json.load(f)
    stats = {}
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as f:
            stats = json.load(f)

    out["iranseda_corpus_records_total"] = manifest.get("records_written")
    out["iranseda_corpus_records_complete"] = stats.get("records_complete")
    out["iranseda_corpus_records_with_broadcast"] = stats.get("records_with_broadcast")
    out["iranseda_corpus_records_with_original_srt"] = stats.get("records_with_original_srt")
    out["iranseda_corpus_records_with_original_txt"] = stats.get("records_with_original_txt")
    out["iranseda_corpus_records_with_corrected_srt"] = stats.get("records_with_corrected_srt")
    out["iranseda_corpus_records_with_corrected_txt"] = stats.get("records_with_corrected_txt")
    out["iranseda_corpus_records_with_summary"] = stats.get("records_with_summary")
    out["iranseda_corpus_records_with_full_text"] = stats.get("records_with_full_text")
    out["iranseda_corpus_export_duration_seconds"] = manifest.get("duration_sec")
    out["iranseda_corpus_last_success_timestamp"] = _now_ts()
    return out


def write_prometheus(cfg, values=None):
    if values is None:
        values = compute(cfg)
    lines = ["# IranSeda corpus exporter metrics (see docs/CORPUS_OPERATIONS.md)"]
    for name in METRIC_NAMES:
        v = values.get(name)
        if v is None:
            continue
        lines.append("# HELP %s see docs" % name)
        lines.append("# TYPE %s gauge" % name)
        lines.append("%s %s" % (name, v if isinstance(v, (int, float)) else 1))
    path = os.path.join(cfg.out_dir, "metrics.prom")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, path)
    return path
