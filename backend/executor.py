from playwright.async_api import Page

async def execute_steps(page: Page, steps: list) -> dict:
    results = []
    for i, step in enumerate(steps):
        action   = step.get("action")
        selector = step.get("selector")
        value    = step.get("value")
        url      = step.get("url")
        try:
            if action == "navigate":
                await page.goto(url, wait_until="networkidle", timeout=15000)
            elif action == "fill":
                await page.wait_for_selector(selector, timeout=6000)
                await page.fill(selector, value)
            elif action == "click":
                await page.wait_for_selector(selector, timeout=6000)
                await page.click(selector)
                await page.wait_for_load_state("networkidle", timeout=8000)
            elif action == "check":
                await page.wait_for_selector(selector, timeout=6000)
                is_checked = await page.is_checked(selector)
                if not is_checked:
                    await page.check(selector)
            await page.wait_for_timeout(300)
            results.append({"step": i, "action": action, "status": "ok"})
        except Exception as e:
            results.append({"step": i, "action": action, "status": "failed", "error": str(e)})
            return {"status": "partial", "completed": i, "results": results}
    return {"status": "success", "results": results}

