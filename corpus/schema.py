"""Versioned corpus schema loader + verification (pure stdlib — no
jsonschema dependency on 53).

Stage 2 (mission IRANSEDA-CORPUS-2026-01): the corpus ships its own
versioned schema files under corpus/schema/:

  corpus/schema/corpus.schema.json   Draft 2020-12 record schema,
                                     v1.0, with x-corpus metadata and
                                     the Stage 1 identity-policy
                                     annotations.
  corpus/schema/field_mapping.json   machine-readable DB/disk/computed
                                     mapping with an explicit status
                                     per field (available / derivable /
                                     missing / unverified /
                                     not_applicable). No source is
                                     ever invented.
  corpus/schema/examples/            reference records:
                                     valid_record.json (passes the
                                     stdlib record validator),
                                     quarantine_record.json (the
                                     {record, problems} line shape of
                                     data/corpus/invalid.jsonl and of
                                     quarantine.jsonl).

`verify()` is the Stage 2 gate: schema is well-formed JSON in the
2020-12 dialect, the field mapping covers every record field and uses
only declared statuses, and the examples pass corpus.validator
(structural validation). Used by tests and by later stages to detect
silent schema drift.
"""

import json
import os

from . import validator

DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_DIR = os.path.join(HERE, "schema")
SCHEMA_PATH = os.path.join(SCHEMA_DIR, "corpus.schema.json")
FIELD_MAPPING_PATH = os.path.join(SCHEMA_DIR, "field_mapping.json")
EXAMPLES_DIR = os.path.join(SCHEMA_DIR, "examples")

MAPPING_STATUSES = ("available", "derivable", "missing", "unverified",
                    "not_applicable", "const")
# source types that imply a live db/disk source must be named
SOURCE_REQUIRED_TYPES = ("db", "disk")

# Top-level record properties that must be covered by the field mapping.
# (Every one of these has at least one field_mapping entry whose path
# starts with it — e.g. "broadcast", "broadcast.jalali.date", ...)
REQUIRED_TOP_COVERAGE = (
    "schema_version", "record_id", "episode_key", "database_refs",
    "program", "audio", "speakers", "transcripts", "crop",
    "source_metadata", "pipeline_state", "provenance", "quality",
    # v1.1 additive (Stage 4, spec §8.1) — must be covered by field mapping
    "session_uid", "session_uid_status", "program_uid",
    "program_uid_status", "linkage",
)


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def schema_dir():
    """Absolute path of the versioned schema directory."""
    return SCHEMA_DIR


def load_schema():
    """Load corpus/schema/corpus.schema.json (dict)."""
    return _load_json(SCHEMA_PATH)


def load_field_mapping():
    """Load corpus/schema/field_mapping.json (dict)."""
    return _load_json(FIELD_MAPPING_PATH)


def list_examples():
    """Names of the bundled example files (sorted)."""
    return sorted(f for f in os.listdir(EXAMPLES_DIR) if f.endswith(".json"))


def load_example(name):
    """Load one bundled example by filename."""
    return _load_json(os.path.join(EXAMPLES_DIR, name))


def _schema_problems(sch):
    p = []
    if not isinstance(sch, dict):
        return ["schema: not a JSON object"]
    if sch.get("$schema") != DRAFT_2020_12:
        p.append("$schema: expected %s, got %r" % (DRAFT_2020_12,
                                                   sch.get("$schema")))
    if not isinstance(sch.get("$id"), str) or not sch["$id"]:
        p.append("$id: missing/empty")
    if not isinstance(sch.get("title"), str):
        p.append("title: missing")
    if not isinstance(sch.get("properties"), dict):
        p.append("properties: missing")
    if not isinstance(sch.get("required"), list):
        p.append("required: missing")
    meta = sch.get("x-corpus")
    if not isinstance(meta, dict) or not isinstance(meta.get("schema_version"), str):
        p.append("x-corpus.schema_version: missing")
    return p


def _mapping_problems(fm):
    p = []
    if not isinstance(fm, dict):
        return ["field_mapping: not a JSON object"]
    if not isinstance(fm.get("version"), str):
        p.append("version: missing")
    legend = fm.get("legend")
    if not isinstance(legend, dict):
        p.append("legend: missing")
    else:
        for s in MAPPING_STATUSES:
            if s not in legend:
                p.append("legend: missing status %r" % s)
    fields = fm.get("fields")
    if not isinstance(fields, list) or not fields:
        p.append("fields: missing/empty")
        return p
    for i, f in enumerate(fields):
        if not isinstance(f, dict):
            p.append("fields[%d]: not an object" % i)
            continue
        for k in ("field", "status"):
            if k not in f:
                p.append("fields[%d]: missing %r" % (i, k))
        st = f.get("status")
        if st is not None and st not in MAPPING_STATUSES:
            p.append("fields[%d]: unknown status %r" % (i, st))
    covered = set()
    for f in fields:
        if not isinstance(f, dict):
            continue
        fld = f.get("field") or ""
        # "table:xyz" entries are out-of-scope markers; real field paths
        # start with a top-level property name.
        for top in REQUIRED_TOP_COVERAGE:
            if fld == top or fld.startswith(top + "."):
                covered.add(top)
    for top in REQUIRED_TOP_COVERAGE:
        if top not in covered:
            p.append("fields: no mapping entry covers %r" % top)
    # Fields read from live db/disk must name that source. (Pure
    # `computed` values like quality.missing / provenance.exported_at and
    # `const` values legitimately have source_type=computed/const.)
    for i, f in enumerate(fields):
        if not isinstance(f, dict):
            continue
        fld = f.get("field") or ""
        if fld.startswith("table:"):
            continue
        if f.get("source_type") in SOURCE_REQUIRED_TYPES and not f.get("source"):
            p.append("fields[%d]: %s has source_type %s but no source"
                     % (i, fld, f.get("source_type")))
    return p


def verify(examples=None):
    """Stage 2 schema gate. Returns a list of problem strings
    (empty = schema, field mapping and examples all consistent)."""
    p = []
    sch = load_schema()
    p.extend(_schema_problems(sch))

    # x-corpus metadata must agree with the versioned record contract.
    meta = sch.get("x-corpus") or {}
    if sch.get("properties", {}).get("schema_version", {}).get("const") != \
            meta.get("schema_version"):
        p.append("x-corpus.schema_version disagrees with "
                 "properties.schema_version.const")

    fm = load_field_mapping()
    p.extend(_mapping_problems(fm))

    # Examples must pass the structural record validator.
    names = examples or list_examples()
    for name in names:
        try:
            ex = load_example(name)
        except (OSError, ValueError) as e:
            p.append("examples/%s: unreadable: %s" % (name, e))
            continue
        if name.startswith("quarantine_record"):
            rec = ex.get("record")
            if not isinstance(rec, dict):
                p.append("examples/%s: missing 'record' object" % name)
                continue
            probs = validator.validate_record(rec)
            if probs:
                p.append("examples/%s: record invalid: %s"
                         % (name, "; ".join(probs)))
            if not isinstance(ex.get("problems"), list) or not ex["problems"]:
                p.append("examples/%s: 'problems' must be a non-empty "
                         "list" % name)
        else:
            probs = validator.validate_record(ex)
            if probs:
                p.append("examples/%s: %s" % (name, "; ".join(probs)))
    return p
