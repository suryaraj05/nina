from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from ollama_client import call_qwen, safe_json
from nfs_schema import NFSTree, NFSPage, NFSAction, NFSExecution, NFSProduct, NFSAuth


def _extract_domain(base_url: str) -> str:
    parsed = urlparse(base_url)
    return parsed.netloc


def _build_schema_snippet() -> str:
    """
    Lightweight textual description of the NFSTree schema for the LLM prompt.
    Avoids tight coupling to Python representation while giving the model structure.
    """
    return """
NFSTree JSON schema (conceptual):
{
  "domain": string,
  "base_url": string,
  "auth": {
    "login_url": string | null,
    "session_check": {
      "type": string,
      "key": string,
      "field": string,
      "expected_value": string
    } | null,
    "login_fields": { [logical_name: string]: string }
  } | null,
  "pages": {
    [page_id: string]: {
      "url_pattern": string,
      "label": string,
      "keywords": string[],
      "content_type": string,
      "products": [{
        "id": string,
        "name": string,
        "price": number | null,
        "image": string | null,
        "detail_url": string
      }],
      "actions": [{
        "name": string,
        "description": string | null,
        "requires_auth": boolean,
        "trigger_intents": string[],   // signup|login|navigate|search|add_to_cart|query|other
        "params": string[],
        "execution": {
          "type": "navigate" | "api_call" | "fill_form" | "click",
          "url_template": string | null,
          "method": string | null,
          "endpoint": string | null,
          "body_template": object | null,
          "field_registry": object | null,
          "submit_selector": string | null,
          "success_redirect": string | null,
          "selector": string | null
        },
        "fallback": (same shape as execution) | null
      }]
    }
  },
  "created_at": string,   // ISO timestamp,
  "version": number
}
""".strip()


def _format_raw_sitemap(raw_sitemap: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for page in raw_sitemap:
        url = page.get("url")
        title = page.get("title")
        keywords = page.get("keywords") or []
        products = page.get("products") or []
        lines.append(f"- URL: {url}")
        if title:
            lines.append(f"  Title: {title}")
        if keywords:
            lines.append(f"  Keywords: {', '.join(map(str, keywords))}")
        if products:
            prod_summaries = []
            for p in products:
                name = p.get("name") or p.get("title") or ""
                price = p.get("price")
                if price is not None:
                    prod_summaries.append(f"{name} (${price})")
                else:
                    prod_summaries.append(str(name))
            lines.append(f"  Products: {', '.join(prod_summaries)}")
    return "\n".join(lines)


async def build_nfs_from_raw(
    base_url: str,
    raw_sitemap: List[Dict[str, Any]],
    api_docs: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Use the LLM to convert a raw sitemap + optional API docs into an NFSTree JSON dict.
    This is used only during onboarding, never from /run.
    """
    domain = _extract_domain(base_url)
    sitemap_str = _format_raw_sitemap(raw_sitemap)
    schema_str = _build_schema_snippet()

    api_docs_section = ""
    if api_docs:
        api_docs_section = f"\n\nAPI Docs:\n{api_docs}\n"

    prompt = f"""
You are designing a navigation function schema (NFS) for a web automation agent.

Base URL: {base_url}
Domain: {domain}

Raw sitemap pages:
{sitemap_str}

{api_docs_section}

NFSTree schema (for reference, you MUST follow this structure):
{schema_str}

TASK:
- Convert the information above into a single NFSTree JSON object.
- For each page, identify:
  - url_pattern (relative path or pattern for the page)
  - label: short human-readable name
  - keywords: important terms describing the page
  - content_type: e.g. "auth", "product_list", "product_detail", "cart", "info", etc.
  - products: list of products/items found on that page (if any)
  - actions: list of actions the agent can perform on that page
- For each action, decide:
  - name and description
  - trigger_intents (choose from: signup|login|navigate|search|add_to_cart|query|other)
  - whether requires_auth is true or false
  - execution.type (one of: navigate|api_call|fill_form|click)
  - execution.url_template / endpoint / method / field_registry / selector as needed
- If there is a login or signup page, include an auth section with login_url, session_check, and login_fields.

CRITICAL INSTRUCTIONS:
- Return ONLY valid JSON matching the NFSTree schema.
- Do NOT include any comments, explanation, or markdown.
- Ensure every action has an execution object with a valid "type".
""".strip()

    # NOTE: call_qwen currently uses temperature=0.1 and num_predict=512 internally.
    # For onboarding we conceptually want a higher num_predict (2048), but we keep
    # the single call site here and rely on the shared client configuration.
    raw = await call_qwen(prompt, timeout=120)
    nfs_dict = safe_json(raw)

    # 4. Add created_at and version
    now_iso = datetime.now(timezone.utc).isoformat()
    nfs_dict.setdefault("domain", domain)
    nfs_dict.setdefault("base_url", base_url)
    nfs_dict["created_at"] = now_iso
    nfs_dict["version"] = 1

    return nfs_dict


def validate_nfs(nfs_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    # Top-level checks
    for key in ("domain", "base_url", "pages"):
        if key not in nfs_dict:
            errors.append(f"Missing top-level key: {key}")

    pages = nfs_dict.get("pages") or {}
    if not isinstance(pages, dict):
        errors.append("pages must be a dict of page_id -> page object")
        return False, errors

    for page_id, page in pages.items():
        if "url_pattern" not in page or not page.get("url_pattern"):
            errors.append(f"Page '{page_id}' missing url_pattern")
        if "label" not in page or not page.get("label"):
            errors.append(f"Page '{page_id}' missing label")

        actions = page.get("actions") or []
        if not isinstance(actions, list):
            errors.append(f"Page '{page_id}' has non-list actions")
            continue

        for idx, action in enumerate(actions):
            prefix = f"Page '{page_id}' action[{idx}]"
            if not action.get("name"):
                errors.append(f"{prefix} missing name")
            execution = action.get("execution")
            if not isinstance(execution, dict):
                errors.append(f"{prefix} missing execution object")
                continue
            if "type" not in execution or not execution.get("type"):
                errors.append(f"{prefix} execution missing type")

    return (len(errors) == 0), errors


