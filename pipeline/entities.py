"""Deterministic (code-only) extraction: entities and evidence-quote repair.

Entities are explicit feature terms matched in the text, so they can never be
unsupported additions. Quotes from the model are accepted only if they are an
exact source substring (after a conservative, logged repair).
"""
from __future__ import annotations

import re

LEXICON = {
    "ads": r"\bads?\b|\badvert\w*|\bcommercials?\b",
    "premium": r"\bpremium\b",
    "free tier": r"\bfree (?:version|tier|plan|users?|account)\b",
    "skip limit": r"\bskips?\b",
    "shuffle": r"\bshuffl\w*",
    "smart shuffle": r"\bsmart shuffle\b",
    "lyrics": r"\blyric\w*",
    "playlist": r"\bplay ?lists?\b",
    "liked songs": r"\bliked songs\b",
    "queue": r"\bqueue\b",
    "search": r"\bsearch\w*",
    "recommendations": r"\brecommend\w*|\bdaily mix\w*|\bdiscover weekly\b",
    "podcast": r"\bpodcasts?\b",
    "audiobook": r"\baudio ?books?\b",
    "download": r"\bdownload\w*",
    "offline": r"\boffline\b",
    "login": r"\blog ?in\b|\bsign ?in\b|\blogged (?:out|in)\b",
    "password": r"\bpassword\w*",
    "account": r"\baccount\w*\b",
    "update": r"\bupdat\w*",
    "crash": r"\bcrash\w*",
    "bluetooth": r"\bbluetooth\b",
    "android auto": r"\bandroid auto\b",
    "car": r"\bcar\b|\bcarplay\b",
    "spotify connect": r"\bspotify connect\b|\bchromecast\b|\bcast(?:ing)?\b",
    "smart tv": r"\bsmart ?tv\b|\b(?:tv|television)\b",
    "watch": r"\bwear ?os\b|\bsmart ?watch\b|\bwatch\b",
    "widget": r"\bwidget\w*",
    "lock screen": r"\block ?screen\b",
    "notification": r"\bnotification\w*",
    "battery": r"\bbattery\b|\bdrain\w*",
    "storage": r"\bstorage\b|\bcache\b",
    "audio quality": r"\baudio quality\b|\bsound quality\b|\bequali[sz]er\b",
    "volume": r"\bvolume\b",
    "family plan": r"\bfamily (?:plan|premium)\b|\bduo\b",
    "student plan": r"\bstudent\b",
    "price": r"\bprice\w*|\bexpensive\b|\bcost\w*\b",
    "refund": r"\brefund\w*",
    "charge": r"\bcharg\w*|\bbilled\b|\bbilling\b",
    "customer support": r"\bcustomer (?:support|service|care)\b|\bsupport team\b",
    "dj": r"\bdj\b",
    "wrapped": r"\bwrapped\b",
    "home screen": r"\bhome (?:screen|page|tab)\b",
    "sleep timer": r"\bsleep timer\b",
    "repeat": r"\brepeat\w*",
    "radio": r"\bradio\b",
}
_COMPILED = [(name, re.compile(p, re.I)) for name, p in LEXICON.items()]


def extract_entities(text: str) -> list[str]:
    return [name for name, rx in _COMPILED if rx.search(text)]


_QUOTE_CHARS = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def repair_quote(quote: str, text: str, full_text_max: int = 300) -> tuple[str | None, str]:
    """Return (exact substring or None, how). Never invents text: any accepted
    quote is sliced from the original review."""
    q = (quote or "").strip()
    if q and q in text:
        return q, "model_exact"
    if q:
        i = text.lower().find(q.lower())
        if i >= 0:
            return text[i:i + len(q)], "model_case_repaired"
        words = [re.escape(w.translate(_QUOTE_CHARS)) for w in q.split()]
        if words:
            # tolerate whitespace / curly-quote differences only
            pat = r"\s+".join(w.replace("'", "['’‘]").replace('"', '["“”]') for w in words)
            m = re.search(pat, text, re.I)
            if m:
                return m.group(0), "model_whitespace_repaired"
    stripped = text.strip()
    if stripped and len(stripped) <= full_text_max:
        return stripped, "fallback_full_text"
    return None, "unsupported_quote"
