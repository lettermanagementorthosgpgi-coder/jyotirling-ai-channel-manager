"""Official OpenAI and Gemini text/image API adapters.

Credentials are read only from environment variables. API keys are never logged
or written to reports, source files, or generated artifacts.
"""
from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request

from PIL import Image


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
        raise ProviderError(f"HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise ProviderError(f"Request failed: {type(exc).__name__}: {exc}") from exc


def available_providers():
    providers = [
        name for name, key in (
            ("openai", "OPENAI_API_KEY"),
            ("gemini", "GEMINI_API_KEY"),
        ) if os.getenv(key)
    ]
    if os.getenv("CLOUDFLARE_API_TOKEN") and os.getenv("CLOUDFLARE_ACCOUNT_ID"):
        providers.append("cloudflare")
    return providers


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

    if provider == "cloudflare":
        token = os.getenv("CLOUDFLARE_API_TOKEN")
        account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        if not token or not account_id:
            raise ProviderError("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are required")
        model = os.getenv("CLOUDFLARE_MODEL", "@cf/meta/llama-3.2-1b-instruct")
        data = _post(
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}",
            {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            {"messages": [{"role": "system", "content": "You are the third independent reviewer for Jyotirling Shivmath. Be factual and careful."},
                          {"role": "user", "content": prompt}]})
        if not data.get("success", False):
            raise ProviderError(f"Cloudflare Workers AI returned errors: {data.get('errors', [])}")
        result = (data.get("result") or {}).get("response", "")
        if not result:
            raise ProviderError("Cloudflare Workers AI returned no text")
        return result, model

    raise ProviderError(f"Unknown provider: {provider}")


def _extract_gemini_image(data):
    """Support documented Interactions API output_image and model_output steps."""
    direct = data.get("output_image") or {}
    if isinstance(direct, dict) and direct.get("data"):
        return direct["data"]

    for step in data.get("steps", []):
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        for block in step.get("content", []):
            if isinstance(block, dict) and block.get("type") == "image" and block.get("data"):
                return block["data"]

    for step in data.get("outputs", []):
        if isinstance(step, dict) and step.get("type") == "image" and step.get("data"):
            return step["data"]
    return None


def _normalize_image_to_png(image_bytes):
    """Normalize provider image bytes to PNG for the downstream composer."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            converted = source.convert("RGB")
            output = io.BytesIO()
            converted.save(output, format="PNG")
            return output.getvalue()
    except Exception as exc:
        raise ProviderError(
            f"Image payload could not be decoded/converted to PNG: {type(exc).__name__}: {exc}"
        ) from exc


def generate_thumbnail_background(provider, prompt):
    """Generate a 16:9 PNG background and return (bytes, model)."""
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
        return _normalize_image_to_png(base64.b64decode(encoded)), model

    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ProviderError("GEMINI_API_KEY is not configured")
        model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
        # This endpoint currently accepts JPEG, not image/png, for response_format.
        data = _post("https://generativelanguage.googleapis.com/v1beta/interactions", {
            "x-goog-api-key": key, "Content-Type": "application/json"
        }, {"model": model, "input": prompt,
            "response_format": {"type": "image", "mime_type": "image/jpeg",
                                "aspect_ratio": "16:9", "image_size": "2K"}},
            timeout=240)
        encoded = _extract_gemini_image(data)
        if not encoded:
            raise ProviderError("Gemini image API returned no image data")
        return _normalize_image_to_png(base64.b64decode(encoded)), model

    raise ProviderError(f"Unknown image provider: {provider}")
