"""Configuration for the corpus exporter.

Everything is environment-gated (mission rule §8): the exporter does
nothing unless explicitly invoked, and the scheduler is disabled by
default (CORPUS_EXPORT_ENABLED=false).

Env vars (all optional; sensible defaults):
  DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME      (fallback: repo .env)
  CORPUS_ROOT          project root (default: parent of corpus/)
  CORPUS_DOWNLOADS_DIR downloads dir (default: <root>/downloads)
  CORPUS_OUT_DIR       output dir (default: <root>/data/corpus)
  CORPUS_INLINE_ORIGINALS   true|false (default true)
  CORPUS_INLINE_LLM         true|false (default true)
  CORPUS_SHARD_LINES      max records per jsonl shard (default 0 = single file)
  CORPUS_INCREMENTAL_HOURS  scheduler interval (default 6)
  CORPUS_OVERLAP_HOURS    watermark overlap (default 12)
  CORPUS_EXPORT_ENABLED   scheduler on/off (default false)
"""

import os
import json

DEFAULTS = {
    "db_host": "127.0.0.1",
    "db_port": 3308,
    "db_user": "n8nuser",
    "db_pass": "",
    "db_name": "radio",
    "inline_originals": True,
    "inline_llm": True,
    "shard_lines": 0,
    "incremental_hours": 6.0,
    "overlap_hours": 12.0,
    "export_enabled": False,
    "site_base": "https://radio.iranseda.ir/",
}


def load_dotenv(path):
    """Minimal .env parser (KEY=VALUE, # comments) — same style as the
    existing dashboard/scripts loaders. Returns dict, never raises."""
    env = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    except OSError:
        pass
    return env


def _b(v, default):
    if v is None or v == "":
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


class Config(object):
    def __init__(self, **kw):
        self.root = kw.get("root")
        self.downloads_dir = kw.get("downloads_dir")
        self.out_dir = kw.get("out_dir")
        self.db_host = kw.get("db_host", DEFAULTS["db_host"])
        self.db_port = int(kw.get("db_port", DEFAULTS["db_port"]))
        self.db_user = kw.get("db_user", DEFAULTS["db_user"])
        self.db_pass = kw.get("db_pass", DEFAULTS["db_pass"])
        self.db_name = kw.get("db_name", DEFAULTS["db_name"])
        self.inline_originals = bool(kw.get("inline_originals", DEFAULTS["inline_originals"]))
        self.inline_llm = bool(kw.get("inline_llm", DEFAULTS["inline_llm"]))
        self.shard_lines = int(kw.get("shard_lines", DEFAULTS["shard_lines"]))
        self.incremental_hours = float(kw.get("incremental_hours", DEFAULTS["incremental_hours"]))
        self.overlap_hours = float(kw.get("overlap_hours", DEFAULTS["overlap_hours"]))
        self.export_enabled = bool(kw.get("export_enabled", DEFAULTS["export_enabled"]))
        self.site_base = kw.get("site_base", DEFAULTS["site_base"])

    # ------------------------------------------------------------------
    @classmethod
    def from_env(cls, root=None, dotenv_path=None):
        root = root or os.environ.get("CORPUS_ROOT") or os.path.abspath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        )
        env = {}
        if dotenv_path is None:
            dotenv_path = os.path.join(root, ".env")
        if os.path.exists(dotenv_path):
            env = load_dotenv(dotenv_path)

        def pick(key, default=None):
            v = os.environ.get(key)
            if v is None or v == "":
                v = env.get(key, default)
            return v if v not in (None, "") else default

        return cls(
            root=root,
            downloads_dir=os.environ.get("CORPUS_DOWNLOADS_DIR")
            or os.path.join(root, "downloads"),
            out_dir=os.environ.get("CORPUS_OUT_DIR") or os.path.join(root, "data", "corpus"),
            db_host=pick("DB_HOST", DEFAULTS["db_host"]),
            db_port=int(pick("DB_PORT", DEFAULTS["db_port"])),
            db_user=pick("DB_USER", DEFAULTS["db_user"]),
            db_pass=pick("DB_PASS", DEFAULTS["db_pass"]),
            db_name=pick("DB_NAME", DEFAULTS["db_name"]),
            inline_originals=_b(os.environ.get("CORPUS_INLINE_ORIGINALS"),
                                 DEFAULTS["inline_originals"]),
            inline_llm=_b(os.environ.get("CORPUS_INLINE_LLM"),
                          DEFAULTS["inline_llm"]),
            shard_lines=int(pick("CORPUS_SHARD_LINES", DEFAULTS["shard_lines"]) or 0),
            incremental_hours=float(pick("CORPUS_INCREMENTAL_HOURS",
                                         DEFAULTS["incremental_hours"])),
            overlap_hours=float(pick("CORPUS_OVERLAP_HOURS", DEFAULTS["overlap_hours"])),
            export_enabled=_b(os.environ.get("CORPUS_EXPORT_ENABLED"),
                              DEFAULTS["export_enabled"]),
        )

    # ------------------------------------------------------------------
    def to_dict(self):
        """Sanitized dump (no password) for manifests/reports."""
        d = {
            "root": self.root,
            "downloads_dir": self.downloads_dir,
            "out_dir": self.out_dir,
            "db_host": self.db_host,
            "db_port": self.db_port,
            "db_user": self.db_user,
            "db_name": self.db_name,
            "db_pass": "<redacted>",
            "inline_originals": self.inline_originals,
            "inline_llm": self.inline_llm,
            "shard_lines": self.shard_lines,
            "incremental_hours": self.incremental_hours,
            "overlap_hours": self.overlap_hours,
            "export_enabled": self.export_enabled,
            "site_base": self.site_base,
        }
        return d

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)
