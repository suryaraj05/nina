from ollama_client import safe_json
from gemini_client import generate

INTENT_PROMPT = """
You are an intent parser for a web navigation agent.
Extract structured data from what the user said.

Known pages on this site:
{sitemap_summary}

Recent conversation:
{session_context}

User's recent actions on this site:
{user_context}

User said: "{user_input}"

Reply ONLY with a JSON object — no explanation, no markdown:
{{
  "intent": "signup|login|navigate|search|click|fill|query|add_to_cart|other",
  "params": {{
    "email":    null,
    "password": null,
    "name":     null,
    "query":    null,
    "page":     null,
    "product":  null
  }},
  "target_hint": "describe target page in 1-3 words"
}}

CRITICAL RULES:
- If user says "add to cart", "add X to cart", "put X in cart", "add this/that to cart" → intent MUST be "add_to_cart". Set "product" to the product name if mentioned (e.g. "polo shirt", "classic hoodie").
- If user says "create account", "sign up", "register", "make an account" → intent MUST be "signup"
- If user says "log in", "sign in", "login" → intent MUST be "login"
- If user asks "what", "show me", "list", "what are", "what's available" → intent MUST be "query"
- "fill" intent is ONLY for filling forms on pages you're already on (not for account creation)
- "query" intent is for asking questions about the current page or available options
- Only include param values explicitly mentioned by the user.
- Use null for anything not mentioned.
- intent must be exactly one of the enum values above.
- target_hint should be descriptive: "signup page", "login page", "homepage", "current page", etc.
"""


def build_intent_prompt(
    user_input: str,
    sitemap_summary: str,
    session_context: str = "No previous conversation.",
    user_context: str = "No previous actions."
) -> str:
    return INTENT_PROMPT.format(
        user_input=user_input,
        sitemap_summary=sitemap_summary,
        session_context=session_context,
        user_context=user_context,
    )


async def parse_intent(
    user_input: str,
    sitemap_summary: str = "No pages discovered yet.",
    session_context: str = "No previous conversation.",
    user_context: str = "No previous actions."
) -> dict:
    prompt = build_intent_prompt(
        user_input=user_input,
        sitemap_summary=sitemap_summary,
        session_context=session_context,
        user_context=user_context,
    )
    raw = await generate(prompt)
    return safe_json(raw)

