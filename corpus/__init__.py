"""IranSeda corpus exporter (v1).

Standalone, read-only, permanent corpus builder for the IranSeda radio
production database + pipeline-generated files.

Design constraints (production host 172.20.1.53, dashboard venv):
  * Python stdlib + pymysql ONLY (no jdatetime, no jsonschema, no pytest).
  * Read-only database access. Never writes to the production DB.
  * Never disturbs the main pipeline (download/Whisper/LLM/site).

Contract:
  schemas/iranseda-corpus-v1.schema.json
  docs/CORPUS_DATA_MODEL.md
  docs/CORPUS_FIELD_MAPPING.md
"""

__version__ = "1.0.0"

SCHEMA_VERSION = "1.0"

SITE_BASE = "https://radio.iranseda.ir/"

# Known job types in the live DB (pipeline_steps slugs + legacy).
# Novel values pass through with a warning, never a failure.
KNOWN_JOB_TYPES = (
    "correct_subtitles",
    "correct_text",
    "summary",
    "full_text",
    "qa",
)
