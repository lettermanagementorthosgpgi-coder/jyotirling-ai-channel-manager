"""Small server-side adapters for OpenAI, Gemini and Anthropic APIs.

Credentials are read only from environment variables. No API key is ever written
to reports, logs, source files, or the browser.
"""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request


class ProviderError(RuntimeError):
    pass


def _post(url, headers, body, timeout=90):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise ProviderError(f"HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise ProviderError(str(exc)) from exc


def available_providers():
    return [name for name, key in (
        ("openai", "OPENAI_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
    ) if os.getenv(key)]


def generate(provider, prompt):
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key: raise ProviderError("OPENAI_API_KEY is not configured")
        model = os.getenv("OPENAI_MODEL", "gpt-6-luna")
        data = _post("https://api.openai.com/v1/responses", {
            "Authorization": f"Bearer {key}", "Content-Type": "application/json"
        }, {"model": model, "input": prompt, "max_output_tokens": 5000})
        parts = []
        for item in data.get("output", []):
            for part in item.get("content", []):
                if part.get("type") == "output_text": parts.append(part.get("text", ""))
        result = "\n".join(parts) or data.get("output_text", "")
        if not result: raise ProviderError("OpenAI returned no text")
        return result, model

    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if not key: raise ProviderError("GEMINI_API_KEY is not configured")
        model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        data = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            {"x-goog-api-key": key, "Content-Type": "application/json"},
            {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
             "generationConfig": {"maxOutputTokens": 5000}})
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        result = "\n".join(p.get("text", "") for p in parts if p.get("text"))
        if not result: raise ProviderError("Gemini returned no text")
        return result, model

    if provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key: raise ProviderError("ANTHROPIC_API_KEY is not configured")
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
        data = _post("https://api.anthropic.com/v1/messages", {
            "x-api-key": key, "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }, {"model": model, "max_tokens": 5000,
            "messages": [{"role": "user", "content": prompt}]})
        result = "\n".join(p.get("text", "") for p in data.get("content", [])
                            if p.get("type") == "text")
        if not result: raise ProviderError("Anthropic returned no text")
        return result, model

    raise ProviderError(f"Unknown provider: {provider}")
