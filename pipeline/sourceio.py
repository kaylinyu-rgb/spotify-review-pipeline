"""CSV reading and source hashing (identical to the provided check_submission.py helpers)."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from .config import SOURCE_FIELDS


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def row_sha(row: dict) -> str:
    """SHA-256 of compact UTF-8 JSON of the six original strings (grading-contract helper)."""
    return hashlib.sha256(canonical([row[k] for k in SOURCE_FIELDS]).encode("utf-8")).hexdigest()


def text_hash(text: str) -> str:
    """Exact-text cache key. No normalisation: similar text is not an exact match."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_rows(path: Path):
    """Stream rows with a real CSV parser (multiline quoted text is one row)."""
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, strict=True)
        missing = [k for k in SOURCE_FIELDS if k not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Input CSV is missing required columns: {missing}")
        for row in reader:
            if None in row or any(row.get(k) is None for k in SOURCE_FIELDS):
                raise ValueError("Malformed CSV row near review_id=%r" % row.get("review_id"))
            yield {k: row[k] for k in SOURCE_FIELDS}
