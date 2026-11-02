"""Official OpenAI and Gemini text/image API adapters.

Credentials are read only from environment variables. API keys are never logged
or written to reports, source files, or generated artifacts.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request


class ProviderError(RuntimeError):
    pass


def _post(url, headers, body, timeout=120):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        # Never include request headers or credentials in an error message.
        raise ProviderError(f"HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise ProviderError(f"Request failed: {type(exc).__name__}: {exc}") from exc


def available_providers():
    return [name for name, key in (
        ("openai", "OPENAI_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
    ) if os.getenv(key)]


def generate(provider, prompt):
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ProviderError("OPENAI_API_KEY is not configured")
        model = os.getenv("OPENAI_MODEL", "gpt-6-luna")
        data = _post("https://api.openai.com/v1/responses", {
            "Authorization": f"Bearer {key}", "Content-Type": "application/json"
        }, {"model": model, "input": prompt, "max_output_tokens": 5000})
        parts = []
        for item in data.get("output", []):
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    parts.append(part.get("text", ""))
        result = "\n".join(parts) or data.get("output_text", "")
        if not result:
            raise ProviderError("OpenAI returned no text")
        return result, model

    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ProviderError("GEMINI_API_KEY is not configured")
        model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        data = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            {"x-goog-api-key": key, "Content-Type": "application/json"},
            {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
             "generationConfig": {"maxOutputTokens": 5000}})
        candidates = data.get("candidates", [])
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        result = "\n".join(p.get("text", "") for p in parts if p.get("text"))
        if not result:
            raise ProviderError("Gemini returned no text")
        return result, model

    raise ProviderError(f"Unknown provider: {provider}")


def generate_thumbnail_background(provider, prompt):
    """Generate a 16:9 background image and return (bytes, model)."""
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ProviderError("OPENAI_API_KEY is not configured")
        model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare")
        data = _post("https://api.openai.com/v1/images/generations", {
            "Authorization": f"Bearer {key}", "Content-Type": "application/json"
        }, {"model": model, "prompt": prompt, "size": "1536x864",
            "quality": "medium", "output_format": "png", "n": 1}, timeout=180)
        images = data.get("data", [])
        encoded = images[0].get("b64_json") if images else None
        if not encoded:
            raise ProviderError("OpenAI image API returned no image data")
        return base64.b64decode(encoded), model

    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ProviderError("GEMINI_API_KEY is not configured")
        model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
        data = _post("https://generativelanguage.googleapis.com/v1beta/interactions", {
            "x-goog-api-key": key, "Content-Type": "application/json"
        }, {"model": model, "input": prompt,
            "response_format": {"type": "image", "mime_type": "image/png",
                                "aspect_ratio": "16:9", "image_size": "2K"}},
            timeout=240)
        output_image = data.get("output_image") or {}
        encoded = output_image.get("data")
        if not encoded:
            # Some responses expose image data inside output content blocks.
            for step in data.get("outputs", []):
                if isinstance(step, dict) and step.get("type") == "image":
                    encoded = step.get("data")
                    if encoded:
                        break
        if not encoded:
            raise ProviderError("Gemini image API returned no image data")
        return base64.b64decode(encoded), model

    raise ProviderError(f"Unknown image provider: {provider}")
