import asyncio
import sys
import queue
import threading
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi import Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from intent_parser  import parse_intent
from action_graph   import resolve_url
from field_registry import build_field_registry, find_missing_params, SEMANTIC_TO_PARAM
from step_generator import generate_steps
from executor       import execute_steps
from ollama_client  import call_qwen
from query_handler  import handle_query
import site_memory as sm
from customer import create_customer, get_customer, get_customer_by_api_key, list_customers
from doc_parser import parse_openapi, parse_plain_text
import session_memory as sessm
import user_memory as userm
import json as json_lib
import os
from database import db
from nfs_store import save_nfs, load_nfs, extract_domain
from intent_resolver import resolve_intent, ResolvedAction
from nfs_builder import build_nfs_from_raw, validate_nfs

# When False, backend does not start Playwright; steps are returned for the SDK to run in the user's browser.
USE_PLAYWRIGHT = os.environ.get("NINA_USE_PLAYWRIGHT", "0") == "1"

# Use sync Playwright on Windows to avoid asyncio subprocess issues
if sys.platform == "win32":
    from playwright.sync_api import sync_playwright
    import queue
    import threading
    _playwright_queue = None
    _playwright_thread = None
    _sync_pw = None
    _sync_browser = None
    _sync_page = None
else:
    from playwright.async_api import async_playwright
    _playwright_queue = None
    _playwright_thread = None
    _sync_pw = None
    _sync_browser = None
    _sync_page = None

app = FastAPI()

origins = [
    "https://dummy-testing-site.vercel.app",
    "https://*.vercel.app",
    "http://localhost:3000",
    "http://localhost:8000",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve Nina docs / API key console from the same Railway service
try:
    import pathlib as _pathlib

    _docs_root = _pathlib.Path(__file__).resolve().parent.parent / "docs"
    if _docs_root.exists():
        app.mount(
            "/console",
            StaticFiles(directory=str(_docs_root), html=True),
            name="console",
        )
except Exception as _e:
    # Never crash app if docs directory is missing or path resolution fails
    print(f"[main] Skipping /console mount: {getattr(_e, 'message', _e)}")


@app.get("/nina-sdk.js")
async def nina_sdk():
    """Serve the embedded JS SDK as a single static file."""
    import pathlib
    sdk_path = pathlib.Path(__file__).with_name("sdk.js")
    return FileResponse(sdk_path, media_type="application/javascript")

class RunRequest(BaseModel):
    user_input:   str
    base_url:     str
    api_key:      str
    session_id:   str = "default"
    extra_params: dict | None = None


def _get_static_registry(base_url: str, target_url: str) -> dict | None:
    """Return a field registry for known paths when Playwright is disabled (client-only mode)."""
    from urllib.parse import urlparse
    base = base_url.rstrip("/")
    target = target_url.rstrip("/")
    path = urlparse(target).path or "/"
    path = path if path.startswith("/") else "/" + path
    path_lower = path.lower()
    # Login / signup: email, password, submit
    if "/login" in path_lower or "/signup" in path_lower:
        return {
            "url": target_url,
            "fields": [
                {"semanticName": "Email", "type": "email", "selector": "[name='email']", "required": True},
                {"semanticName": "Password", "type": "password", "selector": "[name='password']", "required": True},
                {"semanticName": "Login", "type": "submit", "selector": "button[type='submit']", "required": False},
            ]
        }
    # Contact: name, email, subject, message, submit
    if "/contact" in path_lower:
        return {
            "url": target_url,
            "fields": [
                {"semanticName": "Name", "type": "text", "selector": "[name='name']", "required": True},
                {"semanticName": "Email", "type": "email", "selector": "[name='email']", "required": True},
                {"semanticName": "Subject", "type": "text", "selector": "[name='subject']", "required": True},
                {"semanticName": "Message", "type": "text", "selector": "[name='message']", "required": True},
                {"semanticName": "Submit", "type": "submit", "selector": "button[type='submit']", "required": False},
            ]
        }
    return None


def _playwright_worker():
    """Dedicated thread worker that handles all Playwright operations"""
    global _sync_pw, _sync_browser, _sync_page
    
    # CRITICAL: Set ProactorEventLoop policy in this thread before Playwright
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        print("[Playwright Worker] Initializing Playwright...")
        _sync_pw = sync_playwright().start()
        print("[Playwright Worker] Playwright started, launching browser...")
        _sync_browser = _sync_pw.chromium.launch(headless=False)
        print("[Playwright Worker] Browser launched, creating page...")
        _sync_page = _sync_browser.new_page()
        print("[Playwright Worker] Page created successfully!")
        
        # Process commands from queue
        while True:
            try:
                cmd, result_queue = _playwright_queue.get(timeout=1)
                if cmd is None:  # Shutdown signal
                    break
                
                try:
                    if cmd["action"] == "goto":
                        wait_until = cmd.get("wait_until", "networkidle")
                        _sync_page.goto(cmd["url"], wait_until=wait_until, timeout=30000)
                        result_queue.put(("success", None))
                    elif cmd["action"] == "build_registry":
                        # Build field registry
                        fields = []
                        inputs = _sync_page.query_selector_all(
                            "input:not([type='hidden']), button, select, textarea"
                        )
                        for el in inputs:
                            tag = el.get_attribute("type") or "text"
                            name = el.get_attribute("name")
                            el_id = el.get_attribute("id")
                            aria_label = el.get_attribute("aria-label")
                            placeholder = el.get_attribute("placeholder")
                            required = el.get_attribute("required") is not None
                            btn_text = None
                            
                            if tag in ["submit", "button"]:
                                btn_text = el.inner_text().strip()
                            
                            label_text = None
                            if el_id:
                                lbl = _sync_page.query_selector(f"label[for='{el_id}']")
                                if lbl:
                                    label_text = lbl.inner_text().strip()
                            
                            if name:
                                selector = f"[name='{name}']"
                            elif el_id:
                                selector = f"#{el_id}"
                            elif aria_label:
                                selector = f"[aria-label='{aria_label}']"
                            elif placeholder:
                                selector = f"[placeholder='{placeholder}']"
                            elif btn_text:
                                selector = f"button:has-text('{btn_text}')"
                            else:
                                continue
                            
                            semantic = label_text or aria_label or placeholder or btn_text or name or tag
                            fields.append({
                                "semanticName": semantic,
                                "type": tag,
                                "selector": selector,
                                "required": required
                            })
                        registry = {"url": _sync_page.url, "fields": fields}
                        result_queue.put(("success", registry))
                    elif cmd["action"] == "execute_steps":
                        # Execute steps
                        steps = cmd["steps"]
                        results = []
                        for i, step in enumerate(steps):
                            action = step.get("action")
                            selector = step.get("selector")
                            value = step.get("value")
                            url = step.get("url")
                            try:
                                if action == "navigate":
                                    _sync_page.goto(url, wait_until="networkidle", timeout=15000)
                                elif action == "fill":
                                    _sync_page.wait_for_selector(selector, timeout=6000)
                                    _sync_page.fill(selector, value)
                                elif action == "click":
                                    _sync_page.wait_for_selector(selector, timeout=6000)
                                    _sync_page.click(selector)
                                    _sync_page.wait_for_load_state("networkidle", timeout=8000)
                                elif action == "check":
                                    _sync_page.wait_for_selector(selector, timeout=6000)
                                    is_checked = _sync_page.is_checked(selector)
                                    if not is_checked:
                                        _sync_page.check(selector)
                                _sync_page.wait_for_timeout(300)
                                results.append({"step": i, "action": action, "status": "ok"})
                            except Exception as e:
                                results.append({"step": i, "action": action, "status": "failed", "error": str(e)})
                                result_queue.put(("success", {"status": "partial", "completed": i, "results": results}))
                                break
                        else:
                            result_queue.put(("success", {"status": "success", "results": results}))
                    elif cmd["action"] == "wait_for_products":
                        # Wait for products to load dynamically
                        try:
                            # Wait for loading text to disappear or products to appear
                            # Try multiple common product selectors
                            product_selectors = [
                                ".product",
                                "[class*='product']",
                                "[class*='Product']",
                                ".product-card",
                                "[data-product]",
                                "article",
                                "[role='article']"
                            ]
                            
                            # Wait up to 10 seconds for products
                            found = False
                            for _ in range(20):  # Check every 500ms for 10 seconds
                                for selector in product_selectors:
                                    products = _sync_page.query_selector_all(selector)
                                    if len(products) > 0:
                                        # Check if any product has actual content (not just loading)
                                        for prod in products[:3]:
                                            text = prod.inner_text().strip()
                                            if text and "loading" not in text.lower() and len(text) > 10:
                                                found = True
                                                break
                                        if found:
                                            break
                                if found:
                                    break
                                _sync_page.wait_for_timeout(500)
                            
                            # Additional wait for images to load
                            _sync_page.wait_for_timeout(1000)
                        except:
                            pass  # Continue even if wait fails
                        result_queue.put(("success", None))
                    elif cmd["action"] == "extract_content":
                        # Extract page content for queries (sync version)
                        content = {
                            "url": _sync_page.url,
                            "title": _sync_page.title(),
                            "text_content": "",
                            "links": [],
                            "headings": [],
                            "buttons": [],
                            "products": [],
                            "list_items": []
                        }
                        
                        # Extract main text content
                        try:
                            main_content = _sync_page.query_selector("main, article, [role='main'], .content, #content")
                            if main_content:
                                content["text_content"] = main_content.inner_text()[:2000]
                            else:
                                body = _sync_page.query_selector("body")
                                if body:
                                    content["text_content"] = body.inner_text()[:2000]
                        except:
                            pass
                        
                        # Extract links
                        try:
                            links = _sync_page.query_selector_all("a[href]")
                            for link in links[:50]:
                                href = link.get_attribute("href")
                                text = link.inner_text().strip()
                                if href and text:
                                    content["links"].append({"text": text, "href": href})
                        except:
                            pass
                        
                        # Extract headings
                        try:
                            headings = _sync_page.query_selector_all("h1, h2, h3, h4, h5, h6")
                            for heading in headings[:20]:
                                text = heading.inner_text().strip()
                                tag = heading.evaluate("el => el.tagName.toLowerCase()")
                                if text:
                                    content["headings"].append({"level": tag, "text": text})
                        except:
                            pass
                        
                        # Extract buttons
                        try:
                            buttons = _sync_page.query_selector_all("button, [role='button'], input[type='button'], input[type='submit']")
                            for btn in buttons[:30]:
                                text = btn.inner_text().strip() or btn.get_attribute("value") or ""
                                if text:
                                    content["buttons"].append(text)
                        except:
                            pass
                        
                        # Extract list items
                        try:
                            list_items = _sync_page.query_selector_all("li, [role='listitem'], .item, .product, .card")
                            for item in list_items[:30]:
                                text = item.inner_text().strip()
                                if text and len(text) > 3 and len(text) < 200:
                                    content["list_items"].append(text)
                        except:
                            pass
                        
                        # Extract product images - try multiple selector patterns
                        try:
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
                                    products = _sync_page.query_selector_all(selector)
                                    for product in products[:30]:
                                        # Get product name - try multiple patterns
                                        name = ""
                                        name_selectors = [
                                            "h1", "h2", "h3", "h4", "h5", "h6",
                                            ".title", ".name", "[class*='title']",
                                            "[class*='name']", "a", "[href*='/product']"
                                        ]
                                        for ns in name_selectors:
                                            name_el = product.query_selector(ns)
                                            if name_el:
                                                name = name_el.inner_text().strip()
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
                                            img_el = product.query_selector(img_sel)
                                            if img_el:
                                                img_src = img_el.get_attribute("src")
                                                if not img_src:
                                                    img_src = img_el.get_attribute("data-src")  # Lazy loading
                                                img_alt = img_el.get_attribute("alt") or ""
                                                if img_src:
                                                    break
                                        
                                        # Get price
                                        price = ""
                                        price_selectors = [".price", "[class*='price']", ".cost", "[class*='cost']"]
                                        for ps in price_selectors:
                                            price_el = product.query_selector(ps)
                                            if price_el:
                                                price = price_el.inner_text().strip()
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
                        
                        result_queue.put(("success", content))
                except Exception as e:
                    result_queue.put(("error", str(e)))
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[Playwright Worker] Error processing command: {str(e)}")
        
        # Cleanup
        if _sync_browser:
            _sync_browser.close()
        if _sync_pw:
            _sync_pw.stop()
        print("[Playwright Worker] Shutdown complete")
    except Exception as e:
        import traceback
        print(f"[Playwright Worker] ERROR: {str(e)}")
        print(traceback.format_exc())

async def _run_playwright_command(cmd):
    """Send a command to the Playwright worker thread and wait for result"""
    if sys.platform != "win32":
        raise Exception("This function is only for Windows")
    
    result_queue = queue.Queue()
    _playwright_queue.put((cmd, result_queue))
    status, result = result_queue.get(timeout=60)
    
    if status == "error":
        raise Exception(result)
    return result

async def ensure_playwright():
    global _sync_pw, _sync_browser, _sync_page
    
    if sys.platform == "win32":
        # On Windows, Playwright should already be initialized at startup
        if _sync_pw is None or _playwright_thread is None or not _playwright_thread.is_alive():
            raise Exception(
                "Playwright not initialized. This should have been done at startup. "
                "Please restart the server."
            )
        return _sync_page  # Return a dummy object, actual operations go through queue
    else:
        # Use async Playwright on other platforms
        global pw, browser, page
        if pw is None:
            pw = await async_playwright().start()
        if browser is None:
            browser = await pw.chromium.launch(headless=False)
        if page is None:
            page = await browser.new_page()
        return page

@app.get("/health")
def health():
    return {"status": "ok"}

@app.on_event("startup")
async def startup():
    """Initialize Playwright at startup only when USE_PLAYWRIGHT is enabled.
    Wrapped in try/except so missing env vars or Playwright errors don't crash the app.
    """
    try:
        if not USE_PLAYWRIGHT:
            print("=" * 60)
            print("Nina: client-only mode (Playwright disabled)")
            print("  Steps are returned for the SDK to run in the user's browser.")
            print("=" * 60)
            return
        if sys.platform == "win32":
            print("=" * 60)
            print("Initializing Playwright on Windows...")
            print("=" * 60)

            # Create queue and start dedicated worker thread
            global _playwright_queue, _playwright_thread
            _playwright_queue = queue.Queue()
            _playwright_thread = threading.Thread(target=_playwright_worker, daemon=False, name="PlaywrightWorker")
            _playwright_thread.start()

            # Wait a bit for initialization
            import time
            time.sleep(2)

            if _playwright_thread.is_alive() and _sync_pw is not None:
                print("[OK] Playwright initialized successfully at startup")
                print(f"  Browser: {_sync_browser is not None}")
                print(f"  Page: {_sync_page is not None}")
            else:
                print("[ERROR] Playwright initialization may have failed")
                print("  Check logs above for errors")
            print("=" * 60)
        else:
            # On other platforms, initialize async Playwright
            global pw, browser, page
            try:
                pw = await async_playwright().start()
                browser = await pw.chromium.launch(headless=False)
                page = await browser.new_page()
                print("✓ Playwright initialized successfully")
            except Exception as e:
                print(f"✗ Playwright initialization failed: {str(e)}")
    except Exception as e:
        # Never crash the app on startup; just log the error.
        print(f"[startup] Unhandled startup error: {e}")

@app.on_event("shutdown")
async def shutdown():
    if not USE_PLAYWRIGHT:
        return
    if sys.platform == "win32":
        global _playwright_queue, _playwright_thread
        if _playwright_queue and _playwright_thread and _playwright_thread.is_alive():
            # Send shutdown signal
            _playwright_queue.put((None, None))
            _playwright_thread.join(timeout=5)
    else:
        global pw, browser, page
        if browser:
            await browser.close()
        if pw:
            await pw.stop()

@app.post("/run")
async def run_nina(req: RunRequest):
    customer = get_customer_by_api_key(req.api_key)
    if not customer:
        raise HTTPException(status_code=401, detail="Invalid API key")
    uid = customer["uid"]
    base_url = req.base_url
    
    # Add user message to session memory
    sessm.add_message(req.session_id, "user", req.user_input)
    
    # Get context for LLM
    session_context = sessm.get_history_summary(req.session_id)
    user_context    = userm.get_user_context(uid, req.session_id)
    
    try:
        # Parse intent (needed for both Playwright and client-only mode)
        try:
            sitemap_summary = sm.get_sitemap_summary(uid, req.base_url)
            intent_data = await parse_intent(
                req.user_input,
                sitemap_summary,
                session_context=session_context,
                user_context=user_context
            )
        except Exception as e:
            return {
                "status": "error",
                "error": f"Intent parsing failed: {str(e)}",
                "trace": "",
                "intent_data": None,
                "registry": None
            }
        intent  = intent_data["intent"]
        params  = intent_data["params"]
        hint    = intent_data["target_hint"]

        if req.extra_params:
            # Map semantic field names to param keys
            for field_name, value in req.extra_params.items():
                field_lower = field_name.lower()
                # Check if it maps to a param key
                param_key = SEMANTIC_TO_PARAM.get(field_lower)
                if param_key:
                    params[param_key] = value
                else:
                    # Use the field name directly (normalized to lowercase)
                    params[field_lower] = value

        # Simple greetings: return friendly reply without needing Playwright or steps
        _greetings = {"hello", "hi", "hey", "thanks", "thank you", "bye", "goodbye", "help"}
        if (req.user_input or "").strip().lower() in _greetings:
            _replies = {
                "hello": "Hi! I'm Nina. Tell me what you'd like to do — go to a section, search, or fill a form.",
                "hi": "Hi! How can I help you on this site today?",
                "hey": "Hey! What would you like to do?",
                "thanks": "You're welcome!",
                "thank you": "You're welcome!",
                "bye": "Bye! Come back if you need anything.",
                "goodbye": "Bye! Come back if you need anything.",
                "help": "I can take you to pages, show products, or help with forms. Try: \"Go to login\" or \"What products are there?\"",
            }
            msg = _replies.get((req.user_input or "").strip().lower(), _replies["hello"])
            return {
                "status": "success",
                "intent_data": intent_data,
                "query_result": {"answer": msg, "found": True},
                "registry": None,
                "steps": [],
                "results": [],
            }

        # Handle add_to_cart: use sitemap product url/detail_url (website provides these)
        if intent == "add_to_cart":
            product_name = (params.get("product") or "").strip().lower() or req.user_input.lower()
            for phrase in ["add to cart", "add to my cart", "put in cart", "add that", "add this", "to cart"]:
                product_name = product_name.replace(phrase, "").strip()
            product_url = sm.find_product_detail_url(uid, req.base_url, product_name)
            if product_url:
                sep = "&" if "?" in product_url else "?"
                steps = [{"action": "navigate", "url": product_url + sep + "addToCart=1"}]
                return {
                    "status": "success",
                    "intent_data": intent_data,
                    "query_result": None,
                    "registry": None,
                    "steps": steps,
                    "results": [],
                }
            intent = "query"  # No product URL in sitemap: treat as query (fallback message)

        # NFS layer — site-specific knowledge lookup
        domain = extract_domain(base_url)
        nfs = load_nfs(uid, domain)
        print(f"[NFS] loaded: {nfs is not None}, domain: {domain}")
        resolved = resolve_intent(intent_data, nfs, base_url)
        print(f"[NFS] resolved: found={resolved.found}, exec_type={resolved.execution_type}, requires_auth={resolved.requires_auth}, target_url={resolved.target_url}")

        # Auth gate — check before any Playwright or LLM work
        if resolved.requires_auth:
            return {
                "status": "needs_login",
                "message": "You need to be logged in to do that. Want me to log you in first?",
                "auth_config": resolved.auth_config,
                "queued_intent": {
                    "user_input": req.user_input,
                    "base_url": base_url,
                    "session_id": req.session_id,
                },
            }

        # If NFS resolved a navigate action — return immediately, no Playwright needed
        if resolved.found and resolved.execution_type == "navigate":
            return {
                "status": "success",
                "steps": [{"action": "navigate", "url": resolved.target_url}],
                "answer": f"Navigating to {resolved.target_url}",
            }

        # If NFS resolved an api_call action — return instruction to SDK
        if resolved.found and resolved.execution_type == "api_call":
            return {
                "status": "execute_api",
                "execution": resolved.execution,
                "resolved_params": resolved.resolved_params,
            }

        # If NFS resolved target_url, use it; else fall through to existing resolve_url
        if resolved.found and resolved.target_url:
            target_url = resolved.target_url
        else:
            target_url = resolve_url(intent, hint, base_url)  # existing function

        # Client-only mode: no Playwright; return steps for the SDK to run in the user's browser
        if not USE_PLAYWRIGHT:
            if intent == "query":
                # Answer from sitemap tree stored in DB (per-website, tree for fast retrieval)
                tree = sm.load_sitemap_tree(uid, req.base_url)
                if tree:
                    sitemap_flat = sm.tree_to_flat(tree)
                    all_products = []
                    page_titles = []
                    text_parts = []
                    for p in sitemap_flat:
                        title = p.get("label") or p.get("title") or p.get("url") or ""
                        page_titles.append(title)
                        text_parts.append(f"Page: {title} ({p.get('url', '')})")
                        for prod in p.get("products") or []:
                            all_products.append(prod)
                        if p.get("products"):
                            text_parts.append("  Products: " + ", ".join(
                                f"{x.get('name', '')} {x.get('price', '')}" for x in (p["products"] or [])
                            ))
                    aggregated_content = {
                        "url": req.base_url,
                        "title": "Site",
                        "text_content": "\n".join(text_parts),
                        "products": all_products,
                        "links": [],
                        "headings": [{"level": "h2", "text": t} for t in page_titles],
                        "buttons": [],
                        "list_items": page_titles,
                    }
                    from query_handler import handle_query
                    query_result = await handle_query(aggregated_content, req.user_input)
                    return {"status": "success", "intent_data": intent_data, "query_result": query_result, "registry": None, "steps": [], "results": []}
                return {"status": "success", "intent_data": intent_data, "query_result": {"answer": "I don't have the site structure yet. The site can provide it via POST /memory/{uid}/sitemap with pages and products (stored as a tree per website).", "found": False}, "registry": None, "steps": [], "results": []}
            memory = sm.load_memory(uid, req.base_url)
            registry = None
            for p in memory.get("sitemap", []):
                if p.get("url") == target_url and p.get("field_registry") and (p["field_registry"].get("fields") or []):
                    registry = p["field_registry"]
                    break
            if registry is None:
                registry = _get_static_registry(req.base_url, target_url)
            if registry is None:
                registry = {"url": target_url, "fields": []}
            missing = find_missing_params(registry, params)
            if missing:
                return {"status": "needs_input", "missing_fields": missing, "intent_data": intent_data, "registry": registry}
            steps = await generate_steps(intent, params, registry)
            try:
                userm.record_action(uid, req.session_id, command=req.user_input, intent=intent, url=target_url, success=True)
                sessm.add_message(req.session_id, "assistant", f"Generated {len(steps)} steps for {target_url}")
            except Exception:
                pass
            return {"status": "success", "steps": steps, "results": [], "registry": registry, "intent_data": intent_data}

        # Initialize Playwright (only when USE_PLAYWRIGHT is True)
        try:
            page = await ensure_playwright()
        except Exception as e:
            return {
                "status": "error",
                "error": f"Playwright initialization failed: {str(e)}",
                "trace": "",
                "intent_data": None,
                "registry": None
            }

        # Handle query intent (with Playwright)
        if intent == "query":
            print(f"[DEBUG] ========== QUERY INTENT DETECTED ==========")
            print(f"[DEBUG] User input: '{req.user_input}'")
            from urllib.parse import urlparse
            domain = urlparse(req.base_url).netloc
            
            # ALWAYS check for category keywords FIRST (before any sitemap checks)
            query_lower = req.user_input.lower()
            print(f"[DEBUG] Query lower: '{query_lower}'")
            category_keywords = {
                "hoodie": "/category/hoodies",
                "hoodies": "/category/hoodies",
                "t-shirt": "/category/t-shirts",
                "t-shirts": "/category/t-shirts",
                "t shirt": "/category/t-shirts",
                "jacket": "/category/jackets",
                "jackets": "/category/jackets",
                "pant": "/category/pants",
                "pants": "/category/pants"
            }
            
            inferred_category = None
            for keyword, category_path in category_keywords.items():
                if keyword in query_lower:
                    from urllib.parse import urljoin
                    inferred_category = urljoin(req.base_url.rstrip("/"), category_path)
                    print(f"[DEBUG] ✓✓✓ Category detected in query: '{keyword}' -> {inferred_category}")
                    break
            
            if not inferred_category:
                print(f"[DEBUG] ✗✗✗ No category keyword found in query")
            
            # If category detected, navigate directly to it
            if inferred_category:
                target_page_url = inferred_category
                print(f"[DEBUG] Navigating to category page: {target_page_url}")
                
                # Check if already in sitemap
                memory = sm.load_memory(uid, req.base_url)
                cached_page = None
                for page in memory.get("sitemap", []):
                    if page.get("url") == target_page_url:
                        cached_page = page
                        break
                
                if cached_page and cached_page.get("products") and len(cached_page.get("products", [])) > 0:
                    print(f"[DEBUG] Using cached products from sitemap: {len(cached_page.get('products', []))} products")
                    from query_handler import handle_query
                    cached_content = {
                        "url": target_page_url,
                        "title": cached_page.get("title", ""),
                        "text_content": cached_page.get("content", ""),
                        "products": cached_page.get("products", []),
                        "links": cached_page.get("links", []),
                        "headings": cached_page.get("headings", []),
                        "buttons": [],
                        "list_items": []
                    }
                    query_result = await handle_query(cached_content, req.user_input)
                    query_result["from_cache"] = True
                    query_result["products"] = cached_page.get("products", [])
                    return {
                        "status": "success",
                        "intent_data": intent_data,
                        "query_result": query_result,
                        "registry": {"url": target_page_url, "fields": []},
                        "steps": [],
                        "results": []
                    }
                
                # Navigate and extract products
                print(f"[DEBUG] Navigating to {target_page_url} to extract products...")
                try:
                    if sys.platform == "win32":
                        try:
                            await _run_playwright_command({"action": "goto", "url": target_page_url, "wait_until": "networkidle"})
                        except:
                            print(f"[DEBUG] networkidle timeout, using domcontentloaded")
                            await _run_playwright_command({"action": "goto", "url": target_page_url, "wait_until": "domcontentloaded"})
                        print(f"[DEBUG] Waiting for products to load...")
                        await _run_playwright_command({"action": "wait_for_products", "url": target_page_url})
                        print(f"[DEBUG] Extracting content...")
                        content = await _run_playwright_command({"action": "extract_content"})
                    else:
                        try:
                            await page.goto(target_page_url, wait_until="networkidle", timeout=30000)
                        except:
                            await page.goto(target_page_url, wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(2000)
                        from page_extractor import extract_page_content
                        content = await extract_page_content(page)
                    
                    print(f"[DEBUG] Extracted {len(content.get('products', []))} products")
                    # Extract keywords from content for sitemap
                    keywords = []
                    if content.get("title"):
                        keywords.extend(content["title"].lower().split()[:5])
                    if content.get("products"):
                        for p in content["products"][:3]:
                            if p.get("name"):
                                keywords.extend(p["name"].lower().split()[:2])
                    sm.add_page(uid, req.base_url, target_page_url, content.get("title", target_page_url), list(set(keywords)))
                    
                    from query_handler import handle_query
                    query_result = await handle_query(content, req.user_input)
                    query_result["from_cache"] = False
                    query_result["products"] = content.get("products", [])
                    
                    return {
                        "status": "success",
                        "intent_data": intent_data,
                        "query_result": query_result,
                        "registry": {"url": target_page_url, "fields": []},
                        "steps": [],
                        "results": []
                    }
                except Exception as e:
                    import traceback
                    print(f"[ERROR] Failed to extract products from {target_page_url}: {str(e)}")
                    print(traceback.format_exc())
                    # Return error but don't fall through
                    return {
                        "status": "error",
                        "error": f"Failed to extract products: {str(e)}",
                        "trace": traceback.format_exc(),
                        "intent_data": intent_data,
                        "registry": None
                    }
            
            # If no category detected, try sitemap approach
            # (This should rarely happen if category inference works)
            print(f"[DEBUG] No category detected in query, trying sitemap approach...")
            try:
                
                # First, check sitemap for cached data
                found_url = sm.find_url_for_query(uid, req.base_url, req.user_input)
                
                print(f"[DEBUG] Query: {req.user_input}")
                print(f"[DEBUG] Sitemap search - found URL: {found_url}")
                
                # If found URL in sitemap, check if it has products
                if found_url:
                    memory = sm.load_memory(uid, req.base_url)
                    cached_page = None
                    for page in memory.get("sitemap", []):
                        if page.get("url") == found_url:
                            cached_page = page
                            break
                    
                    if cached_page and cached_page.get("products") and len(cached_page.get("products", [])) > 0:
                        # Use cached products from sitemap
                        from query_handler import handle_query
                        # Create content from sitemap
                        cached_content = {
                            "url": found_url,
                            "title": cached_page.get("label", found_url),
                            "text_content": "",
                            "products": cached_page.get("products", []),
                            "links": [],
                            "headings": [],
                            "buttons": [],
                            "list_items": []
                        }
                        
                        query_result = await handle_query(cached_content, req.user_input)
                        query_result["from_cache"] = True
                        query_result["products"] = cached_page.get("products", [])
                        
                        return {
                            "status": "success",
                            "intent_data": intent_data,
                            "query_result": query_result,
                            "registry": {"url": found_url, "fields": []},
                            "steps": [],
                            "results": []
                        }
                    
                    # Navigate to found URL and extract products
                    target_page_url = found_url
                    print(f"[DEBUG] Found matching URL in sitemap: {target_page_url}")
                    
                    # Check if we already have this page in sitemap
                    memory = sm.load_memory(uid, req.base_url)
                    cached_page = None
                    for page in memory.get("sitemap", []):
                        if page.get("url") == target_page_url:
                            cached_page = page
                            break
                    
                    if cached_page and cached_page.get("products") and len(cached_page.get("products", [])) > 0:
                        # Use cached products from that page
                        from query_handler import handle_query
                        cached_content = {
                            "url": target_page_url,
                            "title": cached_page.get("label", target_page_url),
                            "text_content": "",
                            "products": cached_page.get("products", []),
                            "links": [],
                            "headings": [],
                            "buttons": [],
                            "list_items": []
                        }
                        
                        query_result = await handle_query(cached_content, req.user_input)
                        query_result["from_cache"] = True
                        query_result["products"] = cached_page.get("products", [])
                        
                        return {
                            "status": "success",
                            "intent_data": intent_data,
                            "query_result": query_result,
                            "registry": {"url": target_page_url, "fields": []},
                            "steps": [],
                            "results": []
                        }
                    
                    # Navigate to the page and extract products
                    if sys.platform == "win32":
                        # Try networkidle first, fallback to domcontentloaded if timeout
                        try:
                            await _run_playwright_command({"action": "goto", "url": target_page_url, "wait_until": "networkidle"})
                        except Exception as e:
                            if "Timeout" in str(e) or "timeout" in str(e).lower():
                                # Fallback to domcontentloaded for faster loading
                                await _run_playwright_command({"action": "goto", "url": target_page_url, "wait_until": "domcontentloaded"})
                            else:
                                raise
                        
                        # Wait for products to load (wait for loading indicator to disappear or products to appear)
                        await _run_playwright_command({"action": "wait_for_products", "url": target_page_url})
                        content = await _run_playwright_command({"action": "extract_content"})
                    else:
                        try:
                            await page.goto(target_page_url, wait_until="networkidle", timeout=30000)
                        except Exception as e:
                            if "Timeout" in str(e) or "timeout" in str(e).lower():
                                # Fallback to domcontentloaded
                                await page.goto(target_page_url, wait_until="domcontentloaded", timeout=30000)
                            else:
                                raise
                        
                        # Wait for products to load dynamically
                        await page.wait_for_timeout(2000)
                        
                        from page_extractor import extract_page_content
                        content = await extract_page_content(page)
                    
                    # Save to sitemap
                    keywords = []
                    if content.get("title"):
                        keywords.extend(content["title"].lower().split()[:5])
                    if content.get("products"):
                        for p in content["products"][:3]:
                            if p.get("name"):
                                keywords.extend(p["name"].lower().split()[:2])
                    sm.add_page(uid, req.base_url, target_page_url, content.get("title", target_page_url), list(set(keywords)))
                    
                    # Answer query
                    from query_handler import handle_query
                    query_result = await handle_query(content, req.user_input)
                    query_result["from_cache"] = False
                    query_result["products"] = content.get("products", [])
                    
                    return {
                        "status": "success",
                        "intent_data": intent_data,
                        "query_result": query_result,
                        "registry": {"url": target_page_url, "fields": []},
                        "steps": [],
                        "results": []
                    }
                
                # If not in sitemap, navigate to base_url and extract from live page
                print(f"[DEBUG] No sitemap match found, navigating to base_url: {req.base_url}")
                if sys.platform == "win32":
                    # Navigate to base_url first
                    try:
                        await _run_playwright_command({"action": "goto", "url": req.base_url, "wait_until": "networkidle"})
                    except:
                        print(f"[DEBUG] networkidle timeout, using domcontentloaded")
                        await _run_playwright_command({"action": "goto", "url": req.base_url, "wait_until": "domcontentloaded"})
                    
                    # Wait for dynamic content
                    await _run_playwright_command({"action": "wait_for_products", "url": req.base_url})
                    
                    # Extract content using queue
                    content = await _run_playwright_command({"action": "extract_content"})
                    
                    # Save to sitemap for future use
                    keywords = []
                    if content.get("title"):
                        keywords.extend(content["title"].lower().split()[:5])
                    if content.get("products"):
                        for p in content["products"][:3]:
                            if p.get("name"):
                                keywords.extend(p["name"].lower().split()[:2])
                    sm.add_page(uid, req.base_url, content["url"], content.get("title", content["url"]), list(set(keywords)))
                    
                    # Answer query using LLM - pass content dict directly
                    from query_handler import handle_query
                    query_result = await handle_query(content, req.user_input)
                    query_result["from_cache"] = False
                    
                    return {
                        "status": "success",
                        "intent_data": intent_data,
                        "query_result": query_result,
                        "registry": {"url": content["url"], "fields": []},
                        "steps": [],
                        "results": []
                    }
                else:
                    # For non-Windows, navigate to base_url first
                    print(f"[DEBUG] No sitemap match found, navigating to base_url: {req.base_url}")
                    try:
                        await page.goto(req.base_url, wait_until="networkidle", timeout=30000)
                    except:
                        await page.goto(req.base_url, wait_until="domcontentloaded", timeout=30000)
                    
                    # Wait for dynamic content
                    await page.wait_for_timeout(2000)
                    
                    # Extract content
                    from page_extractor import extract_page_content
                    content = await extract_page_content(page)
                    
                    # Save to sitemap
                    keywords = []
                    if content.get("title"):
                        keywords.extend(content["title"].lower().split()[:5])
                    if content.get("products"):
                        for p in content["products"][:3]:
                            if p.get("name"):
                                keywords.extend(p["name"].lower().split()[:2])
                    sm.add_page(uid, req.base_url, page.url, content.get("title", page.url), list(set(keywords)))
                    
                    # Answer query using LLM
                    from query_handler import handle_query
                    query_result = await handle_query(content, req.user_input)
                    query_result["from_cache"] = False
                    
                    registry = await build_field_registry(page)
                    sm.cache_registry(uid, req.base_url, page.url, registry)
                    
                    return {
                        "status": "success",
                        "intent_data": intent_data,
                        "query_result": query_result,
                        "registry": registry,
                        "steps": [],
                        "results": []
                    }
            except Exception as e:
                import traceback
                print(f"[ERROR] Query handling failed: {str(e)}")
                print(traceback.format_exc())
                # Try category inference as fallback
                try:
                    query_lower = req.user_input.lower()
                    if "hoodie" in query_lower or "hoodies" in query_lower:
                        from urllib.parse import urljoin
                        inferred_category = urljoin(req.base_url.rstrip("/"), "/category/hoodies")
                        print(f"[DEBUG] Fallback: Navigating to {inferred_category}")
                        if sys.platform == "win32":
                            await _run_playwright_command({"action": "goto", "url": inferred_category, "wait_until": "domcontentloaded"})
                            await _run_playwright_command({"action": "wait_for_products", "url": inferred_category})
                            content = await _run_playwright_command({"action": "extract_content"})
                        else:
                            await page.goto(inferred_category, wait_until="domcontentloaded", timeout=30000)
                            await page.wait_for_timeout(2000)
                            from page_extractor import extract_page_content
                            content = await extract_page_content(page)
                        
                        keywords = []
                        if content.get("title"):
                            keywords.extend(content["title"].lower().split()[:5])
                        if content.get("products"):
                            for p in content["products"][:3]:
                                if p.get("name"):
                                    keywords.extend(p["name"].lower().split()[:2])
                        sm.add_page(uid, req.base_url, inferred_category, content.get("title", inferred_category), list(set(keywords)))
                        from query_handler import handle_query
                        query_result = await handle_query(content, req.user_input)
                        query_result["from_cache"] = False
                        query_result["products"] = content.get("products", [])
                        return {
                            "status": "success",
                            "intent_data": intent_data,
                            "query_result": query_result,
                            "registry": {"url": inferred_category, "fields": []},
                            "steps": [],
                            "results": []
                        }
                except Exception as e2:
                    import traceback
                    print(f"[ERROR] Sitemap query handling also failed: {str(e2)}")
                    print(traceback.format_exc())
                    # Return error instead of falling through
                    return {
                        "status": "error",
                        "error": f"Query handling failed: {str(e2)}",
                        "trace": traceback.format_exc(),
                        "intent_data": intent_data,
                        "registry": None
                    }
            
            # If we get here, query handling didn't return (shouldn't happen)
            print(f"[WARNING] Query handling didn't return - this shouldn't happen!")
            return {
                "status": "error",
                "error": "Query handling failed to return a response",
                "intent_data": intent_data,
                "registry": None
            }
        
        # Normal flow (for non-query intents)
        from urllib.parse import urlparse
        domain = urlparse(req.base_url).netloc
        
        # Check sitemap for cached page data
        memory = sm.load_memory(uid, req.base_url)
        cached_page = None
        for page in memory.get("sitemap", []):
            if page.get("url") == target_url:
                cached_page = page
                break
        
        if cached_page and cached_page.get("field_registry") and cached_page["field_registry"].get("fields"):
            # Use cached registry if available
            registry = cached_page["field_registry"]
        else:
            # Navigate and build fresh registry
            # Handle page navigation - sync on Windows, async on others
            if sys.platform == "win32":
                # Use queue-based approach - all operations in same thread
                try:
                    await _run_playwright_command({"action": "goto", "url": target_url})
                    registry = await _run_playwright_command({"action": "build_registry"})
                    
                    # Save to sitemap
                    content = await _run_playwright_command({"action": "extract_content"})
                    keywords = []
                    if content.get("title"):
                        keywords.extend(content["title"].lower().split()[:5])
                    sm.add_page(uid, req.base_url, target_url, content.get("title", target_url), list(set(keywords)))
                    sm.cache_registry(uid, req.base_url, target_url, registry)
                except Exception as e:
                    # If navigation fails, try with domcontentloaded instead of networkidle
                    try:
                        await _run_playwright_command({"action": "goto", "url": target_url, "wait_until": "domcontentloaded"})
                        registry = await _run_playwright_command({"action": "build_registry"})
                        content = await _run_playwright_command({"action": "extract_content"})
                        keywords = []
                        if content.get("title"):
                            keywords.extend(content["title"].lower().split()[:5])
                        sm.add_page(uid, req.base_url, target_url, content.get("title", target_url), list(set(keywords)))
                        sm.cache_registry(uid, req.base_url, target_url, registry)
                    except Exception as e2:
                        raise Exception(f"Navigation failed: {str(e2)}")
            else:
                try:
                    await page.goto(target_url, wait_until="networkidle", timeout=30000)
                    registry = await build_field_registry(page)
                    
                    # Save to sitemap
                    from page_extractor import extract_page_content
                    content = await extract_page_content(page)
                    keywords = []
                    if content.get("title"):
                        keywords.extend(content["title"].lower().split()[:5])
                    sm.add_page(uid, req.base_url, target_url, content.get("title", target_url), list(set(keywords)))
                    sm.cache_registry(uid, req.base_url, target_url, registry)
                except Exception as e:
                    # Fallback to domcontentloaded
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                    registry = await build_field_registry(page)
                    from page_extractor import extract_page_content
                    content = await extract_page_content(page)
                    keywords = []
                    if content.get("title"):
                        keywords.extend(content["title"].lower().split()[:5])
                    sm.add_page(uid, req.base_url, target_url, content.get("title", target_url), list(set(keywords)))
                    sm.cache_registry(uid, req.base_url, target_url, registry)

        missing = find_missing_params(registry, params)
        if missing:
            return {
                "status":        "needs_input",
                "missing_fields": missing,
                "intent_data":   intent_data,
                "registry":      registry
            }

        steps  = await generate_steps(intent, params, registry)
        
        # Execute steps - sync on Windows, async on others
        if sys.platform == "win32":
            result = await _run_playwright_command({"action": "execute_steps", "steps": steps})
        else:
            result = await execute_steps(page, steps)

        # Record successful/failed action in user memory and session memory
        try:
            userm.record_action(
                uid, req.session_id,
                command=req.user_input,
                intent=intent,
                url=page.url,
                success=(result["status"] == "success")
            )
            sessm.add_message(
                req.session_id,
                "assistant",
                f"Executed {len(steps)} steps on {page.url}"
            )
        except Exception:
            # Memory failures should not break the main flow
            pass

        return {
            "status":    result["status"],
            "steps":     steps,
            "results":   result["results"],
            "registry":  registry,
            "intent_data": intent_data
        }
    except Exception as e:
        import traceback
        error_msg = str(e)
        error_trace = traceback.format_exc()
        return {
            "status": "error",
            "error": error_msg,
            "trace": error_trace,
            "intent_data": None,
            "registry": None
        }

class CustomerCreate(BaseModel):
    name:  str
    email: str

@app.post("/customers")
async def new_customer(body: CustomerCreate):
    customer = create_customer(body.name, body.email)
    return customer

@app.get("/customers")
async def all_customers():
    return list_customers()

@app.get("/customers/{uid}")
async def get_one_customer(uid: str):
    c = get_customer(uid)
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    return c

@app.post("/customers/{uid}/upload-docs")
async def upload_docs(
    uid: str,
    base_url: str = Form(...),
    file: UploadFile = File(...)
):
    customer = get_customer(uid)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    content = await file.read()

    if file.filename.endswith(".json"):
        try:
            spec = json_lib.loads(content)
            pages = parse_openapi(spec, base_url)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    else:
        pages = parse_plain_text(content.decode("utf-8"), base_url)

    # Store each parsed page into site memory
    for page in pages:
        sm.add_page(uid, base_url, page["url"], page["label"], page["keywords"])

    from customer import add_site_to_customer
    add_site_to_customer(uid, base_url)

    return {
        "status":       "ok",
        "pages_added":  len(pages),
        "sitemap":      sm.load_memory(uid, base_url)["sitemap"]
    }

@app.get("/memory/{uid}/{domain}")
async def get_memory(uid: str, domain: str):
    base_url = f"https://{domain.replace('_', '.')}"
    return sm.load_memory(uid, base_url)


class SitemapPage(BaseModel):
    url:      str
    title:    str
    keywords: list[str] = []
    products: list[dict] = []


class SitemapUpload(BaseModel):
    base_url: str
    pages:    list[SitemapPage]


@app.post("/memory/{uid}/sitemap")
async def upload_sitemap(uid: str, body: SitemapUpload):
    """
    Let a website provide its sitemap. Stored as a JSON tree per website (customer + domain)
    in Supabase for fast retrieval. Each website's sitemap is isolated.
    POST with base_url and pages (url, title, keywords, products). Tree is built and saved.
    """
    from customer import get_customer, add_site_to_customer
    if not get_customer(uid):
        raise HTTPException(status_code=404, detail="Customer not found")
    base_url = body.base_url.rstrip("/")
    pages = [
        {"url": p.url, "title": p.title, "keywords": list(p.keywords or []), "products": list(p.products or [])}
        for p in body.pages
    ]
    tree = sm.pages_to_tree(pages, base_url)
    sm.save_sitemap_tree(uid, base_url, tree)
    add_site_to_customer(uid, base_url)
    return {"status": "ok", "pages_added": len(body.pages), "tree_stored": True}


@app.delete("/memory/{uid}/{domain}")
async def clear_memory(uid: str, domain: str):
    import os
    path = f"site_memory/{uid}/{domain}.json"
    if os.path.exists(path):
        os.remove(path)
    return {"status": "cleared"}


@app.post("/memory/{uid}/{domain}/openapi")
async def upload_openapi_spec(uid: str, domain: str, file: UploadFile = File(...)):
    """
    Seed site memory from an uploaded OpenAPI JSON spec.

    - Customer uploads their OpenAPI spec (JSON).
    - We parse the paths and create sitemap entries so Nina already knows routes
      like /checkout without needing to discover them by crawling.
    """
    import json

    # Reconstruct base_url from domain the same way as other memory endpoints
    base_url = f"https://{domain.replace('_', '.')}"

    try:
        raw = await file.read()
        spec = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in uploaded OpenAPI spec")

    paths = spec.get("paths") or {}
    if not isinstance(paths, dict) or not paths:
        raise HTTPException(status_code=400, detail="OpenAPI spec has no paths")

    pages_added = 0

    for path, path_item in paths.items():
        # Skip non-string paths defensively
        if not isinstance(path, str):
            continue

        # Path-level object may contain operations (get/post/...) and other keys
        if not isinstance(path_item, dict):
            continue

        # Collect keywords from all operations on this path
        keywords = set()

        # Basic keyword from the path itself
        clean_path = path.strip("/")
        if clean_path:
            keywords.update(clean_path.replace("/", " ").split())

        # Default label is the raw path; we'll upgrade it if we find a better summary
        label = path

        for method, operation in path_item.items():
            # Only consider HTTP methods (get, post, put, delete, patch, options, head)
            if method.lower() not in {"get", "post", "put", "delete", "patch", "options", "head"}:
                continue
            if not isinstance(operation, dict):
                continue

            summary = operation.get("summary") or operation.get("description")
            if summary and isinstance(summary, str):
                # Prefer the first non-empty summary as the label
                if label == path:
                    label = summary.strip()
                keywords.update(summary.lower().split())

            operation_id = operation.get("operationId")
            if operation_id:
                keywords.update(str(operation_id).lower().replace("_", " ").split())

            tags = operation.get("tags") or []
            for tag in tags:
                keywords.update(str(tag).lower().split())

        # Build absolute URL for this route
        from urllib.parse import urljoin

        full_url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))

        # Persist into Supabase-backed site memory
        sm.add_page(
            uid=uid,
            base_url=base_url,
            url=full_url,
            label=label,
            keywords=sorted(set(k for k in keywords if k)),
        )
        pages_added += 1

    return {"status": "ok", "pages_added": pages_added}


@app.post("/nfs/{uid}/upload")
async def upload_nfs(uid: str, body: dict):
    """
    Upload a complete NFSTree JSON for a given customer + domain.
    """
    is_valid, warnings = validate_nfs(body)
    if not is_valid:
        return {"status": "error", "warnings": warnings}

    domain = body.get("domain") or extract_domain(body.get("base_url", ""))
    if not domain:
        return {"status": "error", "warnings": ["Missing domain and base_url in NFS body"]}

    ok = save_nfs(uid, domain, body)
    if not ok:
        return {"status": "error", "warnings": ["Failed to persist NFS tree"]}

    return {"status": "ok", "domain": domain}


@app.get("/nfs/{uid}/{domain}")
async def get_nfs(uid: str, domain: str):
    tree = load_nfs(uid, domain)
    if not tree:
        return {"status": "not_found"}
    return tree


@app.delete("/nfs/{uid}/{domain}")
async def delete_nfs(uid: str, domain: str):
    customer = get_customer(uid)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer_id = customer["id"]
    db.table("nfs_trees").delete().eq("customer_id", customer_id).eq("domain", domain).execute()
    return {"status": "deleted"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
