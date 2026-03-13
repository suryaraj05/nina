from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from nfs_store import (
    find_action_for_intent,
    find_best_page,
    find_product_in_nfs,
)


@dataclass
class ResolvedAction:
    found: bool
    target_url: Optional[str] = None
    action_name: Optional[str] = None
    execution_type: Optional[str] = None  # navigate|api_call|fill_form|click|None
    execution: Optional[Dict[str, Any]] = None
    resolved_params: Dict[str, Any] = field(default_factory=dict)
    requires_auth: bool = False
    auth_config: Optional[Dict[str, Any]] = None
    field_registry: Optional[Dict[str, Any]] = None


def _extract_url_path(target_hint: str) -> str:
    if not target_hint:
        return ""
    if "://" in target_hint:
        return urlparse(target_hint).path or "/"
    # treat as already a path
    return target_hint


def _join_url(base_url: str, path: str) -> str:
    if not base_url:
        return path
    if not path:
        return base_url
    if base_url.endswith("/") and path.startswith("/"):
        return base_url[:-1] + path
    if not base_url.endswith("/") and not path.startswith("/"):
        return base_url + "/" + path
    return base_url + path


def resolve_intent(intent_result: Dict[str, Any], nfs: Optional[Dict[str, Any]], base_url: str) -> ResolvedAction:
    # 1. If nfs is None → no resolution possible (backward compatible behavior)
    if nfs is None:
        return ResolvedAction(
            found=False,
            target_url=None,
            action_name=None,
            execution_type=None,
            execution=None,
            resolved_params={},
            requires_auth=False,
            auth_config=None,
            field_registry=None,
        )

    # 2. Extract from intent_result: intent, params, target_hint
    intent = intent_result.get("intent") or ""
    params: Dict[str, Any] = intent_result.get("params") or {}
    target_hint: str = intent_result.get("target_hint") or ""
    print(f"[RESOLVER] intent={intent}, params={params}, target_hint={target_hint}")

    # Keywords from params: use stringified values as a simple heuristic
    keywords_from_params: List[str] = [str(v) for v in params.values() if v]

    page = None
    action = None

    # 3. Special case — product intents
    if intent in ("add_to_cart", "view_product") and "product" in params:
        product_name = str(params.get("product"))
        product_page_tuple = find_product_in_nfs(nfs, product_name)
        if product_page_tuple:
            _, page = product_page_tuple
            action = find_action_for_intent(page, intent)

    # 4. General case if page/action still not found
    if page is None:
        url_path = _extract_url_path(target_hint)
        page = find_best_page(nfs, url_path, intent, keywords_from_params)
        print(f"[RESOLVER] best_page={page}")
        if page:
            action = find_action_for_intent(page, intent)
            print(f"[RESOLVER] action={action}")

    # If we still don't have a page or action, return unresolved
    if not page or not action:
        return ResolvedAction(
            found=False,
            target_url=None,
            action_name=None,
            execution_type=None,
            execution=None,
            resolved_params=params,
            requires_auth=False,
            auth_config=None,
            field_registry=None,
        )

    # 5. Build target_url
    execution = action.get("execution") or {}
    url_template = execution.get("url_template")

    if url_template:
        try:
            formatted = url_template.format(**params)
        except Exception:
            formatted = url_template
        if formatted.startswith("http://") or formatted.startswith("https://"):
            target_url = formatted
        else:
            target_url = _join_url(base_url, formatted)
    else:
        page_url_pattern = page.get("url_pattern") or ""
        target_url = _join_url(base_url, page_url_pattern)

    # 6. Build ResolvedAction
    requires_auth = bool(action.get("requires_auth"))
    auth_config = nfs.get("auth") if requires_auth else None

    execution_type = execution.get("type")
    field_registry = execution.get("field_registry")

    return ResolvedAction(
        found=True,
        target_url=target_url,
        action_name=action.get("name"),
        execution_type=execution_type,
        execution=execution,
        resolved_params=params,
        requires_auth=requires_auth,
        auth_config=auth_config,
        field_registry=field_registry,
    )


