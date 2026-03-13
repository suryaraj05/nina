"""
Extract content from the current page for querying
"""
from playwright.async_api import Page

async def extract_page_content(page: Page) -> dict:
    """Extract text content, links, and structured data from the current page"""
    content = {
        "url": page.url,
        "title": await page.title(),
        "text_content": "",
        "links": [],
        "headings": [],
        "buttons": [],
        "products": [],
        "list_items": []
    }
    
    # Extract main text content
    try:
        main_content = await page.query_selector("main, article, [role='main'], .content, #content")
        if main_content:
            content["text_content"] = (await main_content.inner_text())[:2000]  # Limit to 2000 chars
        else:
            body = await page.query_selector("body")
            if body:
                content["text_content"] = (await body.inner_text())[:2000]
    except:
        pass
    
    # Extract links
    try:
        links = await page.query_selector_all("a[href]")
        for link in links[:50]:  # Limit to 50 links
            href = await link.get_attribute("href")
            text = (await link.inner_text()).strip()
            if href and text:
                content["links"].append({"text": text, "href": href})
    except:
        pass
    
    # Extract headings
    try:
        headings = await page.query_selector_all("h1, h2, h3, h4, h5, h6")
        for heading in headings[:20]:  # Limit to 20 headings
            text = (await heading.inner_text()).strip()
            tag = await heading.evaluate("el => el.tagName.toLowerCase()")
            if text:
                content["headings"].append({"level": tag, "text": text})
    except:
        pass
    
    # Extract buttons
    try:
        buttons = await page.query_selector_all("button, [role='button'], input[type='button'], input[type='submit']")
        for btn in buttons[:30]:  # Limit to 30 buttons
            text = (await btn.inner_text()).strip() or await btn.get_attribute("value") or ""
            if text:
                content["buttons"].append(text)
    except:
        pass
    
    # Extract list items (for product lists, menu items, etc.)
    try:
        list_items = await page.query_selector_all("li, [role='listitem'], .item, .product, .card")
        for item in list_items[:30]:  # Limit to 30 items
            text = (await item.inner_text()).strip()
            if text and len(text) > 3 and len(text) < 200:
                content["list_items"].append(text)
    except:
        pass
    
    # Extract product images - try multiple selector patterns and wait for dynamic content
    try:
        # Wait a bit for products to load
        await page.wait_for_timeout(2000)
        
        # Try various product selector patterns
        product_selectors = [
            ".product",
            "[class*='product']",
            "[class*='Product']",
            ".product-card",
            "[data-product]",
            "article",
            "[role='article']",
            "[class*='item']",
            ".card"
        ]
        
        all_products = []
        seen_names = set()
        
        for selector in product_selectors:
            try:
                products = await page.query_selector_all(selector)
                for product in products[:30]:
                    # Get product name - try multiple patterns
                    name = ""
                    name_selectors = [
                        "h1", "h2", "h3", "h4", "h5", "h6",
                        ".title", ".name", "[class*='title']",
                        "[class*='name']", "a", "[href*='/product']"
                    ]
                    for ns in name_selectors:
                        name_el = await product.query_selector(ns)
                        if name_el:
                            name = (await name_el.inner_text()).strip()
                            if name and len(name) > 2 and "loading" not in name.lower():
                                break
                    
                    # Skip if no name or already seen
                    if not name or name in seen_names or len(name) < 3:
                        continue
                    
                    # Get product image
                    img_src = None
                    img_alt = ""
                    img_selectors = ["img", "picture img", "[class*='image'] img"]
                    for img_sel in img_selectors:
                        img_el = await product.query_selector(img_sel)
                        if img_el:
                            img_src = await img_el.get_attribute("src")
                            if not img_src:
                                img_src = await img_el.get_attribute("data-src")  # Lazy loading
                            img_alt = await img_el.get_attribute("alt") or ""
                            if img_src:
                                break
                    
                    # Get price
                    price = ""
                    price_selectors = [".price", "[class*='price']", ".cost", "[class*='cost']"]
                    for ps in price_selectors:
                        price_el = await product.query_selector(ps)
                        if price_el:
                            price = (await price_el.inner_text()).strip()
                            if price:
                                break
                    
                    # Only add if we have name or image
                    if name and name not in seen_names:
                        seen_names.add(name)
                        all_products.append({
                            "name": name,
                            "image": img_src,
                            "price": price
                        })
            except:
                continue
        
        content["products"] = all_products[:20]  # Limit to 20
    except Exception as e:
        print(f"Error extracting products: {str(e)}")
        pass
    
    return content

