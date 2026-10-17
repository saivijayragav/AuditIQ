"""Constrained LLM layer for the mapping cascade (optional, off by default).

Ported from the legacy ``LLM`` class: an OpenAI-compatible client (Google Gemini
endpoint by default), a strict JSON answer contract, exponential-backoff retries
for transient errors, and a disk cache so runs are reproducible and re-runnable.

The layer is only instantiated when a mapping run explicitly enables it *and* an
API key is configured; all other runs stay fully deterministic.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Optional, Sequence

from ...settings import GOOGLE_API_KEY, LLM_MODEL

SYSTEM = (
    "You classify ledger heads from an Indian company's trial balance into financial statement "
    "line items (FSLIs) of Schedule III of the Companies Act, 2013. Answer ONLY with JSON: "
    '{"code": "<one code from the candidate list, or UNKNOWN>", "confidence": <number from 0 to 1>}. '
    "Use UNKNOWN if the head cannot be classified from the information given. Never invent codes."
)

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def parse_answer(text: str) -> tuple[str, float]:
    """Parse the model's JSON answer into ``(code, confidence)``."""
    if not text:
        return "UNKNOWN", 0.0
    try:
        match = re.search(r"\{.*?\}", text, re.S)
        if match:
            data = json.loads(match.group(0))
            code = str(data.get("code", "UNKNOWN")).strip()
            conf = min(1.0, max(0.0, float(data.get("confidence", 0))))
            return code, conf
    except Exception:
        pass
    code_match = re.search(r'"code"\s*:\s*"([^"]+)"', text)
    conf_match = re.search(r'"confidence"\s*:\s*([0-9.]+)', text)
    if code_match:
        code = code_match.group(1).strip()
        conf = float(conf_match.group(1)) if conf_match else 0.8
        return code, min(1.0, max(0.0, conf))
    return "UNKNOWN", 0.0


class LLM:
    """OpenAI-compatible chat client with retry, disk cache and token accounting."""

    def __init__(
        self,
        model: str = LLM_MODEL,
        cache_path: str = "llm_cache.json",
        run: int = 0,
        api_key: Optional[str] = None,
        base_url: str = _DEFAULT_BASE_URL,
    ):
        from openai import (  # lazy import; only needed when the layer is enabled
            APIConnectionError,
            APITimeoutError,
            InternalServerError,
            OpenAI,
            RateLimitError,
        )

        self._errors = (RateLimitError, APIConnectionError, InternalServerError, APITimeoutError)
        key = (api_key or GOOGLE_API_KEY or "").strip()
        if not key:
            raise RuntimeError("GOOGLE_API_KEY is not set; cannot enable the LLM mapping layer")
        if model.startswith("google/"):
            model = model[len("google/") :]
        self.client = OpenAI(api_key=key, base_url=base_url, timeout=25.0)
        self.model = model
        self.run = run
        self.path = cache_path
        self.dirty = 0
        self.cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
        self.reset()

    def reset(self) -> None:
        self.calls = self.tin = self.tout = 0

    def flush(self) -> None:
        with open(self.path, "w") as handle:
            json.dump(self.cache, handle)
        self.dirty = 0

    def _create(self, kwargs: dict):
        last_exc: Optional[BaseException] = None
        for attempt in range(5):
            try:
                return self.client.chat.completions.create(temperature=0, **kwargs)
            except self._errors as exc:
                print(f"[LLM] rate-limit/connection error (attempt {attempt + 1}/5): {exc}")
                time.sleep(3 * (2**attempt))
                last_exc = exc
            except Exception as exc:  # non-transient: don't retry
                print(f"[LLM] unexpected error (attempt {attempt + 1}/5): {type(exc).__name__}: {exc}")
                last_exc = exc
                break
        assert last_exc is not None, "all retries exhausted but no exception was captured"
        raise last_exc

    def ask(self, head, candidates: Sequence[tuple[str, str]]) -> dict:
        """Ask the model to classify ``head`` against ``candidates`` (code, text)."""
        lines = "\n".join(f"- {code}: {text}" for code, text in candidates)
        prompt = (
            f'Ledger head: "{head.raw_name}"\n'
            f'Parent group / account type: "{head.group or "not available"}"\n'
            f"Source system: {head.source}\nBalance side: {head.side}\n"
            f"Candidate FSLIs:\n{lines}\n"
        )
        key = hashlib.sha256(f"{self.model}|{self.run}|{SYSTEM}|{prompt}".encode()).hexdigest()
        entry = self.cache.get(key)
        if entry is None:
            t0 = time.perf_counter()
            try:
                response = self._create(
                    dict(
                        model=self.model,
                        max_tokens=120,
                        messages=[
                            {"role": "system", "content": SYSTEM},
                            {"role": "user", "content": prompt},
                        ],
                    )
                )
                text = response.choices[0].message.content
                code, conf = parse_answer(text)
                entry = dict(
                    code=code,
                    conf=conf,
                    latency=time.perf_counter() - t0,
                    tin=response.usage.prompt_tokens,
                    tout=response.usage.completion_tokens,
                    temp0=True,
                    raw=text,
                )
                self.cache[key] = entry
                self.dirty += 1
                if self.dirty >= 5:
                    self.flush()
            except self._errors as exc:
                print(f"[LLM] giving up on this record (rate-limited): {exc.__class__.__name__}")
                entry = dict(
                    code="UNKNOWN",
                    conf=0.0,
                    latency=time.perf_counter() - t0,
                    tin=0,
                    tout=0,
                    temp0=True,
                    raw="",
                )
        self.calls += 1
        self.tin += entry["tin"]
        self.tout += entry["tout"]
        return entry


def llm_available() -> bool:
    """True when an API key is configured and the ``openai`` client is importable."""
    if not GOOGLE_API_KEY:
        return False
    try:
        import openai  # noqa: F401

        return True
    except Exception:
        return False
