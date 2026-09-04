"""Thin client for Groq's free, OpenAI-compatible chat completions API.

Used as the $0 open-weight "brain" for both the benchmarks/agent_eval task suite and
the interactive graphcode chat agent (graphcode/mcp/client.py) — a real open-weight
model, no paid API key required (Groq's free tier publishes real per-model rate
limits: https://console.groq.com/docs/rate-limits).

Requires GROQ_API_KEY in the environment (free signup, no card: console.groq.com/keys).

Note: llama-3.3-70b-versatile was deprecated by Groq on 2026-06-17. DEFAULT_MODEL is
openai/gpt-oss-120b, Groq's recommended replacement (still free tier, 131k context,
supports tool calling).
"""

from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv

load_dotenv()  # picks up GROQ_API_KEY from a local, gitignored .env if present

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"


class GroqNotConfigured(RuntimeError):
    pass


def _post(payload: dict) -> dict:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise GroqNotConfigured(
            "GROQ_API_KEY not set. Free signup (no card): https://console.groq.com/keys"
        )
    resp = httpx.post(
        GROQ_API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def chat_with_tools(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    tool_choice: str = "auto",
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 3000,
) -> tuple[dict, dict]:
    """Returns (assistant_message, usage_dict). assistant_message may contain
    'content' (str | None) and/or 'tool_calls' (list[dict])."""
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice
    data = _post(payload)
    message = data["choices"][0]["message"]
    usage = data.get("usage", {})
    return message, usage


def chat(
    messages: list[dict],
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 3000,
) -> tuple[str, dict]:
    """Returns (message_content, usage_dict). Convenience wrapper with no tool calling."""
    message, usage = chat_with_tools(
        messages, tools=None, model=model, temperature=temperature, max_tokens=max_tokens
    )
    return message.get("content") or "", usage
