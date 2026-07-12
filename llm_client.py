"""Shared low-level Gemini API calling logic, used by synthesize.py and title_filter.py."""

import json
import logging

import requests

from config import GEMINI_API_KEY, GEMINI_API_URL

logger = logging.getLogger("llm_client")


def call_gemini_raw(system_instruction, user_prompt, temperature=0.2, timeout=30):
    """Calls Gemini and returns the raw text response. Raises on failure --
    callers decide how to handle errors (retry, skip, default, etc.)."""
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Run: export GEMINI_API_KEY=\"your-key-here\""
        )

    body = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    resp = requests.post(
        GEMINI_API_URL,
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
        json=body,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def parse_json_response(text):
    """Strips accidental markdown fences and parses JSON."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())
