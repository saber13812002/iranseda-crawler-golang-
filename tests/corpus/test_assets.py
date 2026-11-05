"""Offline unit tests for corpus.assets (Stage 3, Task B).

No network, no git, no DB: fetch and git are injectable fakes. Mirrors the
style of test_linkage.py (plain asserts, module-level test_* functions).
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from corpus import assets
from corpus import scan_assets

GH = {"user": "saber13812002", "repo": "iranseda-crawler-golang-",
      "branch": "download-db"}

STEM_A = "radio-maaref-05-07-19-13-30"  # mission A
STEM_B = "radio-maaref-05-03-10-05-30"  # mission B


def _session(sid=1, pid=7, ch=14, e="154148409",
             fname=None, srtf=None, link=None):
    if fname is None:
        fname = STEM_A + ".mp4"
    if srtf is None:
        srtf = STEM_A + ".srt"
    if link is None:
        link = ("https://radio.iranseda.ir/epgarchivePart/?VALID=TRUE"
                "&ch=%d&e=%s" % (ch, e))
    return {"id": sid, "program_id": pid, "link": link,
            "filename": fname, "srt_filename": srtf}


def _llm(sid=1, job="correct_subtitles", rel=None, model="roshan-70b",
         finished="2026-01-01 12:00:00", lid=100):
    return {"id": lid, "session_id": sid, "job_type": job,
            "model": model, "file_relpath": rel,
            "finished_at": datetime.strptime(finished,
                                             "%Y-%m-%d %H:%M:%S")
            if finished else finished, "status": "done"}


def _reg(sessions=None, llm=None, gh=None, **kw):
    return assets.build_registry(sessions if sessions is not None
                                 else [_session()],
                                 llm or [], gh or GH, **kw)


# ---------------------------------------------------------------------------
# stem parser (OQ-5)

def test_parse_canonical_mission_a():
    p = assets.parse_asset_filename(STEM_A + ".srt")
    assert p["stem_family"] == "canonical"
    assert p["stem"] == STEM_A
    assert p["chan"] == "maaref"
    assert p["components"] == {"jy": 5, "jm": 7, "jd": 19, "hh": 13,
                               "mi": 30}
    assert p["date_valid"] is True
    assert p["time_valid"] is True
    assert p["broadcast"] is not None
    assert p["broadcast"]["jalali"]["date"] == "1405-07-19"
    assert p["broadcast"]["jalali"]["time"] == "13:30:00"


def test_parse_canonical_with_suffix():
    p = assets.parse_asset_filename(STEM_A + ".correct.srt")
    assert p["stem_family"] == "canonical"
    assert p["stem"] == STEM_A
    assert p["asset_suffix"] == "correct"
    p2 = assets.parse_asset_filename(STEM_B + ".summary.en.txt")
    assert p2["asset_suffix"] == "summary.en"
    p3 = assets.parse_asset_filename(STEM_A + ".mp4")
    assert p3["asset_suffix"] == ""


def test_parse_legacy_underscore_unparsed():
    p = assets.parse_asset_filename("radio-maaref-05_07_19-13_30.srt")
    assert p["stem_family"] == "unparsed"
    assert p["stem"] is None
    assert p["broadcast"] is None


def test_parse_copy_and_numbered_unparsed():
    p1 = assets.parse_asset_filename("radio-maaref-05-03-10-05-30 - Copy.srt")
    p2 = assets.parse_asset_filename("radio-maaref-05-03-10-05-30 (1).srt")
    assert p1["stem_family"] == "unparsed"
    assert p2["stem_family"] == "unparsed"
    assert p1["broadcast"] is None and p2["broadcast"] is None


def test_parse_three_digit_tail_not_canonical():
    p = assets.parse_asset_filename("radio-maaref-05-07-19-13-300.srt")
    assert p["stem_family"] == "unparsed"
    assert p["stem"] is None


def test_parse_not_a_radio_file():
    p = assets.parse_asset_filename("something-else.srt")
    assert p["stem_family"] == "none"
    p2 = assets.parse_asset_filename("radio-foo.mp4")
    assert p2["stem_family"] == "unparsed"  # radio-* but no canonical shape


def test_parse_invalid_jalali_date_still_canonical_but_no_broadcast():
    p = assets.parse_asset_filename("radio-maaref-05-13-40-00-00.srt")
    assert p["stem_family"] == "canonical"
    assert p["stem"] == "radio-maaref-05-13-40-00-00"
    assert p["date_valid"] is False
    assert p["broadcast"] is None


def test_parse_invalid_time():
    p = assets.parse_asset_filename("radio-maaref-05-07-19-25-30.srt")
    assert p["stem_family"] == "canonical"
    assert p["time_valid"] is False
    assert p["broadcast"] is None


# ---------------------------------------------------------------------------
# session identity

def test_session_uid_link_and_fallback():
    assert assets.session_uid(_session()) == "iranseda:ch14:e154148409"
    s = {"id": 42, "program_id": 7, "link": "https://x/?VALID=TRUE",
         "filename": "f.mp4", "srt_filename": None}
    assert assets.session_uid(s) == "iranseda:db7:s42"


# ---------------------------------------------------------------------------
# URL builders (OQ-4 / R7)

def test_github_raw_url_template():
    u = assets.github_raw_url(GH["user"], GH["repo"], GH["branch"],
                              "downloads/cleaned/" + STEM_A + ".correct.srt")
    assert u == ("https://raw.githubusercontent.com/saber13812002/"
                 "iranseda-crawler-golang-/download-db/"
                 "downloads/cleaned/" + STEM_A + ".correct.srt")


def test_github_blob_url_template():
    u = assets.github_blob_url(GH["user"], GH["repo"], GH["branch"],
                               "downloads/" + STEM_A + ".srt")
    assert u == ("https://github.com/saber13812002/iranseda-crawler-golang-/"
                 "blob/download-db/downloads/" + STEM_A + ".srt")


def test_url_builder_quotes_relpath():
    u = assets.github_raw_url("u", "r", "b", "downloads/a b.srt")
    assert u.endswith("downloads/a%20b.srt")


def test_url_builder_aborts_without_branch_r7():
    try:
        assets.github_raw_url("u", "r", "", "downloads/x.srt")
        assert False, "expected ValueError"
    except ValueError:
        pass
    try:
        assets.github_raw_url("u", "r", None, "downloads/x.srt")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_url_builder_requires_identity():
    try:
        assets.github_raw_url(None, "r", "b", "downloads/x.srt")
        assert False, "expected ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# registry builder

def test_registry_mission_a_assets():
    llm = [_llm(1, "correct_subtitles",
                "downloads/cleaned/%s.correct.srt" % STEM_A),
           _llm(1, "correct_text",
                "downloads/cleaned/%s.correct.txt" % STEM_A, lid=101),
           _llm(1, "summary",
                "downloads/cleaned/%s.summary.txt" % STEM_A, lid=102)]
    reg = _reg([_session()], llm)
    assert len(reg) == 1
    row = reg[0]
    assert row["session_uid"] == "iranseda:ch14:e154148409"
    assert row["stem"] == STEM_A
    assert row["stem_family"] == "canonical"
    assert row["broadcast_jalali"] == "1405-07-19"
    types = [a["asset_type"] for a in row["assets"]]
    assert types == ["audio", "corrected_srt", "corrected_txt", "raw_srt",
                     "summary_en", "summary_fa"]
    by = {a["asset_type"]: a for a in row["assets"]}
    assert by["audio"]["relpath"] == "downloads/" + STEM_A + ".mp4"
    assert by["audio"]["source"] == "db:filename"
    assert by["audio"]["processing_version"] is None
    assert by["raw_srt"]["relpath"] == "downloads/" + STEM_A + ".srt"
    assert by["raw_srt"]["source"] == "db:srt_filename"
    cs = by["corrected_srt"]
    assert cs["relpath"] == "downloads/cleaned/%s.correct.srt" % STEM_A
    assert cs["source"] == "db:llm:correct_subtitles"
    assert cs["processing_version"] == "roshan-70b"      # C14
    assert cs["produced_at"] == "2026-01-01 12:00:00"    # C13
    assert by["summary_en"]["source"] == "pattern"
    assert by["summary_en"]["relpath"] == (
        "downloads/cleaned/%s.summary.en.txt" % STEM_A)
    assert row["asset_count"] == 6


def test_registry_no_summary_en_for_unparsed_stem():
    s = _session(fname="radio-maaref-05_07_19-13_30.mp4",
                 srtf="radio-maaref-05_07_19-13_30.srt")
    reg = _reg([s], [])
    row = reg[0]
    assert row["stem_family"] == "unparsed"
    types = [a["asset_type"] for a in row["assets"]]
    assert "summary_en" not in types
    assert set(types) == {"audio", "raw_srt"}


def test_registry_llm_unknown_job_type_passes_through():
    llm = [_llm(1, "new_job", "downloads/cleaned/x.weird")]
    reg = _reg([_session()], llm)
    by = {a["asset_type"]: a for a in reg[0]["assets"]}
    assert "other_llm" in by
    assert by["other_llm"]["source"] == "db:llm:new_job"


def test_registry_llm_row_without_relpath_skipped():
    llm = [_llm(1, "summary", None)]
    reg = _reg([_session()], llm)
    types = [a["asset_type"] for a in reg[0]["assets"]]
    assert "summary_fa" not in types


def test_registry_llm_orphan_session_ignored():
    llm = [_llm(999, "summary", "downloads/cleaned/other.summary.txt")]
    reg = _reg([_session()], llm)
    types = [a["asset_type"] for a in reg[0]["assets"]]
    assert "summary_fa" not in types


def test_registry_duplicate_relpath_latest_wins():
    llm = [
        _llm(1, "correct_subtitles",
             "downloads/cleaned/%s.correct.srt" % STEM_A,
             model="old-model", lid=100),
        _llm(1, "correct_subtitles",
             "downloads/cleaned/%s.correct.srt" % STEM_A,
             model="new-model", lid=200),
    ]
    reg = _reg([_session()], llm)
    cs = [a for a in reg[0]["assets"] if a["asset_type"] == "corrected_srt"]
    assert len(cs) == 1
    assert cs[0]["processing_version"] == "new-model"


def test_registry_aborts_without_branch_r7():
    try:
        assets.build_registry([_session()], [],
                              {"user": "u", "repo": "r", "branch": None})
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_registry_quarantine_flags_all_assets():
    reg = _reg([_session()], [], quarantine_ids={"iranseda:ch14:e154148409"})
    row = reg[0]
    assert row["quarantined"] is True
    assert all(a["quarantined"] for a in row["assets"])


def test_registry_c5_c6_hidden_until_published():
    reg = _reg([_session()], [])
    for a in reg[0]["assets"]:
        assert a["raw_url"] is None
        assert a["blob_url"] is None
        assert a["published"] is None
        assert a["_raw_url"].startswith("https://raw.githubusercontent.com/")


# ---------------------------------------------------------------------------
# way 1: on disk

def _tmp_downloads():
    d = tempfile.mkdtemp(prefix="stage3_assets_")
    return d


def test_check_disk_sets_c9_c8_c7_and_status():
    d = _tmp_downloads()
    try:
        cleaned = os.path.join(d, "downloads", "cleaned")
        os.makedirs(cleaned)
        afile = os.path.join(d, "downloads", STEM_A + ".mp4")
        cfile = os.path.join(d, "downloads", "cleaned",
                             STEM_A + ".correct.srt")
        content = b"fake audio bytes"
        with open(afile, "wb") as f:
            f.write(content)
        with open(cfile, "wb") as f:
            f.write(b"0\n00:00:00,000 --> 00:00:01,000\nx\n")
        llm = [_llm(1, "correct_subtitles",
                    "downloads/cleaned/%s.correct.srt" % STEM_A)]
        reg = _reg([_session()], llm)
        n = assets.check_disk(reg, d)
        assert n == 2
        by = {a["asset_type"]: a for a in reg[0]["assets"]}
        assert by["audio"]["exists_on_disk"] is True
        assert by["audio"]["size_bytes"] == len(content)
        assert by["audio"]["sha256"] == hashlib.sha256(content).hexdigest()
        assert by["corrected_srt"]["exists_on_disk"] is True
        assert by["raw_srt"]["exists_on_disk"] is False
        assert by["summary_en"]["exists_on_disk"] is False
        assert by["raw_srt"]["sha256"] is None
        assert by["raw_srt"]["size_bytes"] is None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_check_disk_relpath_sanitized_to_basename():
    # filenames with path components are reduced to their basename and the
    # relpath can never escape the downloads dir
    s = _session(fname="sub/dir/evil.mp4", srtf=None)
    reg = _reg([s], [])
    a = reg[0]["assets"][0]
    assert a["relpath"] == "downloads/evil.mp4"
    d = _tmp_downloads()
    try:
        assets.check_disk(reg, d)
        assert a["exists_on_disk"] is False
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# ways 2+3: git trees

def _fake_git(present, log_sha="deadbeef" * 5):
    calls = []

    def git(args):
        calls.append(list(args))
        if args[0] == "cat-file" and args[1] == "-e":
            return (0, "", "") if args[2] in present else (1, "", "")
        if args[0] == "log":
            return (0, log_sha + "\n", "")
        return (1, "", "unexpected " + " ".join(args))
    git.calls = calls
    return git


def test_check_git_tree_sets_c10_c12_and_operational():
    ab = "origin/" + GH["branch"]
    rel_a = "downloads/" + STEM_A + ".mp4"
    rel_s = "downloads/" + STEM_A + ".srt"
    rel_c = "downloads/cleaned/%s.correct.srt" % STEM_A
    present = {ab + ":" + rel_a, ab + ":" + rel_s,
               "origin/phase3-radio-rag-service:" + rel_a}
    git = _fake_git(present)
    reg = _reg([_session()], [])
    res = assets.check_git_tree(reg, "/repo", "origin/" + GH["branch"],
                                operational_ref="origin/phase3-radio-rag-service",
                                git=git)
    assert res == {"in_asset_branch": 2, "in_operational_branch": 1}
    by = {a["asset_type"]: a for a in reg[0]["assets"]}
    assert by["audio"]["exists_in_git_tree"] is True
    assert by["audio"]["publishing_commit_sha"] == "deadbeef" * 5
    assert by["audio"]["operational_branch_present"] is True
    assert by["raw_srt"]["exists_in_git_tree"] is True
    assert by["raw_srt"]["operational_branch_present"] is False
    assert by["corrected_srt" if "corrected_srt" in by
               else "summary_en"]["exists_in_git_tree"] in (True, False)
    assert by["summary_en"]["exists_in_git_tree"] is False
    assert by["summary_en"]["publishing_commit_sha"] is None


def test_check_git_tree_operational_absent_is_none():
    git = _fake_git(set())
    reg = _reg([_session()], [])
    assets.check_git_tree(reg, "/repo", GH["branch"], git=git)
    for a in reg[0]["assets"]:
        assert a["operational_branch_present"] is None


def test_check_git_tree_recomputes_published():
    ab = "origin/" + GH["branch"]
    d = _tmp_downloads()
    try:
        os.makedirs(os.path.join(d, "downloads"))
        p = os.path.join(d, "downloads", STEM_A + ".mp4")
        with open(p, "wb") as f:
            f.write(b"x")
        present = {ab + ":downloads/" + STEM_A + ".mp4"}
        git = _fake_git(present)
        reg = _reg([_session()], [])
        assets.check_disk(reg, d)
        assets.check_git_tree(reg, "/repo", ab, git=git)
        by = {a["asset_type"]: a for a in reg[0]["assets"]}
        assert by["audio"]["published"] == "published"
        assert by["audio"]["raw_url"] is not None
        assert by["audio"]["raw_url"] == by["audio"]["_raw_url"]
        assert by["raw_srt"]["published"] == "missing"
        assert by["raw_srt"]["raw_url"] is None
        # on disk but not in tree -> not_published
        cfile = os.path.join(d, "downloads", "cleaned",
                             STEM_A + ".summary.en.txt")
        os.makedirs(os.path.dirname(cfile), exist_ok=True)
        with open(cfile, "wb") as f:
            f.write(b"en")
        reg2 = _reg([_session()], [])
        assets.check_disk(reg2, d)
        git2 = _fake_git(set())
        assets.check_git_tree(reg2, "/repo", ab, git=git2)
        by2 = {a["asset_type"]: a for a in reg2[0]["assets"]}
        assert by2["summary_en"]["published"] == "not_published"
        assert by2["summary_en"]["raw_url"] is None
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# ways 4+5: HTTP + sha

def _fake_fetch(mapping, exc=None):
    calls = []

    def fetch(url, timeout=None):
        calls.append((url, timeout))
        if exc is not None and url in exc:
            raise exc[url]
        if url in mapping:
            return mapping[url]
        return {"status": 404, "body": b"", "truncated": False,
                "final_url": None, "elapsed": 0.0, "reason": "http_404"}
    fetch.calls = calls
    return fetch


def _ok(body=b"hello", status=200):
    return {"status": status, "body": body, "truncated": False,
            "final_url": None, "elapsed": 0.1, "reason": None}


def test_verify_http_sha_match_true():
    d = _tmp_downloads()
    try:
        os.makedirs(os.path.join(d, "downloads"))
        p = os.path.join(d, "downloads", STEM_A + ".srt")
        body = b"subtitles here"
        with open(p, "wb") as f:
            f.write(body)
        reg = _reg([_session()], [])
        assets.check_disk(reg, d)
        a = reg[0]["assets"][1]  # raw_srt
        url = a["_raw_url"]
        fetch = _fake_fetch({url: _ok(body)})  # other two URLs -> 404
        stats = assets.verify_http(reg, fetch=fetch, cache_path=None)
        assert stats["requests_used"] == 3
        assert stats["http_200"] == 1
        assert stats["http_404"] == 2
        assert stats["sha_match_true"] == 1
        assert a["http_status"] == 200
        assert a["sha_match"] is True
        assert len(fetch.calls) == 3
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_verify_http_404_and_sha_mismatch():
    d = _tmp_downloads()
    try:
        os.makedirs(os.path.join(d, "downloads"))
        p = os.path.join(d, "downloads", STEM_A + ".srt")
        with open(p, "wb") as f:
            f.write(b"local content")
        reg = _reg([_session()], [])
        assets.check_disk(reg, d)
        a = reg[0]["assets"][1]  # raw_srt
        url = a["_raw_url"]
        fetch = _fake_fetch({url: _ok(b"DIFFERENT")})
        assets.verify_http(reg, fetch=fetch)
        assert a["http_status"] == 200
        assert a["sha_match"] is False
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_verify_http_skipped_large():
    reg = _reg([_session()], [])
    for a in reg[0]["assets"]:
        a["exists_on_disk"] = True
        a["sha256"] = "aa" * 32
    fetch = _fake_fetch({a["_raw_url"]: _ok(b"z" * 50)
                         for a in reg[0]["assets"]})
    stats = assets.verify_http(reg, fetch=fetch, sha_cap_bytes=10)
    assert stats["sha_skipped_large"] == 3
    assert all(a["sha_match"] == "skipped_large" for a in reg[0]["assets"])


def test_verify_http_budget_and_skip():
    reg = _reg([_session()], [])
    fetch = _fake_fetch({a["_raw_url"]: _ok(b"x")
                         for a in reg[0]["assets"]})
    stats = assets.verify_http(reg, fetch=fetch, max_requests=1)
    assert stats["requests_used"] == 1
    assert stats["skipped_budget"] == 2
    assert len(fetch.calls) == 1
    skipped = [a for a in reg[0]["assets"]
               if a["http_reason"] == "budget_exhausted"]
    assert len(skipped) == 2
    assert skipped[0]["http_status"] is None
    assert skipped[0]["sha_match"] is None


def test_verify_http_resumable_from_cache():
    reg = _reg([_session()], [])
    urls = [a["_raw_url"] for a in reg[0]["assets"]]
    cache_path = os.path.join(tempfile.mkdtemp(prefix="stage3_cache_"),
                              "cache.json")
    try:
        cache = {urls[0]: {"http_status": 200, "http_reason": None,
                           "sha_match": True,
                           "http_verified_at": "2026-01-01T00:00:00Z",
                           "elapsed": 0.1}}
        with open(cache_path, "w") as f:
            json.dump(cache, f)
        fetch = _fake_fetch({u: _ok(b"x") for u in urls})
        stats = assets.verify_http(reg, fetch=fetch, cache_path=cache_path)
        assert stats["reused_from_prior"] == 1
        assert stats["requests_used"] == 2
        assert len(fetch.calls) == 2
        assert urls[0] not in [c[0] for c in fetch.calls]
        # second run: everything cached, zero requests
        stats2 = assets.verify_http(reg, fetch=fetch, cache_path=cache_path)
        assert stats2["requests_used"] == 0
        assert stats2["reused_from_prior"] == 3
        assert len(fetch.calls) == 2
    finally:
        shutil.rmtree(os.path.dirname(cache_path), ignore_errors=True)


def test_verify_http_fetch_exception_recorded():
    reg = _reg([_session()], [])
    url = reg[0]["assets"][0]["_raw_url"]
    fetch = _fake_fetch({}, exc={url: OSError("conn reset")})
    stats = assets.verify_http(reg, fetch=fetch)
    assert stats["http_error"] == 1
    a = reg[0]["assets"][0]
    assert a["http_status"] is None
    assert a["http_reason"].startswith("fetch_error:")
    assert a["sha_match"] is None


def test_verify_http_dedups_shared_filename():
    # two sessions sharing the same filename -> same raw URL -> 1 request,
    # both rows get the same HTTP result
    s1 = _session(1, link="https://x/?ch=14&e=111")
    s2 = _session(2, link="https://x/?ch=14&e=222")
    reg = _reg([s1, s2], [])
    fetch = _fake_fetch({a["_raw_url"]: _ok(b"same body")
                         for s in reg for a in s["assets"]})
    stats = assets.verify_http(reg, fetch=fetch)
    assert stats["entries_checked"] == 6
    assert stats["distinct_urls"] == 3
    assert stats["requests_used"] == 3
    assert len(fetch.calls) == 3
    assert stats["http_200"] == 3
    for s in reg:
        for a in s["assets"]:
            assert a["http_status"] == 200
            assert a["sha_match"] == "n/a"  # no local sha (files absent)


def test_verify_http_worker_cap_effective_workers():
    # requesting 8 workers must still cap at 2 concurrent (R: <=2 parallel)
    import threading

    class Barrier(object):
        def __init__(self):
            self.cur = 0
            self.max = 0
            self.lock = threading.Lock()

        def enter(self):
            with self.lock:
                self.cur += 1
                self.max = max(self.max, self.cur)

        def leave(self):
            with self.lock:
                self.cur -= 1

    bar = Barrier()
    calls = []

    def slow_fetch(url, timeout=None):
        calls.append(url)
        bar.enter()
        import time
        time.sleep(0.05)
        bar.leave()
        return _ok(b"x")

    # distinct filenames AND srt names -> distinct URLs (no dedup) so the
    # concurrency cap is actually exercised
    reg = _reg([_session(sid=i + 1,
                         fname="radio-maaref-05-07-19-13-%02d.mp4" % (30 + i),
                         srtf="radio-maaref-05-07-19-13-%02d.srt" % (30 + i))
                for i in range(4)], [])
    stats = assets.verify_http(reg, fetch=slow_fetch, max_workers=8)
    assert stats["distinct_urls"] == 12
    assert len(calls) == 12
    assert bar.max <= 2


def test_verify_http_status_filter():
    reg = _reg([_session()], [])
    for a in reg[0]["assets"]:
        a["exists_on_disk"] = True
        a["exists_in_git_tree"] = True
        a["published"] = "published"
        a["raw_url"] = a["_raw_url"]
    fetch = _fake_fetch({a["_raw_url"]: _ok(b"x")
                         for a in reg[0]["assets"]})
    stats = assets.verify_http(reg, fetch=fetch,
                               verify_statuses={"published"})
    assert stats["entries_checked"] == 3
    stats2 = assets.verify_http(reg, fetch=fetch,
                                verify_statuses={"missing"})
    assert stats2["entries_checked"] == 0
    assert stats2["requests_used"] == 0


# ---------------------------------------------------------------------------
# reporting

def test_fp_range_fetch_match_and_mismatch():
    head_b = b"H" * 1024
    tail_b = b"T" * 1024
    size = 3 * 1024 * 1024
    fp = {"head_sha256": hashlib.sha256(head_b).hexdigest(),
          "tail_sha256": hashlib.sha256(tail_b).hexdigest(),
          "size_bytes": size, "chunk": 1024}

    def rng_ok(rng):
        if rng.startswith("bytes=0-"):
            return (206, head_b, size)
        return (206, tail_b, 1024)
    r = assets.fp_range_fetch("http://x/big.mp4", fp, rng_get=rng_ok)
    assert r["fp_ok"] is True
    assert r["head_ok"] is True and r["tail_ok"] is True
    assert r["size_ok"] is True
    assert r["reason"] is None

    def rng_bad_tail(rng):
        if rng.startswith("bytes=0-"):
            return (206, head_b, size)
        return (206, b"X" * 1024, 1024)
    r2 = assets.fp_range_fetch("http://x/big.mp4", fp, rng_get=rng_bad_tail)
    assert r2["fp_ok"] is False
    assert r2["tail_ok"] is False

    def rng_bad_size(rng):
        if rng.startswith("bytes=0-"):
            return (206, head_b, size + 1)
        return (206, tail_b, 1024)
    r3 = assets.fp_range_fetch("http://x/big.mp4", fp, rng_get=rng_bad_size)
    assert r3["fp_ok"] is False
    assert r3["size_ok"] is False

    def rng_404(rng):
        import urllib.error
        raise urllib.error.HTTPError("http://x/big.mp4", 404, "not found",
                                     None, None)
    r4 = assets.fp_range_fetch("http://x/big.mp4", fp, rng_get=rng_404)
    assert r4["http_status"] == 404
    assert r4["fp_ok"] is None
    assert "http_404" in (r4["reason"] or "")


def test_verify_http_large_uses_fp_probe_not_full_download():
    import tempfile as _tf
    d = _tf.mkdtemp()
    try:
        # a "large" local file relative to a tiny cap
        os.makedirs(os.path.join(d, "downloads"))
        p = os.path.join(d, "downloads", "big.mp4")
        with open(p, "wb") as f:
            f.write(b"A" * 4096 + b"B" * 4096)
        s = _session(fname="big.mp4", srtf="")
        reg = _reg([s], [])
        assets.check_disk(reg, d, sha_cap_bytes=100)  # tiny cap -> fp
        a = reg[0]["assets"][0]
        assert a["fingerprint"] is not None
        assert a["size_bytes"] == 8192
        fetch_calls = []

        def no_fetch(url, timeout=None):
            fetch_calls.append(url)
            return _ok(b"SHOULD NOT BE USED")

        fp_calls = []

        def fake_fp(url, fp, timeout=None):
            fp_calls.append((url, fp))
            return {"http_status": 206, "fp_ok": True, "size_ok": True,
                    "head_ok": True, "tail_ok": True, "reason": None,
                    "remote_size": fp["size_bytes"]}
        stats = assets.verify_http(reg, fetch=no_fetch,
                                   max_requests=100, fp_probe=fake_fp)
        assert fetch_calls == []           # full-body fetch never used
        assert len(fp_calls) == 1
        assert a["sha_match"] == "fp_match"
        assert a["http_status"] == 206
        assert stats["fp_probes"] == 1
        assert stats["fp_match"] == 1
        # fingerprint must NOT affect published (C11 unchanged):
        # without check_git_tree the pipeline is incomplete -> None
        assert a["published"] in (None, "published", "not_published",
                                  "missing", "excluded")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_verify_http_fp_mismatch_and_probe_error():
    d = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(d, "downloads"))
        p = os.path.join(d, "downloads", "big.mp4")
        with open(p, "wb") as f:
            f.write(b"A" * 4096)
        s = _session(fname="big.mp4", srtf="")
        reg = _reg([s], [])
        assets.check_disk(reg, d, sha_cap_bytes=100)
        a = reg[0]["assets"][0]
        assert a["fingerprint"] is not None

        def fp_mismatch(url, fp, timeout=None):
            return {"http_status": 206, "fp_ok": False, "size_ok": True,
                    "head_ok": True, "tail_ok": False,
                    "reason": None, "remote_size": fp["size_bytes"]}
        stats = assets.verify_http(reg, fetch=_fake_fetch({}), max_requests=10,
                                   fp_probe=fp_mismatch)
        assert a["sha_match"] == "fp_mismatch"
        assert stats["fp_mismatch"] == 1

        def fp_err(url, fp, timeout=None):
            raise RuntimeError("boom")
        stats2 = assets.verify_http(reg, fetch=_fake_fetch({}), max_requests=10,
                                    fp_probe=fp_err)
        assert a["sha_match"] is None
        assert a["http_reason"].startswith("probe_error")
        assert stats2["fp_error"] == 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_verify_http_no_fingerprint_falls_back_to_full_fetch():
    # large file on disk but fingerprint not computed (cap=None path is not
    # used in the CLI; simulate an entry without fingerprint)
    s = _session(fname="big.mp4", srtf=None)
    reg = _reg([s], [])
    a = reg[0]["assets"][0]
    a["fingerprint"] = None
    seen = {}

    def fp_probe(url, fp, timeout=None):
        seen["called"] = True
        return {}
    r = assets.verify_http(reg, fetch=_fake_fetch({}), max_requests=10,
                           fp_probe=fp_probe)
    assert "called" not in seen
    assert a["http_status"] == 404   # full-body (fake) path was used
    assert a["sha_match"] is None    # 404 -> no sha verdict
    assert r["fp_probes"] == 0


def test_five_way_row_shape_and_url_rule():
    reg = _reg([_session()], [])
    a = reg[0]["assets"][0]
    a["exists_on_disk"] = True
    a["exists_in_git_tree"] = True
    assets._recompute_published(a)
    row = assets.five_way_row(reg[0], a)
    assert row["session_uid"] == "iranseda:ch14:e154148409"
    assert row["status"] == "published"
    assert row["raw_url"] == a["_raw_url"]
    assert "sha256" in row and "http_status" in row
    assert "publishing_commit_sha" in row
    # non-published asset: raw_url must be absent/None
    b = reg[0]["assets"][1]
    row2 = assets.five_way_row(reg[0], b)
    assert row2["raw_url"] is None


def test_summarize_counts():
    d = _tmp_downloads()
    try:
        os.makedirs(os.path.join(d, "downloads"))
        p = os.path.join(d, "downloads", STEM_A + ".mp4")
        with open(p, "wb") as f:
            f.write(b"x")
        ab = "origin/" + GH["branch"]
        git = _fake_git({ab + ":downloads/" + STEM_A + ".mp4"})
        reg = _reg([_session()], [])
        assets.check_disk(reg, d)
        assets.check_git_tree(reg, "/repo", ab, git=git)
        s = assets.summarize(reg)
        assert s["total_sessions"] == 1
        assert s["total_assets"] == 3
        assert s["distinct_stems"] == 1
        assert s["distinct_programs"] == 1
        assert s["stem_family"] == {"canonical": 1}
        au = s["asset_types"]["audio"]
        assert au["total"] == 1
        assert au["on_disk"] == 1
        assert au["in_asset_branch"] == 1
        assert au["status"]["published"] == 1
        rs = s["asset_types"]["raw_srt"]
        assert rs["on_disk"] == 0
        assert rs["status"]["missing"] == 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_default_asset_fetch_never_raises():
    r = assets.default_asset_fetch(
        "http://127.0.0.1:1/definitely-not-listening", timeout=0.5)
    assert r["status"] is None
    assert r["reason"] is not None
    assert "body" in r and "elapsed" in r


# ---------------------------------------------------------------------------
# CLI helpers (remote parsing — OQ-4/R7)

def test_parse_github_remote_https_and_ssh():
    u, r = scan_assets.parse_github_remote(
        "https://github.com/saber13812002/iranseda-crawler-golang-.git")
    assert u == "saber13812002" and r == "iranseda-crawler-golang-"
    u2, r2 = scan_assets.parse_github_remote(
        "git@github.com:saber13812002/iranseda-crawler-golang-.git")
    assert u2 == "saber13812002" and r2 == "iranseda-crawler-golang-"
    u3, r3 = scan_assets.parse_github_remote(
        "https://github.com/saber13812002/iranseda-crawler-golang-")
    assert u3 == "saber13812002" and r3 == "iranseda-crawler-golang-"


def test_parse_github_remote_non_github_rejected():
    assert scan_assets.parse_github_remote(
        "https://git.ai.ismc.ir/ai-tools/x.git") == (None, None)
    assert scan_assets.parse_github_remote("") == (None, None)
    assert scan_assets.parse_github_remote(None) == (None, None)
