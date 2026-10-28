"""
test_episode_canon.py — regression tests for the episode-URL canonicalization
and the dedup behavior that depends on it (Task A, STEP 2).

Covers, exactly as required:
  * relative URLs            ("../epgarchivePart/?VALID=TRUE&ch=14&e=100")
  * absolute URLs            ("https://radio.iranseda.ir/epgarchivePart/?VALID=TRUE&ch=14&e=100")
  * trailing slashes         ("...epgarchivePart/?ch=14&e=100/")
  * query parameters         (VALID flag, param order, extra params, missing params)
  * repeated discovery       (a second walk of the same archive inserts nothing)
  * distinct episodes        (different e or ch never collapse into one key)

Stdlib only (unittest + a tiny in-memory fake of the DB layer); no network,
no MySQL. Run:  python -m unittest tests.test_episode_canon -v
"""
import os
import sys
import unittest

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, R)

import iranseda_site as site  # noqa: E402


# ---------------------------------------------------------------------------
# fake DB layer — mimics what the dedup paths do against radio_program_sessions
# ---------------------------------------------------------------------------

class FakeSessionsDB:
    """In-memory stand-in for radio_program_sessions.

    Enforces the UNIQUE(program_id, link) invariant the migration adds:
    inserting an already-known (program_id, link) pair is a no-op (IGNORE).
    """

    def __init__(self):
        self.rows = []  # (program_id, link)

    def insert_ignore(self, program_id, link):
        if (program_id, link) in self.rows:
            return False
        self.rows.append((program_id, link))
        return True

    def links_for(self, program_id):
        return [l for p, l in self.rows if p == program_id]


def simulate_discovery(db, program_id, pages_items, site_mod=site):
    """Replay the core loop of discover_new.py / _seed_program against the
    fake DB: canonical known-set, insert only unseen episodes, keep walking
    until a page has nothing new. Returns the list of inserted links."""
    known = {site_mod.canon_episode_link(l)
             for l in db.links_for(program_id)}
    known.discard(None)
    inserted = []
    for items in pages_items:
        new_items = [it for it in items
                     if it.get("canon") and it["canon"] not in known]
        for it in new_items:
            assert db.insert_ignore(program_id, it["url"])  # UNIQUE holds
            known.add(it["canon"])
            inserted.append(it["url"])
        if not new_items:
            break  # caught up
    return inserted


def ep(ch, e, **kw):
    """Build a parse_episode_cards()-shaped record with a canonical url,
    as the live parser emits (relative href, VALID flag)."""
    url = f"../epgarchivePart/?VALID=TRUE&ch={ch}&e={e}"
    rec = {"e": e, "url": url, "canon": site.canon_episode_link(url),
           "title": "t", "date_jalali": "1 Farvardin", "year": 1405,
           "time": "01:25"}
    rec.update(kw)
    return rec


# ---------------------------------------------------------------------------
# 1) the canonicalization function itself
# ---------------------------------------------------------------------------

class TestCanonEquivalence(unittest.TestCase):
    """The same episode written in different URL forms must get one key."""

    BASE_EP = "epgarchivePart?ch=14&e=100"

    def test_relative_and_absolute_are_equal(self):
        rel = "../epgarchivePart/?VALID=TRUE&ch=14&e=100"
        abs_ = "https://radio.iranseda.ir/epgarchivePart/?VALID=TRUE&ch=14&e=100"
        self.assertEqual(site.canon_episode_link(rel), self.BASE_EP)
        self.assertEqual(site.canon_episode_link(abs_), self.BASE_EP)
        self.assertEqual(site.canon_episode_link(rel),
                         site.canon_episode_link(abs_))

    def test_trailing_slash_is_irrelevant(self):
        self.assertEqual(site.canon_episode_link(
            "../epgarchivePart/?VALID=TRUE&ch=14&e=100/"), self.BASE_EP)
        self.assertEqual(site.canon_episode_link(
            "../epgarchivePart/?ch=14&e=100/"), self.BASE_EP)
        self.assertEqual(site.canon_episode_link(
            "https://radio.iranseda.ir/epgarchivePart/?ch=14&e=100/"),
            self.BASE_EP)

    def test_valid_flag_and_param_order_are_irrelevant(self):
        self.assertEqual(site.canon_episode_link(
            "../epgarchivePart/?ch=14&e=100"), self.BASE_EP)
        self.assertEqual(site.canon_episode_link(
            "../epgarchivePart/?e=100&ch=14"), self.BASE_EP)
        self.assertEqual(site.canon_episode_link(
            "../epgarchivePart/?VALID=FALSE&ch=14&e=100"), self.BASE_EP)

    def test_extra_params_do_not_change_identity(self):
        self.assertEqual(site.canon_episode_link(
            "../epgarchivePart/?VALID=TRUE&ch=14&e=100&pn=3"), self.BASE_EP)

    def test_deep_prefix_and_double_slash_prefix(self):
        self.assertEqual(site.canon_episode_link(
            "https://radio.iranseda.ir/../../epgarchivePart/?ch=14&e=100"),
            self.BASE_EP)
        self.assertEqual(site.canon_episode_link(
            "/epgarchivePart/?ch=14&e=100"), self.BASE_EP)

    def test_distinct_episodes_never_collapse(self):
        self.assertNotEqual(site.canon_episode_link(
            "../epgarchivePart/?ch=14&e=100"),
            site.canon_episode_link("../epgarchivePart/?ch=14&e=101"))
        self.assertNotEqual(site.canon_episode_link(
            "../epgarchivePart/?ch=14&e=100"),
            site.canon_episode_link("../epgarchivePart/?ch=15&e=100"))

    def test_non_episode_links_return_none(self):
        self.assertIsNone(site.canon_episode_link(
            "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=049113"))
        self.assertIsNone(site.canon_episode_link(
            "../epgarchivePart/?ch=14"))            # missing e
        self.assertIsNone(site.canon_episode_link(
            "../epgarchivePart/?e=100"))            # missing ch
        self.assertIsNone(site.canon_episode_link(""))
        self.assertIsNone(site.canon_episode_link(None))


class TestParseCardsCarryCanon(unittest.TestCase):
    """The live parser must attach the same canonical key to each card."""

    HTML = """
    <a href="../epgarchivePart/?VALID=TRUE&ch=14&e=5555">
      <div class="dt-title fa-number"><h2>29</h2>
        <h4>مهر<span class="clearfix">1405 (ساعت 1:25)</span></h4></div>
      <p class="ott-name x">تیتر</p></a>
    <a href="../epgarchivePart/?VALID=TRUE&ch=14&e=5554">
      <div class="dt-title fa-number"><h2>28</h2>
        <h4>مهر<span class="clearfix">1405 (ساعت 1:25)</span></h4></div>
      <p class="ott-name x"></p></a>
    """

    def test_parser_output_cannot_duplicate_across_formats(self):
        cards = site.parse_episode_cards(self.HTML)
        self.assertEqual(len(cards), 2)
        canon = [c["canon"] for c in cards]
        self.assertEqual(canon, ["epgarchivePart?ch=14&e=5555",
                                 "epgarchivePart?ch=14&e=5554"])
        # an absolute re-parsing of the same page yields identical keys
        abs_cards = site.parse_episode_cards(
            self.HTML.replace("../epgarchivePart",
                              "https://radio.iranseda.ir/epgarchivePart"))
        self.assertEqual([c["canon"] for c in abs_cards], canon)


# ---------------------------------------------------------------------------
# 2) repeated discovery must not create duplicates
# ---------------------------------------------------------------------------

class TestRepeatedDiscovery(unittest.TestCase):
    def _page(self, ch, e):
        return [ep(ch, e)]

    def test_second_run_inserts_nothing(self):
        db = FakeSessionsDB()
        first = simulate_discovery(db, 7, [self._page(14, 200),
                                            self._page(14, 199)])
        self.assertEqual(len(first), 2)
        second = simulate_discovery(db, 7, [self._page(14, 200),
                                            self._page(14, 199)])
        self.assertEqual(second, [])
        self.assertEqual(len(db.rows), 2)

    def test_new_episode_is_still_added(self):
        db = FakeSessionsDB()
        simulate_discovery(db, 7, [self._page(14, 200)])
        added = simulate_discovery(db, 7, [self._page(14, 201),
                                           self._page(14, 200)])
        self.assertEqual(len(added), 1)
        self.assertEqual(len(db.rows), 2)

    def test_format_mismatch_between_runs_is_recognized(self):
        """The stored link is relative; a later walk 'sees' the same episode
        as an absolute URL. The canonical key must still match."""
        db = FakeSessionsDB()
        db.insert_ignore(7, "../epgarchivePart/?VALID=TRUE&ch=14&e=200")
        # the fresh record, as an absolute variant, must NOT be re-inserted
        abs_item = ep(14, 200)
        abs_item["url"] = ("https://radio.iranseda.ir/epgarchivePart/"
                           "?ch=14&e=200")
        abs_item["canon"] = site.canon_episode_link(abs_item["url"])
        added = simulate_discovery(db, 7, [[abs_item]])
        self.assertEqual(added, [])
        self.assertEqual(len(db.rows), 1)

    def test_same_e_different_program_not_confused_within_program(self):
        db = FakeSessionsDB()
        simulate_discovery(db, 7, [self._page(14, 200)])
        simulate_discovery(db, 8, [self._page(14, 200)])  # other program
        self.assertEqual(len(db.rows), 2)  # same episode, two programs: OK

    def test_distinct_episodes_all_stay_distinct(self):
        db = FakeSessionsDB()
        added = simulate_discovery(db, 7, [self._page(14, 200 - i)
                                           for i in range(5)][::-1])
        self.assertEqual(len(added), 5)
        self.assertEqual(len(set(l for _, l in db.rows)), 5)


# ---------------------------------------------------------------------------
# 3) seeding-path behavior (per-episode dedup + SEED_EPISODE_CAP)
# ---------------------------------------------------------------------------

class TestSeedBehavior(unittest.TestCase):
    def _seed_walk(self, db, program_id, pages_items, start_mode,
                   start_year=None, episode_cap=0, new_max_e=0):
        """Mirrors _seed_program's per-episode filter (incl. the cap)."""
        known = {site.canon_episode_link(l)
                 for l in db.links_for(program_id)}
        known.discard(None)
        inserted = 0
        page = 0
        for items in pages_items:
            page += 1
            batch = []
            stop = False
            for it in items:
                if start_mode == "new_only" and it["e"] <= new_max_e:
                    stop = True
                    break
                if start_mode == "from_date" and start_year and \
                        it.get("year") and it["year"] < start_year:
                    stop = True
                    break
                if episode_cap and inserted + len(batch) >= episode_cap:
                    stop = True
                    break
                if not it.get("canon") or it["canon"] in known:
                    continue
                batch.append(it)
            for it in batch:
                db.insert_ignore(program_id, it["url"])
                known.add(it["canon"])
                inserted += 1
            if stop:
                break
        return inserted, page

    def test_seed_cap_limits_total_inserts(self):
        db = FakeSessionsDB()
        pages = [[ep(14, 300 - i) for i in range(20)] for _ in range(3)]
        inserted, _ = self._seed_walk(db, 9, pages, "from_date",
                                      episode_cap=7)
        self.assertEqual(inserted, 7)
        self.assertEqual(len(db.rows), 7)

    def test_reseed_with_cap_inserts_next_batch_without_dups(self):
        """SEED_EPISODE_CAP is a per-run limit: each seed run inserts at most
        `cap` NEW episodes; re-runs continue from where the queue is, and the
        canonical dedup guarantees no duplicate rows ever."""
        db = FakeSessionsDB()
        pages = [[ep(14, 300 - i) for i in range(20)] for _ in range(3)]
        self._seed_walk(db, 9, pages, "from_date", episode_cap=7)
        self.assertEqual(len(db.rows), 7)
        inserted, _ = self._seed_walk(db, 9, pages, "from_date",
                                      episode_cap=7)
        self.assertEqual(inserted, 7)  # next-newest batch, still <= cap
        self.assertEqual(len(db.rows), 14)
        self.assertEqual(len(set(l for _, l in db.rows)), 14)

    def test_exact_rerun_of_known_items_is_noop(self):
        """Re-walking exactly the items already in the queue inserts nothing
        (the per-episode dedup the fix adds to the seed path)."""
        db = FakeSessionsDB()
        db.insert_ignore(9, "../epgarchivePart/?VALID=TRUE&ch=14&e=300")
        db.insert_ignore(9, "../epgarchivePart/?VALID=TRUE&ch=14&e=299")
        page = [[ep(14, 300), ep(14, 299), ep(14, 298)]]
        inserted, _ = self._seed_walk(db, 9, page, "from_date")
        self.assertEqual(inserted, 1)      # only e=298 was new
        self.assertEqual(len(db.rows), 3)
        # walk the exact same page again: everything is known now
        inserted2, _ = self._seed_walk(db, 9, page, "from_date")
        self.assertEqual(inserted2, 0)
        self.assertEqual(len(db.rows), 3)
        self.assertEqual(len(set(l for _, l in db.rows)), 3)

    def test_new_only_stops_at_newest_known(self):
        db = FakeSessionsDB()
        db.insert_ignore(9, "../epgarchivePart/?VALID=TRUE&ch=14&e=300")
        page = [[ep(14, e) for e in range(300, 280, -1)]]
        inserted, _ = self._seed_walk(db, 9, page, "new_only",
                                      new_max_e=300)
        self.assertEqual(inserted, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
