from database import db
from urllib.parse import urlparse

def _get_site(uid: str, base_url: str) -> dict | None:
    from customer import get_customer
    customer = get_customer(uid)
    if not customer:
        return None
    domain = urlparse(base_url).netloc
    result = db.table("sites") \
        .select("*") \
        .eq("customer_id", customer["id"]) \
        .eq("domain", domain) \
        .execute()
    return result.data[0] if result.data else None

def _get_or_create_site(uid: str, base_url: str) -> dict:
    site = _get_site(uid, base_url)
    if site:
        return site
    from customer import get_customer, add_site_to_customer
    add_site_to_customer(uid, base_url)
    return _get_site(uid, base_url)

def has_memory(uid: str, base_url: str) -> bool:
    from customer import get_customer
    customer = get_customer(uid)
    if not customer:
        return False
    domain = urlparse(base_url).netloc
    result = db.table("site_pages") \
        .select("id") \
        .eq("customer_id", customer["id"]) \
        .eq("domain", domain) \
        .limit(1) \
        .execute()
    return len(result.data) > 0

def add_page(uid: str, base_url: str, url: str, label: str, keywords: list[str]):
    from customer import get_customer
    customer = get_customer(uid)
    if not customer:
        return
    domain = urlparse(base_url).netloc
    # Store keywords as JSON in a text field - we'll use title for label
    db.table("site_pages").upsert({
        "customer_id": customer["id"],
        "domain":      domain,
        "url":         url,
        "title":       label,
        "content":     " ".join(keywords)  # Store keywords in content field temporarily
    }, on_conflict="customer_id,domain,url").execute()


def add_page_with_products(
    uid: str,
    base_url: str,
    url: str,
    label: str,
    keywords: list[str],
    products: list[dict] | None = None,
    links: list | None = None,
    headings: list | None = None,
):
    """Store a page in the sitemap with optional products for fast retrieval."""
    from customer import get_customer
    customer = get_customer(uid)
    if not customer:
        return
    domain = urlparse(base_url).netloc
    row = {
        "customer_id": customer["id"],
        "domain":      domain,
        "url":         url,
        "title":       label,
        "content":     " ".join(keywords) if keywords else "",
    }
    if products is not None:
        row["products"] = products
    if links is not None:
        row["links"] = links
    if headings is not None:
        row["headings"] = headings
    db.table("site_pages").upsert(row, on_conflict="customer_id,domain,url").execute()

def find_url_for_query(uid: str, base_url: str, query: str) -> str | None:
    from customer import get_customer
    customer = get_customer(uid)
    if not customer:
        return None
    domain = urlparse(base_url).netloc
    result = db.table("site_pages") \
        .select("url, title, content") \
        .eq("customer_id", customer["id"]) \
        .eq("domain", domain) \
        .execute()
    
    query_words = query.lower().split()
    best_url, best_score = None, 0
    
    for page in result.data:
        score = 0
        title   = (page.get("title") or "").lower()
        content = (page.get("content") or "").lower()  # keywords stored here
        all_text = title + " " + content
        for word in query_words:
            if word in all_text:
                score += 1
        if score > best_score:
            best_score = score
            best_url   = page["url"]
    
    return best_url if best_score > 0 else None


def _score_page_for_query(page: dict, query_words: list[str]) -> int:
    """Score a page dict (title, content/keywords) against query words."""
    title = (page.get("title") or page.get("label") or "").lower()
    content = (page.get("content") or " ".join(page.get("keywords") or [])).lower()
    all_text = title + " " + content
    return sum(1 for w in query_words if w in all_text)


def find_url_in_pages(pages: list[dict], query: str) -> str | None:
    """Return best matching page URL from a list of page dicts (e.g. from get_sitemap_pages)."""
    if not pages:
        return None
    query_words = query.lower().split()
    best_url, best_score = None, 0
    for page in pages:
        score = _score_page_for_query(page, query_words)
        if score > best_score:
            best_score = score
            best_url = page.get("url")
    return best_url if best_score > 0 else None


def get_sitemap_pages(uid: str, base_url: str) -> list[dict]:
    """
    Return sitemap as a list of page dicts. Prefer tree from DB (sitemap_tree); if none, use site_pages (load_memory).
    """
    from urllib.parse import urljoin
    tree = load_sitemap_tree(uid, base_url)
    if tree:
        flat = tree_to_flat(tree)
        base = base_url.rstrip("/") + "/"
        out = []
        for p in flat:
            url = p.get("url") or "/"
            if url != "/" and not url.startswith("http"):
                url = urljoin(base, url.lstrip("/"))
            out.append({
                "url": url,
                "label": p.get("label") or p.get("title") or url,
                "title": p.get("title"),
                "content": " ".join(p.get("keywords") or []),
                "products": p.get("products") or [],
                "keywords": p.get("keywords") or [],
            })
        return out
    mem = load_memory(uid, base_url)
    return mem.get("sitemap", [])


def find_product_detail_url(uid: str, base_url: str, product_name: str) -> str | None:
    """
    Find a product's detail page URL from the sitemap. Products may have optional "url" or "detail_url" (website-specific).
    Returns None if no matching product has a detail URL.
    """
    from urllib.parse import urljoin
    pages = get_sitemap_pages(uid, base_url)
    query_norm = (product_name or "").strip().lower().replace("-", " ")
    if not query_norm:
        return None
    base = base_url.rstrip("/") + "/"
    for page in pages:
        for product in page.get("products") or []:
            name = (product.get("name") or "").strip().lower().replace("-", " ")
            if not name:
                continue
            name_words = [w for w in name.split() if len(w) > 1]
            match = (
                query_norm in name
                or name in query_norm
                or (name_words and all(w in query_norm for w in name_words))
            )
            if match:
                detail_url = product.get("url") or product.get("detail_url")
                if detail_url:
                    if not detail_url.startswith("http"):
                        detail_url = urljoin(base, detail_url.lstrip("/"))
                    return detail_url
    return None


def get_sitemap_summary(uid: str, base_url: str) -> str:
    from customer import get_customer
    customer = get_customer(uid)
    if not customer:
        return "No pages discovered yet."
    domain = urlparse(base_url).netloc
    result = db.table("site_pages") \
        .select("title, url") \
        .eq("customer_id", customer["id"]) \
        .eq("domain", domain) \
        .execute()
    if not result.data:
        return "No pages discovered yet."
    lines = [f"  - {p.get('title', p['url'])}: {p['url']}" for p in result.data]
    return "\n".join(lines)

def cache_registry(uid: str, base_url: str, page_url: str, registry: dict):
    from customer import get_customer
    customer = get_customer(uid)
    if not customer:
        return
    domain = urlparse(base_url).netloc
    # Store registry in fields JSONB column
    db.table("site_pages").upsert({
        "customer_id": customer["id"],
        "domain":      domain,
        "url":         page_url,
        "fields":      registry
    }, on_conflict="customer_id,domain,url").execute()

def load_memory(uid: str, base_url: str) -> dict:
    from customer import get_customer
    customer = get_customer(uid)
    if not customer:
        return {"sitemap": [], "domain": urlparse(base_url).netloc, "base_url": base_url}
    domain = urlparse(base_url).netloc
    result = db.table("site_pages") \
        .select("*") \
        .eq("customer_id", customer["id"]) \
        .eq("domain", domain) \
        .execute()
    # Map to expected format; expose DB "fields" as field_registry for registry lookup
    sitemap = []
    for page in result.data:
        sitemap.append({
            "url": page.get("url"),
            "label": page.get("title", page.get("url")),
            "title": page.get("title"),
            "content": page.get("content"),
            "products": page.get("products", []),
            "links": page.get("links", []),
            "headings": page.get("headings", []),
            "keywords": (page.get("content") or "").split() if page.get("content") else [],
            "field_registry": page.get("fields") if isinstance(page.get("fields"), dict) else None,
        })
    return {
        "domain":  domain,
        "base_url": base_url,
        "sitemap": sitemap
    }


# --- Sitemap tree (one per website, JSON tree in DB for fast retrieval) ---

def save_sitemap_tree(uid: str, base_url: str, tree: dict) -> None:
    """Store sitemap as a JSON tree for this website (customer + domain). One row per site."""
    from customer import get_customer
    from datetime import datetime, timezone
    customer = get_customer(uid)
    if not customer:
        return
    domain = urlparse(base_url).netloc
    db.table("sitemap_tree").upsert({
        "customer_id": customer["id"],
        "domain": domain,
        "tree": tree,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="customer_id,domain").execute()


def load_sitemap_tree(uid: str, base_url: str) -> dict | None:
    """Load the sitemap tree for this website. Returns None if none stored."""
    from customer import get_customer
    customer = get_customer(uid)
    if not customer:
        return None
    domain = urlparse(base_url).netloc
    result = db.table("sitemap_tree") \
        .select("tree") \
        .eq("customer_id", customer["id"]) \
        .eq("domain", domain) \
        .limit(1) \
        .execute()
    if not result.data:
        return None
    return result.data[0].get("tree")


def tree_to_flat(node: dict, base_url: str = "") -> list[dict]:
    """Flatten a sitemap tree to a list of page nodes (depth-first). Each node has url, title, products, etc."""
    out = []
    url = node.get("url") or "/"
    title = node.get("title") or ""
    products = node.get("products") or []
    keywords = node.get("keywords") or []
    # Skip root container (url="/", title="Site") unless it has products
    is_real_page = url != "/" or products or (title and title != "Site")
    if is_real_page:
        out.append({
            "url": url,
            "title": title,
            "label": title or url,
            "products": products,
            "keywords": keywords,
        })
    for child in node.get("children") or []:
        out.extend(tree_to_flat(child, base_url))
    return out


def pages_to_tree(pages: list[dict], base_url: str = "") -> dict:
    """
    Build a JSON tree from a flat list of pages (each: url, title, keywords, products).
    Tree structure: root with url="/", children = list of page nodes (one level under root).
    Each child has url, title, products, keywords, children (empty or nested).
    """
    root = {"url": "/", "title": "Site", "products": [], "keywords": [], "children": []}
    for p in pages:
        url = (p.get("url") or "").strip()
        if not url:
            continue
        # Normalize to path (strip base_url if present)
        if base_url and url.startswith(base_url):
            url = url[len(base_url):] or "/"
        if not url.startswith("/"):
            url = "/" + url
        node = {
            "url": url,
            "title": p.get("title") or p.get("label") or url,
            "products": list(p.get("products") or []),
            "keywords": list(p.get("keywords") or []),
            "children": [],
        }
        root["children"].append(node)
    return root


