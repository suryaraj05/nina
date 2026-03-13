from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from database import db
from customer import get_customer
from nfs_schema import NFSTree
from urllib.parse import urlparse


def extract_domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc


def save_nfs(uid: str, domain: str, nfs_dict: Dict[str, Any]) -> bool:
    try:
        customer = get_customer(uid)
        if not customer:
            return False

        customer_id = customer["id"]
        now_iso = datetime.now(timezone.utc).isoformat()

        payload = {
            "customer_id": customer_id,
            "domain": domain,
            "tree": nfs_dict,
            "updated_at": now_iso,
        }

        db.table("nfs_trees").upsert(
            payload,
            on_conflict="customer_id,domain",
        ).execute()
        return True
    except Exception:
        return False


def load_nfs(uid: str, domain: str) -> Optional[Dict[str, Any]]:
    customer = get_customer(uid)
    if not customer:
        return None

    customer_id = customer["id"]
    result = (
        db.table("nfs_trees")
        .select("tree")
        .eq("customer_id", customer_id)
        .eq("domain", domain)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0].get("tree")


def _score_page(page: Dict[str, Any], url_path: str, intent: str, query_keywords: List[str]) -> int:
    score = 0
    url_pattern = page.get("url_pattern") or ""
    content_type = (page.get("content_type") or "").lower()
    normalized_intent = intent.lower()

    # Exact URL match
    if url_pattern and url_path and url_pattern == url_path:
        score += 100

    # Intent → content_type mapping with primary/secondary weights
    PRIMARY_INTENT_CONTENT = {
        "login": ["auth"],
        "signup": ["auth"],
        "navigate": ["landing", "product_list", "product_detail", "contact", "other"],
        "search": ["product_list"],
        "query": ["product_list"],
        "add_to_cart": ["product_detail"],
        "view_product": ["product_detail"],
    }
    SECONDARY_INTENT_CONTENT = {
        "search": ["landing"],
        "query": ["landing"],
        "add_to_cart": ["product_list"],
        "view_product": ["product_list"],
    }
    if content_type in (PRIMARY_INTENT_CONTENT.get(normalized_intent) or []):
        score += 50
    elif content_type in (SECONDARY_INTENT_CONTENT.get(normalized_intent) or []):
        score += 25

    # Keyword overlap between page keywords and query keywords
    page_keywords = [str(k).lower() for k in page.get("keywords") or []]
    q_keywords = [str(k).lower() for k in query_keywords]
    overlap = set(page_keywords) & set(q_keywords)
    score += 10 * len(overlap)

    # Bonus: if intent name directly appears in page keywords
    if normalized_intent in page_keywords:
        score += 20

    # Bonus: if target_hint words appear in page label
    label = (page.get("label") or "").lower()
    for kw in q_keywords:
        if kw in label:
            score += 15

    return score


def find_best_page(nfs: Dict[str, Any], url_path: str, intent: str, query_keywords: List[str]) -> Optional[Dict[str, Any]]:
    pages = nfs.get("pages") or {}
    print(f"[FIND_PAGE] url_path='{url_path}', intent='{intent}', keywords={query_keywords}")
    print(f"[FIND_PAGE] available pages: {list(pages.keys())}")
    best_page: Optional[Dict[str, Any]] = None
    best_score = 0

    for page in pages.values():
        current_score = _score_page(page, url_path, intent, query_keywords)
        print(f"[FIND_PAGE] scoring page '{page.get('url_pattern')}': score={current_score}")
        if current_score > best_score:
            best_score = current_score
            best_page = page

    return best_page


def find_action_for_intent(page: Dict[str, Any], intent: str) -> Optional[Dict[str, Any]]:
    actions = page.get("actions") or []
    intent_lower = intent.lower()
    for action in actions:
        triggers = [str(t).lower() for t in action.get("trigger_intents") or []]
        if intent_lower in triggers:
            return action
    return None


def _product_match_score(name: str, query: str) -> int:
    name_l = name.lower()
    query_l = query.lower()

    if name_l == query_l:
        return 3
    if query_l in name_l:
        return 2

    name_words = set(name_l.split())
    query_words = set(query_l.split())
    if name_words & query_words:
        return 1
    return 0


def find_product_in_nfs(nfs: Dict[str, Any], product_name: str) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    pages = nfs.get("pages") or {}
    best_product: Optional[Dict[str, Any]] = None
    best_page: Optional[Dict[str, Any]] = None
    best_score = 0

    for page in pages.values():
        products = page.get("products") or []
        for product in products:
            name = product.get("name")
            if not name:
                continue
            score = _product_match_score(name, product_name)
            if score > best_score:
                best_score = score
                best_product = product
                best_page = page

    if best_product and best_page:
        return best_product, best_page
    return None


