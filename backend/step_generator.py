import json
from gemini_client import generate

STEP_PROMPT = """
You are a browser automation planner.

User intent: {intent}
User provided values: {params}

Available fields on the current page:
{field_registry}

Generate an ordered JSON array of browser steps.
Reply ONLY with the JSON array — no explanation, no markdown.

Valid actions: navigate, fill, click, check

Schema:
  fill:     {{"action": "fill",     "selector": "...", "value": "..."}}
  click:    {{"action": "click",    "selector": "..."}}
  check:    {{"action": "check",    "selector": "..."}}
  navigate: {{"action": "navigate", "url":      "..."}}

Rules:
  - ONLY use selectors from the field list above. Never invent selectors.
  - Skip any field where the user value is null.
  - If confirmPassword field exists, set it to the same value as password.
  - Always place the submit/click step LAST.
  - For checkboxes use action check not click.
"""

async def generate_steps(intent: str, params: dict, field_registry: dict) -> list:
    fields_str = json.dumps(field_registry["fields"], indent=2)
    params_str = json.dumps({k: v for k, v in params.items() if v is not None})
    prompt = STEP_PROMPT.format(
        intent=intent,
        params=params_str,
        field_registry=fields_str
    )
    raw = await generate(prompt)
    return json.loads(raw)

