from playwright.async_api import Page

PARAM_ALIASES = {
    "email":           ["email", "mail", "e-mail", "email address"],
    "password":        ["password", "pass", "pwd"],
    "name":            ["name", "full name", "your name", "username"],
    "confirmPassword": ["confirm", "retype", "repeat", "confirm password"],
    "phone":           ["phone", "phone number", "mobile", "telephone"],
}

# Map semantic field names to param keys
SEMANTIC_TO_PARAM = {
    "full name": "name",
    "name": "name",
    "email": "email",
    "password": "password",
    "confirm password": "confirmPassword",
    "phone number": "phone",
    "phone": "phone",
}

async def build_field_registry(page: Page) -> dict:
    fields = []
    inputs = await page.query_selector_all(
        "input:not([type='hidden']), button, select, textarea"
    )
    for el in inputs:
        tag         = await el.get_attribute("type") or "text"
        name        = await el.get_attribute("name")
        el_id       = await el.get_attribute("id")
        aria_label  = await el.get_attribute("aria-label")
        placeholder = await el.get_attribute("placeholder")
        required    = await el.get_attribute("required") is not None
        btn_text    = None

        if tag in ["submit", "button"]:
            btn_text = (await el.inner_text()).strip()

        label_text = None
        if el_id:
            lbl = await page.query_selector(f"label[for='{el_id}']")
            if lbl:
                label_text = (await lbl.inner_text()).strip()

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
            "type":         tag,
            "selector":     selector,
            "required":     required
        })

    return {"url": page.url, "fields": fields}


def find_missing_params(field_registry: dict, user_params: dict) -> list:
    missing = []
    for field in field_registry["fields"]:
        if not field["required"]:
            continue
        if field["type"] in ["submit", "button", "checkbox"]:
            continue
        matched = False
        sem = field["semanticName"].lower()
        
        # First, check if the semantic name itself is a key in user_params
        if sem in user_params and user_params[sem] is not None:
            matched = True
        else:
            # Check if semantic name maps to a param key
            param_key = SEMANTIC_TO_PARAM.get(sem)
            if param_key and param_key in user_params and user_params[param_key] is not None:
                matched = True
            else:
                # Check aliases
                for param_key, param_val in user_params.items():
                    if param_val is None:
                        continue
                    # Check if param_key matches semantic name
                    if param_key.lower() == sem:
                        matched = True
                        break
                    # Check aliases
                    aliases = PARAM_ALIASES.get(param_key, [param_key])
                    if any(alias in sem for alias in aliases):
                        matched = True
                        break
        
        if not matched:
            missing.append(field["semanticName"])
    return missing

