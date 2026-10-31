"""Anthropic SDK wrapper: per-analysis call budget, prompt caching, result cache, usage/cost,
and a single `LLMUnavailable` signal that triggers the offline (degraded) path."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import anthropic

from app.agents.schemas import LLMUsage
from app.config import get_settings

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "generated" / "llm_cache"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMUnavailable(RuntimeError):
    """The LLM cannot be used for this request; callers switch to rule-based reasoning."""


def models() -> tuple[str, str]:
    cfg = get_settings().llm
    return (os.environ.get("ANTHROPIC_MODEL") or cfg.default_model,
            os.environ.get("ANTHROPIC_MODEL_FAST") or cfg.default_fast_model)


def resolve_mode() -> tuple[str, str | None]:
    """('online'|'degraded', reason). auto = online only when credentials are configured."""
    mode = os.environ.get("LLM_MODE", "auto").lower()
    if mode == "offline":
        return "degraded", "LLM_MODE=offline"
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    if mode == "online" or has_key:
        return "online", None
    return "degraded", "no ANTHROPIC_API_KEY configured"


def cache_key(*parts: Any) -> str:
    blob = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


class LLMSession:
    """One analysis run's view of the LLM: budget, usage and cache."""

    def __init__(self, client: Any | None = None, mode: str | None = None, cache_dir: Path | None = CACHE_DIR) -> None:
        cfg = get_settings().llm
        resolved, reason = resolve_mode()
        if mode is not None and mode != resolved:
            reason = None if mode == "online" else "forced offline"
        self.mode = mode or resolved
        self.model, self.fast_model = models()
        self.usage = LLMUsage(mode="online" if self.mode == "online" else "degraded", degraded_reason=reason,
                              model=self.model, fast_model=self.fast_model)
        self.budget = cfg.max_calls_per_analysis
        self.cache_dir = cache_dir
        self._client = client
        if self.mode == "online" and self._client is None:
            try:
                self._client = anthropic.Anthropic(timeout=cfg.timeout_s, max_retries=1)
            except Exception as e:  # missing credentials etc.
                self.degrade(f"client init failed: {type(e).__name__}")

    @property
    def online(self) -> bool:
        return self.mode == "online" and self._client is not None

    def degrade(self, reason: str) -> None:
        self.mode = "degraded"
        self.usage.mode = "degraded"
        self.usage.degraded_reason = reason

    # ---------------------------------------------------------------- result cache
    def cache_get(self, key: str) -> Any | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            self.usage.cache_hits += 1
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def cache_put(self, key: str, value: Any) -> None:
        if self.cache_dir is None:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / f"{key}.json").write_text(json.dumps(value, default=str), encoding="utf-8")

    # ---------------------------------------------------------------- calls
    def create(self, *, system: str, messages: list[dict[str, Any]], fast: bool = False,
               tools: list[dict[str, Any]] | None = None, schema: dict[str, Any] | None = None,
               effort: str | None = None, max_tokens: int | None = None) -> Any:
        if not self.online:
            raise LLMUnavailable(self.usage.degraded_reason or "offline")
        if self.usage.calls >= self.budget:
            raise self._fail(f"call budget of {self.budget} per analysis exhausted")
        cfg = get_settings().llm
        model = self.fast_model if fast else self.model
        output_config: dict[str, Any] = {"effort": effort or cfg.effort}
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens or cfg.max_tokens,
            # Stable system prompt first, cached; volatile evidence goes in messages.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "output_config": output_config,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = {"type": "auto"}  # forced tool_choice is rejected on current models
        if not fast:
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        self.usage.calls += 1
        try:
            client: Any = self._client
            msg = client.beta.messages.create(**kwargs) if not fast else client.messages.create(**kwargs)
        except anthropic.AuthenticationError as e:
            raise self._fail("authentication failed") from e
        except anthropic.PermissionDeniedError as e:
            raise self._fail("permission denied") from e
        except anthropic.NotFoundError as e:
            raise self._fail(f"model not found: {model}") from e
        except anthropic.RateLimitError as e:
            raise self._fail("rate limited") from e
        except anthropic.BadRequestError as e:
            raise self._fail(f"bad request: {e.message[:120]}") from e
        except anthropic.APIStatusError as e:
            raise self._fail(f"API error {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise self._fail("network unavailable") from e
        except Exception as e:  # e.g. TypeError when no credentials resolve: never let the demo crash
            if "authentication" in str(e).lower():
                raise self._fail("no API credentials (set ANTHROPIC_API_KEY)") from e
            raise self._fail(f"client error: {type(e).__name__}") from e
        self._record(msg, model)
        if getattr(msg, "stop_reason", None) == "refusal":
            raise self._fail("model declined the request")
        return msg

    def _fail(self, reason: str) -> LLMUnavailable:
        self.degrade(reason)
        return LLMUnavailable(reason)

    def _record(self, msg: Any, model: str) -> None:
        u = getattr(msg, "usage", None)
        if u is None:
            return
        inp = int(getattr(u, "input_tokens", 0) or 0)
        out = int(getattr(u, "output_tokens", 0) or 0)
        cread = int(getattr(u, "cache_read_input_tokens", 0) or 0)
        cwrite = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
        self.usage.input_tokens += inp
        self.usage.output_tokens += out
        self.usage.cache_read_tokens += cread
        self.usage.cache_write_tokens += cwrite
        price = get_settings().llm.pricing.get(model)
        if price:
            p_in, p_out, p_read = price
            self.usage.cost_usd = round(
                self.usage.cost_usd + (inp * p_in + cwrite * p_in * 1.25 + out * p_out + cread * p_read) / 1e6, 5)


def text_of(msg: Any) -> str:
    return "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")


def tool_uses(msg: Any) -> list[Any]:
    return [b for b in msg.content if getattr(b, "type", "") == "tool_use"]
