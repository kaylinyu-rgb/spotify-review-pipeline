"""Model providers behind one small interface (standard-library HTTP only).

Every call returns raw usage so cost is computed from billed units x editable
rates (pipeline/rates.py). Keys are read from environment variables and never logged.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import ssl
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field


class TransportError(Exception):
    def __init__(self, msg, retryable=True, status=None, usage_unknown=False):
        super().__init__(msg)
        self.retryable, self.status, self.usage_unknown = retryable, status, usage_unknown


@dataclass
class Result:
    text: str
    stop_reason: str
    usage: dict = field(default_factory=dict)   # input, cached_input, cache_write, output (mutually exclusive)
    provider_request_id: str = ""
    raw: dict | None = None


def _ssl_ctx():
    try:
        import certifi  # macOS python.org builds often lack system certs
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _post(url, headers, body, timeout=180):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers, "content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
            return json.loads(r.read().decode("utf-8")), dict(r.headers)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        retryable = e.code in (408, 409, 425, 429, 500, 502, 503, 504, 529)
        raise TransportError(f"HTTP {e.code}: {detail}", retryable=retryable, status=e.code) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, ssl.SSLError, OSError) as e:
        # A timeout may still be billed by the provider -> usage unknown, must be reconciled.
        raise TransportError(f"{type(e).__name__}: {e}", retryable=True, usage_unknown=True) from None


def _get(url, headers, timeout=180) -> bytes:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise TransportError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}", retryable=e.code in (429, 500, 502, 503, 504, 529),
                             status=e.code) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise TransportError(f"{type(e).__name__}: {e}", retryable=True) from None


def _key(name):
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"{name} is not set. Copy .env.example to .env and fill it in (paid calls only).")
    return v


class Anthropic:
    name = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model, effort="low"):
        self.model, self.effort = model, effort

    def settings(self):
        return {"provider": self.name, "model": self.model, "thinking": "adaptive" if self.effort in ("medium", "high") else "disabled",
                "effort": self.effort,
                "endpoint": "v1/messages (standard tier)", "structured_output": "output_config.format json_schema"}

    def params(self, system, user, schema, max_tokens) -> dict:
        body = {"model": self.model, "max_tokens": max_tokens,
                "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                "messages": [{"role": "user", "content": user}],
                "thinking": {"type": "disabled"},
                "output_config": {"effort": self.effort, "format": {"type": "json_schema", "schema": schema}}}
        if self.effort in ("medium", "high"):   # stronger settings: let the model think (adaptive), billed as output
            body["thinking"] = {"type": "adaptive"}
        if "sonnet" in self.model:  # Sonnet 5.5 turns off up-front thinking this way
            body["thinking"] = {"type": "between_tools"}
        return body

    @staticmethod
    def headers():
        return {"x-api-key": _key("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"}

    def complete(self, system, user, schema, max_tokens) -> Result:
        resp, _ = _post(self.URL, self.headers(), self.params(system, user, schema, max_tokens))
        return self.parse(resp)

    @staticmethod
    def parse(resp) -> Result:
        u = resp.get("usage", {}) or {}
        text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
        return Result(text=text, stop_reason=resp.get("stop_reason", ""), provider_request_id=resp.get("id", ""),
                      usage={"input": u.get("input_tokens", 0), "cached_input": u.get("cache_read_input_tokens", 0) or 0,
                             "cache_write": u.get("cache_creation_input_tokens", 0) or 0, "output": u.get("output_tokens", 0)},
                      raw={"usage": u, "stop_reason": resp.get("stop_reason")})


class AnthropicBatch(Anthropic):
    """Message Batches API: 50% price, asynchronous (provider guarantees < 24 h). The queue lives
    server-side, so an interrupted local process loses nothing: batch ids are saved and collected later."""
    name = "anthropic-batch"
    BURL = "https://api.anthropic.com/v1/messages/batches"

    def settings(self):
        return {**super().settings(), "endpoint": "v1/messages/batches (batch tier, 50% price)"}

    def submit(self, requests: list[dict]) -> dict:
        resp, _ = _post(self.BURL, self.headers(), {"requests": requests}, timeout=300)
        return resp

    def status(self, batch_id: str) -> dict:
        return json.loads(_get(f"{self.BURL}/{batch_id}", self.headers()).decode("utf-8"))

    def results(self, results_url: str):
        for line in _get(results_url, self.headers(), timeout=600).decode("utf-8").splitlines():
            if line.strip():
                yield json.loads(line)


class OpenAI:
    name = "openai"
    URL = "https://api.openai.com/v1/responses"

    def __init__(self, model, effort="none"):
        self.model, self.effort = model, effort

    def settings(self):
        return {"provider": self.name, "model": self.model, "reasoning.effort": self.effort,
                "endpoint": "v1/responses (standard tier)", "structured_output": "text.format json_schema strict"}

    def complete(self, system, user, schema, max_tokens) -> Result:
        body = {"model": self.model, "max_output_tokens": max_tokens, "reasoning": {"effort": self.effort},
                "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "text": {"format": {"type": "json_schema", "name": "result", "schema": schema, "strict": True}}}
        resp, _ = _post(self.URL, {"authorization": "Bearer " + _key("OPENAI_API_KEY")}, body)
        u = resp.get("usage", {}) or {}
        cached = (u.get("input_tokens_details") or {}).get("cached_tokens", 0) or 0
        text, refusal = "", ""
        for item in resp.get("output", []):
            for c in item.get("content", []) or []:
                if c.get("type") == "output_text":
                    text += c.get("text", "")
                elif c.get("type") == "refusal":
                    refusal = c.get("refusal", "refusal")
        stop = "refusal" if refusal else ("max_tokens" if resp.get("status") == "incomplete" else "end_turn")
        # OpenAI input_tokens INCLUDES cached tokens; reasoning is already inside output_tokens.
        return Result(text=text, stop_reason=stop, provider_request_id=resp.get("id", ""),
                      usage={"input": u.get("input_tokens", 0) - cached, "cached_input": cached, "cache_write": 0,
                             "output": u.get("output_tokens", 0)}, raw={"usage": u, "status": resp.get("status")})


class Jev:
    """TypeSafe Jev: one review (state) per call, several Choice questions per call."""
    name = "jev"
    URL = "https://api.typesafe.ai/v1/systemone"

    def __init__(self, model="jev-latest"):
        self.model = model

    def settings(self):
        return {"provider": self.name, "model": self.model, "endpoint": "v1/systemone", "primitives": "choice x3"}

    def ask(self, state, questions) -> tuple[dict, dict, str]:
        resp, _ = _post(self.URL, {"authorization": "Bearer " + _key("TYPESAFE_API_KEY")},
                        {"state": state, "model": self.model, "questions": questions}, timeout=60)
        u = resp.get("usage", {}) or {}
        return resp.get("answers", {}), {"input": u.get("input_tokens", 0), "cached_input": 0, "cache_write": 0,
                                         "output": u.get("output_tokens", 0)}, resp.get("model", self.model)


# ---------------------------------------------------------------------------
class Mock:
    """FREE offline stand-in used only for tests. Labels are keyword rules, usage is
    synthetic, and its label_config starts with 'mock:' so exports refuse it as real."""
    name = "mock"

    def __init__(self, model="mock-keywords", effort="none", fail_rate=0.0, seed=0):
        self.model, self.effort, self.fail_rate = model, effort, fail_rate
        self.rng = random.Random(seed)

    def settings(self):
        return {"provider": "mock", "model": self.model, "note": "synthetic test provider, not a real model"}

    RULES = [
        (r"premium|pay|skip|subscription|price|expensive|money|charg", "billing.premium_paywall", 3),
        (r"\bads?\b|advert", "usability.ads", 3),
        (r"crash|won'?t open|not opening|stops? playing|not playing|can'?t play", "playback.crash_or_wont_open", 4),
        (r"log ?in|password|logged out|account", "access.login_failure", 4),
        (r"download|offline", "downloads.download_fails", 3),
        (r"lyric", "catalog.lyrics", 3),
        (r"shuffle|update|layout|interface", "usability.ui_redesign_or_navigation", 2),
        (r"song|artist|search|podcast", "catalog.missing_or_removed_content", 2),
    ]

    def complete(self, system, user, schema, max_tokens) -> Result:
        time.sleep(0.01)
        if self.rng.random() < self.fail_rate:
            raise TransportError("mock 529 overloaded", status=529)
        items = json.loads(user[user.index("["):])
        for it in items:
            it.setdefault("id", it.get("k"))
        out = []
        for it in items:
            t = it["text"]
            low = t.lower()
            label, sev = "other.general_praise", 1
            neg = re.search(r"bad|worst|hate|terrible|poor|sucks|annoy|useless|waste|can'?t|not|never", low)
            for pat, lab, s in self.RULES:
                if re.search(pat, low):
                    label, sev = lab, s
                    break
            intent = "complaint" if neg or sev >= 3 else "praise"
            if re.search(r"uninstall|deleting|cancel|switch(ing)? to", low):
                intent = "cancellation"
            if label == "other.general_praise" and intent == "complaint":
                label, sev = "other.general_criticism", 2
            if intent == "praise":
                sev = 1
            if "verification" in system[:200].lower():
                out.append({"id": it["id"], "topic": label.split(".")[0], "intent": intent, "sev": sev})
            else:
                words = t.split()
                out.append({"k": it["id"], "label": label, "intent": intent, "sev": sev,
                            "sent": -0.5 if intent in ("complaint", "cancellation") else 1, "quote": " ".join(words[:12]) or t,
                            "flag": False})
        if self.rng.random() < self.fail_rate and len(out) > 1:
            out.pop()  # simulate a missing ID in an otherwise valid response
        text = json.dumps({"results": out}, ensure_ascii=False)
        return Result(text=text, stop_reason="end_turn", provider_request_id="mock-" + uuid.uuid4().hex[:12],
                      usage={"input": len(system + user) // 4, "cached_input": 0, "cache_write": 0, "output": len(text) // 4})

    def ask(self, state, questions):
        r = self.complete("verification", "x" + json.dumps([{"id": "x", "text": state}]), None, 0)
        o = json.loads(r.text)["results"][0]
        sev_names = {1: "s1_no_problem", 2: "s2_annoyance", 3: "s3_degraded", 4: "s4_blocked", 5: "s5_serious_harm"}
        answers = {"topic": {"choice": o["topic"]}, "intent": {"choice": o["intent"]}, "severity": {"choice": sev_names[o["sev"]]}}
        return answers, {"input": len(state) // 4 + 300, "cached_input": 0, "cache_write": 0, "output": 15}, "mock-jev"


def make(provider: str, model: str, effort: str = "low", **kw):
    if provider == "anthropic":
        return Anthropic(model, effort)
    if provider == "anthropic-batch":
        return AnthropicBatch(model, effort)
    if provider == "openai":
        return OpenAI(model, effort)
    if provider == "jev":
        return Jev(model)
    if provider == "mock":
        return Mock(model, effort, fail_rate=kw.get("mock_fail_rate", 0.0), seed=kw.get("seed", 0))
    raise SystemExit(f"Unknown provider {provider!r} (allowlist: anthropic, openai, jev, mock)")


def stable_id(*parts) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16]
