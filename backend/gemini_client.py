from __future__ import annotations

import asyncio
import os
from typing import Optional

import google.generativeai as genai


async def generate(prompt: str, system: str = "") -> str:
    """
    Drop-in replacement for the Ollama client, using Gemini 1.5 Flash.

    Args:
        prompt:  The main user/content prompt.
        system:  Optional system instruction to steer behavior.

    Returns:
        The raw text response from Gemini.
    """
    api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in environment")

    genai.configure(api_key=api_key)

    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config={
            "temperature": 0.1,
            "max_output_tokens": 512,
        },
        # If system is empty, let the model use its default behavior
        system_instruction=system or None,
    )

    # Run the blocking generate_content call in a thread to keep things async-friendly
    response = await asyncio.to_thread(model.generate_content, prompt)
    # google-generativeai returns a rich object; .text gives the concatenated text parts
    return response.text


