"""
Handle user queries about page content using LLM
"""
from ollama_client import call_qwen, safe_json
from page_extractor import extract_page_content

QUERY_PROMPT = """
You are a helpful assistant that answers questions about a web page.

User asked: "{user_query}"

Current page information:
- URL: {url}
- Title: {title}
- Text content: {text_content}
- Links: {links}
- Headings: {headings}
- Buttons: {buttons}
- List items: {list_items}
- Products: {products}

Answer the user's question based on the page content above.
If the information is not available on the page, say so clearly.

Reply ONLY with a JSON object — no explanation, no markdown:
{{
  "answer": "your answer to the user's question",
  "found": true or false,
  "items": ["list", "of", "items", "if", "applicable"],
  "products": [{{"name": "product name", "image": "image_url", "price": "price"}}]
}}

Rules:
- Be concise and helpful
- If asking about "things available" or "what's on the page", list the items
- If asking about specific information, provide the exact answer
- If information is not found, set "found" to false
"""

async def handle_query(page_or_content, user_query: str) -> dict:
    """Extract page content and answer user's query using LLM"""
    # Check if it's a page object or content dict
    if isinstance(page_or_content, dict):
        content = page_or_content
    else:
        content = await extract_page_content(page_or_content)
    
    # Format content for prompt
    links_str = ", ".join([f"{link['text']} ({link['href']})" for link in content.get("links", [])[:10]])
    headings_str = ", ".join([h["text"] for h in content.get("headings", [])[:10]])
    buttons_str = ", ".join(content.get("buttons", [])[:10])
    items_str = ", ".join(content.get("list_items", [])[:20])
    products_str = ", ".join([f"{p.get('name', 'Product')} ({p.get('price', '')})" for p in content.get("products", [])[:10]])
    
    prompt = QUERY_PROMPT.format(
        user_query=user_query,
        url=content.get("url", "unknown"),
        title=content.get("title", "unknown"),
        text_content=content.get("text_content", "")[:1500],
        links=links_str or "None",
        headings=headings_str or "None",
        buttons=buttons_str or "None",
        list_items=items_str or "None",
        products=products_str or "None"
    )
    
    # Include products in response
    products_data = content.get("products", [])
    
    raw = await call_qwen(prompt, timeout=30)
    result = safe_json(raw)
    
    # When user asks for a specific product ("show me classic hoodie"), return only that product
    if products_data:
        query_lower = (user_query or "").lower().replace("-", " ")
        matching = []
        for p in products_data:
            name = (p.get("name") or "").strip()
            if not name:
                continue
            name_norm = name.lower().replace("-", " ")
            if name_norm in query_lower or query_lower in name_norm:
                matching.append(p)
            else:
                name_words = [w for w in name_norm.split() if len(w) > 1]
                if name_words and all(w in query_lower for w in name_words):
                    matching.append(p)
        result["products"] = matching if matching else products_data
    
    return result

