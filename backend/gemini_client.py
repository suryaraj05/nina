from __future__ import annotations

import asyncio
import os
from typing import Optional

from google import genai


async def generate(prompt: str, system: str = "") -> str:
    """
    Drop-in replacement for the Ollama client, using Gemini 1.5 Flash.

    This implementation uses the newer `google.genai` client instead of the
    deprecated `google.generativeai` package.
    """
    api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in environment")

    # Client is cheap to construct; keep it simple and re-create per call.
    client = genai.Client(api_key=api_key)

    # Map our simple temperature/max_tokens config to the new client.
    config = genai.types.GenerateContentConfig(
        temperature=0.1,
        max_output_tokens=512,
    )

    # Run the blocking client call in a thread so our interface stays async.
    response = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-1.5-flash",
        contents=prompt,
        config=config if system == "" else genai.types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=512,
            system_instruction=system,
        ),
    )

    # `google-genai` responses expose helper to get concatenated text.
    # Fall back gracefully if the helper isn't present.
    if hasattr(response, "output_text"):
        return response.output_text
    if hasattr(response, "text"):
        return response.text  # type: ignore[attr-defined]
    # Last resort: string representation
    return str(response)
