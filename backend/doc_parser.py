import json
from urllib.parse import urljoin

def parse_openapi(spec: dict, base_url: str) -> list[dict]:
    """
    Parse an OpenAPI 3.x or Swagger 2.x spec.
    Return list of { url, label, keywords } dicts ready for site_memory.
    """
    pages = []
    paths = spec.get("paths", {})
    base = base_url.rstrip("/")

    for path, methods in paths.items():
        for method, details in methods.items():
            if method.lower() not in ["get", "post", "put", "delete", "patch"]:
                continue
            summary = details.get("summary", "")
            tags    = details.get("tags", [])
            full_url = base + path

            keywords = []
            keywords.extend(tags)
            keywords.extend(summary.lower().split())
            for segment in path.strip("/").split("/"):
                if segment and not segment.startswith("{"):
                    keywords.extend(segment.replace("-","_").split("_"))

            keywords = list(set(w for w in keywords if len(w) > 2))

            pages.append({
                "url":      full_url,
                "label":    summary or path,
                "keywords": keywords,
                "method":   method.upper()
            })

    return pages


def parse_plain_text(text: str, base_url: str) -> list[dict]:
    """
    Parse plain text like:
    /signup - Create a new account
    /products/hoodies - Browse hoodies
    /cart - View shopping cart
    """
    pages = []
    base = base_url.rstrip("/")

    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or not line.startswith("/"):
            continue
        parts = line.split(" - ", 1)
        path  = parts[0].strip()
        label = parts[1].strip() if len(parts) > 1 else path

        keywords = []
        for segment in path.strip("/").split("/"):
            if segment and not segment.startswith("{"):
                keywords.extend(segment.replace("-","_").split("_"))
        keywords.extend(label.lower().split())
        keywords = list(set(w for w in keywords if len(w) > 2))

        pages.append({
            "url":      base + path,
            "label":    label,
            "keywords": keywords,
            "method":   "GET"
        })

    return pages


