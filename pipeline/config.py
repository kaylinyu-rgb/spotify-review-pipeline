"""Shared label definitions, versions and default settings.

Everything a model role is allowed to output is defined here, so code (not the
model) owns the taxonomy. Changing anything that affects labels must bump a
version string, which changes `label_config` and invalidates the result cache.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

SOURCE_FIELDS = ("review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp")
FULL_SHA256 = "1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6"
FULL_ROWS = 660_622
FULL_NONEMPTY = 660_609
FULL_DISTINCT = 484_189

TOPICS = ("access", "usability", "playback", "downloads", "catalog", "billing", "support", "other")
INTENTS = ("cancellation", "complaint", "request", "praise", "unclear")  # precedence order
SENTIMENTS = (-1.0, -0.5, 0.0, 0.5, 1.0)
SEVERITIES = (1, 2, 3, 4, 5)

# Optional custom subtopics. issue_id == "<topic>.<subtopic>", so grouping is a
# deterministic function of the enrichment label and needs no model.
SUBTOPICS: dict[str, tuple[str, ...]] = {
    "access": ("login_failure", "logged_out_or_account_lost", "account_hacked", "signup_or_install", "access_other"),
    "usability": ("ads", "shuffle_or_track_control", "ui_redesign_or_navigation", "playlist_or_library", "usability_other"),
    "playback": ("crash_or_wont_open", "playback_stops_or_skips", "device_or_connection", "audio_quality", "performance_or_battery", "playback_other"),
    "downloads": ("download_fails", "downloads_disappear", "offline_mode", "downloads_other"),
    "catalog": ("missing_or_removed_content", "search_or_discovery", "recommendations", "lyrics", "podcasts_or_audiobooks", "catalog_other"),
    "billing": ("premium_paywall", "price", "charge_or_cancel_problem", "premium_not_recognized", "billing_other"),
    "support": ("support_unhelpful_or_unreachable", "support_other"),
    "other": ("general_praise", "general_criticism", "unrelated_or_unclear", "other_specific"),
}
LABELS = tuple(f"{t}.{s}" for t, subs in SUBTOPICS.items() for s in subs)

# ---- versions -------------------------------------------------------------
ENRICH_PROMPT_VERSION = "enrich-p2"   # p2: short per-batch keys, quotes <= 12 words
ENRICH_SCHEMA_VERSION = "schema-s2"
VERIFY_PROMPT_VERSION = "verify-p1"
GROUP_PROMPT_VERSION = "group-p1"
MEMO_PROMPT_VERSION = "memo-p1"
ENTITY_LEXICON_VERSION = "entities-l1"

# ---- default model settings (editable via CLI flags / env) ------------------
DEFAULTS = {
    "enrich_provider": os.environ.get("ENRICH_PROVIDER", "anthropic"),
    "enrich_model": os.environ.get("ENRICH_MODEL", "claude-haiku-5-5"),
    "enrich_effort": os.environ.get("ENRICH_EFFORT", "low"),          # thinking disabled + effort low (openai: reasoning.effort=none)
    "verify_provider": os.environ.get("VERIFY_PROVIDER", "jev"),
    "verify_model": os.environ.get("VERIFY_MODEL", "jev-latest"),
    "fallback_provider": os.environ.get("FALLBACK_PROVIDER", "anthropic"),
    "fallback_model": os.environ.get("FALLBACK_MODEL", "claude-haiku-5-5"),
    "fallback_effort": os.environ.get("FALLBACK_EFFORT", "medium"),   # same cheap model WITH adaptive thinking, capped fraction
    "group_provider": os.environ.get("GROUP_PROVIDER", "anthropic"),
    "group_model": os.environ.get("GROUP_MODEL", "claude-haiku-5-5"),
    "memo_provider": os.environ.get("MEMO_PROVIDER", "anthropic"),
    "memo_model": os.environ.get("MEMO_MODEL", "claude-haiku-5-5"),
    "memo_effort": os.environ.get("MEMO_EFFORT", "medium"),           # adaptive thinking for the one memo call
    "mode": os.environ.get("ENRICH_MODE", "batch"),   # Message Batches API: 50% price
    "batch_size": 50,             # hard maximum is 50 (grading contract)
    "batch_char_cap": 14_000,     # long reviews make smaller batches
    "workers": 1,
    "max_output_tokens_per_review": 110,
    "invalid_output_retries": 1,  # contract: retry invalid output once
    "transport_retries": 4,       # 429/5xx/timeouts, bounded backoff + jitter
    "budget_usd_per_100k": 10.0,  # course cap: <= $10 per 100k reviews
    "verify_rate": 0.01,          # declared random verification sample
    "verify_seed": "verify-seed-v1",
    "fallback_max_fraction": 0.001,  # capped Sonnet fallback (fraction of distinct texts)
}


def label_config(provider: str, model: str, effort: str) -> str:
    return f"{provider}:{model}+effort-{effort}+{ENRICH_PROMPT_VERSION}+{ENRICH_SCHEMA_VERSION}+{ENTITY_LEXICON_VERSION}"


def topic_of(label: str) -> str:
    return label.split(".", 1)[0]


def read_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def load_dotenv(path: Path | None = None) -> None:
    """Tiny .env loader (no dependency). Never logs values."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v
