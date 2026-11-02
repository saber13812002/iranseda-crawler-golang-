"""
test_messenger_publisher.py — no-network tests for the Telegram/Bale
PublisherClient adapter (dashboard/messenger_publisher.py).

Covers the honesty contract:
  * no credentials            -> not configured, install keeps the stub
  * MESSENGER_* + TELEGRAM_* fallback credential resolution
  * all chats accept          -> marker with message ids, check -> published
  * one chat fails            -> error, NO marker (worker retries, bounded)
  * network exception         -> error, NO marker
  * unknown external id       -> never a fabricated "published"
  * build_message HTML-escapes untrusted title/body

Stdlib only; the HTTP layer is stubbed. Run:
    python -m unittest tests.test_messenger_publisher -v
"""
import html
import os
import sys
import unittest

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(R, "dashboard"))

import messenger_publisher as mp  # noqa: E402
import reporter  # noqa: E402


class _EnvGuard:
    KEYS = ("MESSENGER_TYPE", "MESSENGER_BOT_TOKEN", "MESSENGER_CHAT_ID",
            "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")

    def __enter__(self):
        self.old = {k: os.environ.get(k) for k in self.KEYS}
        for k in self.KEYS:
            os.environ.pop(k, None)
        return self

    def set(self, **kw):
        for k, v in kw.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestConfig(unittest.TestCase):
    def test_none_when_no_creds(self):
        with _EnvGuard():
            self.assertIsNone(mp.load_config())

    def test_messenger_env_multi_chat(self):
        with _EnvGuard() as env:
            env.set(MESSENGER_TYPE="bale", MESSENGER_BOT_TOKEN="t",
                    MESSENGER_CHAT_ID="a, b")
            self.assertEqual(mp.load_config(), ("bale", "t", ["a", "b"]))

    def test_telegram_fallback(self):
        with _EnvGuard() as env:
            env.set(TELEGRAM_BOT_TOKEN="tk", TELEGRAM_CHAT_ID="77")
            self.assertEqual(mp.load_config(), ("telegram", "tk", ["77"]))

    def test_messenger_beats_fallback(self):
        with _EnvGuard() as env:
            env.set(MESSENGER_BOT_TOKEN="m", MESSENGER_CHAT_ID="1",
                    TELEGRAM_BOT_TOKEN="t", TELEGRAM_CHAT_ID="2")
            self.assertEqual(mp.load_config(), ("telegram", "m", ["1"]))


class TestPublish(unittest.TestCase):
    def _client(self):
        return mp.MessengerClient(("telegram", "token", ["1", "2"]))

    def _swap(self, fake):
        orig = mp.http_post_json
        mp.http_post_json = fake
        return orig

    def _restore(self, orig):
        mp.http_post_json = orig

    def test_all_ok_gives_marker_then_published(self):
        c = self._client()
        orig = self._swap(lambda url, payload, timeout=20:
                          (200, {"ok": True, "result": {"message_id": 5}}))
        try:
            res = c.publish({"event_type": "download_batch", "title": "T",
                             "body": "b"})
        finally:
            self._restore(orig)
        self.assertNotIn("error", res)
        self.assertTrue(res["external_task_id"].startswith("sent:"))
        self.assertIn("5,5", res["external_task_id"])
        st = c.check_status(res["external_task_id"])
        self.assertEqual(st["state"], "published")
        self.assertIn("message_ids=", st["post_urls"]["telegram"])
        self.assertIsNone(st["error"])

    def test_one_chat_fails_no_marker(self):
        c = self._client()
        calls = {"n": 0}

        def fake(url, payload, timeout=20):
            calls["n"] += 1
            if calls["n"] == 1:
                return (200, {"ok": True, "result": {"message_id": 1}})
            return (400, {"ok": False, "description": "bad chat id"})

        orig = self._swap(fake)
        try:
            res = c.publish({"title": "T"})
        finally:
            self._restore(orig)
        self.assertIn("error", res)
        self.assertIsNone(res.get("external_task_id"))
        self.assertIn("bad chat id", res["error"])

    def test_network_exception_is_failure(self):
        c = self._client()

        def boom(url, payload, timeout=20):
            raise OSError("net down")

        orig = self._swap(boom)
        try:
            res = c.publish({"title": "T"})
        finally:
            self._restore(orig)
        self.assertIn("error", res)
        self.assertIsNone(res.get("external_task_id"))
        self.assertIn("chat 1", res["error"])

    def test_unknown_ext_id_never_published(self):
        c = self._client()
        st = c.check_status("something-else")
        self.assertNotEqual(st["state"], "published")

    def test_build_message_escapes_html(self):
        text = mp.build_message({"event_type": "e", "title": "<b>x</b>",
                                 "body": "a&b"})
        self.assertNotIn("<b>x</b>", text)
        # expected escaped forms computed at runtime (no entity literals
        # in this source file)
        self.assertIn(html.escape("<b>x</b>"), text)
        self.assertIn(html.escape("a&b"), text)

    def test_build_message_caps_length(self):
        text = mp.build_message({"event_type": "e", "title": "x",
                                 "body": "y" * 9000})
        self.assertLessEqual(len(text), 4000)


class TestInstall(unittest.TestCase):
    def test_keeps_stub_without_creds(self):
        orig = reporter.get_client()
        try:
            with _EnvGuard():
                self.assertFalse(mp.install_if_configured())
                self.assertIsInstance(reporter.get_client(),
                                      reporter.StubClient)
                self.assertFalse(reporter.client_configured())
        finally:
            reporter.set_client(orig)

    def test_sets_real_client_with_creds(self):
        orig = reporter.get_client()
        try:
            with _EnvGuard() as env:
                env.set(MESSENGER_BOT_TOKEN="t", MESSENGER_CHAT_ID="1")
                self.assertTrue(mp.install_if_configured())
                self.assertTrue(reporter.client_configured())
        finally:
            reporter.set_client(orig)


if __name__ == "__main__":
    unittest.main()
