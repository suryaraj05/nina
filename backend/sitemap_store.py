"""
Sitemap storage system - stores website structure for faster queries
"""
import json
import os
from datetime import datetime
from urllib.parse import urlparse, urljoin

SITEMAP_DIR = "sitemaps"

def ensure_sitemap_dir():
    """Create sitemap directory if it doesn't exist"""
    if not os.path.exists(SITEMAP_DIR):
        os.makedirs(SITEMAP_DIR)

def get_domain_key(url: str) -> str:
    """Extract domain key from URL for storage"""
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    return domain

def get_sitemap_path(domain: str) -> str:
    """Get file path for domain sitemap"""
    ensure_sitemap_dir()
    return os.path.join(SITEMAP_DIR, f"{domain}.json")

def load_sitemap(domain: str) -> dict:
    """Load sitemap for a domain"""
    path = get_sitemap_path(domain)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_sitemap(domain: str, sitemap: dict):
    """Save sitemap for a domain"""
    path = get_sitemap_path(domain)
    sitemap["last_updated"] = datetime.now().isoformat()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(sitemap, f, indent=2, ensure_ascii=False)

def update_page_info(domain: str, url: str, page_data: dict):
    """Update or add page information to sitemap"""
    sitemap = load_sitemap(domain)
    
    if "pages" not in sitemap:
        sitemap["pages"] = {}
    
    sitemap["pages"][url] = {
        "url": url,
        "fields": page_data.get("fields", []),
        "products": page_data.get("products", []),
        "content": page_data.get("text_content", ""),
        "links": page_data.get("links", []),
        "headings": page_data.get("headings", []),
        "last_visited": datetime.now().isoformat()
    }
    
    # Update domain info
    sitemap["domain"] = domain
    if "first_visited" not in sitemap:
        sitemap["first_visited"] = datetime.now().isoformat()
    
    save_sitemap(domain, sitemap)
    return sitemap

def find_in_sitemap(domain: str, query: str, query_type: str = "product") -> dict:
    """
    Search sitemap for query
    query_type: "product", "page", "field", "link", "all"
    """
    sitemap = load_sitemap(domain)
    results = {
        "found": False,
        "pages": [],
        "products": [],
        "fields": [],
        "matching_links": []
    }
    
    if "pages" not in sitemap:
        return results
    
    query_lower = query.lower()
    query_words = query_lower.split()
    
    # Search all pages
    for url, page_data in sitemap["pages"].items():
        # Search products
        if query_type in ["product", "all"]:
            for product in page_data.get("products", []):
                product_name = product.get("name", "").lower()
                if query_lower in product_name or any(word in product_name for word in query_words):
                    results["products"].append({
                        **product,
                        "page_url": url
                    })
        
        # Search fields
        if query_type in ["field", "all"]:
            for field in page_data.get("fields", []):
                field_name = field.get("semanticName", "").lower()
                if query_lower in field_name:
                    results["fields"].append({
                        **field,
                        "page_url": url
                    })
        
        # Search links for relevant pages (e.g., "hoodies" -> "/category/hoodies")
        if query_type in ["link", "all"]:
            for link in page_data.get("links", []):
                link_text = link.get("text", "").lower()
                link_href = link.get("href", "")
                # Check if query matches link text - improved matching
                # Match if any query word is in link text, or link text is in query
                matches = False
                for word in query_words:
                    if word in link_text or link_text in word:
                        matches = True
                        break
                if not matches and link_text in query_lower:
                    matches = True
                
                if matches:
                    # Check if this link points to a category/product page
                    if "/category/" in link_href or "/shop" in link_href or "/product" in link_href or link_href.startswith("/category") or link_href.startswith("/shop"):
                        # Construct full URL
                        if link_href.startswith("http"):
                            full_url = link_href
                        elif link_href.startswith("/"):
                            # Absolute path - use domain from the page URL
                            parsed = urlparse(url)
                            base = f"{parsed.scheme}://{parsed.netloc}"
                            full_url = urljoin(base, link_href)
                        else:
                            # Relative path
                            full_url = urljoin(url, link_href)
                        
                        results["matching_links"].append({
                            "text": link.get("text", ""),
                            "href": link_href,
                            "full_url": full_url,
                            "from_page": url
                        })
        
        # Search page content
        if query_type in ["page", "all"]:
            content = page_data.get("content", "").lower()
            if query_lower in content:
                results["pages"].append({
                    "url": url,
                    "title": page_data.get("title", ""),
                    "match": True
                })
    
    results["found"] = len(results["products"]) > 0 or len(results["fields"]) > 0 or len(results["pages"]) > 0 or len(results["matching_links"]) > 0
    return results

def get_page_from_sitemap(domain: str, url: str) -> dict:
    """Get specific page data from sitemap"""
    sitemap = load_sitemap(domain)
    if "pages" in sitemap and url in sitemap["pages"]:
        return sitemap["pages"][url]
    return None

