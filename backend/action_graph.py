ACTION_GRAPH = {
    "signup": {
        "url":     "/signup",
        "aliases": ["register", "create account", "make an account", "sign up"],
    },
    "login": {
        "url":     "/login",
        "aliases": ["sign in", "log in", "signin"],
    },
    "navigate": {
        "url":     "/",
        "aliases": ["go to", "open", "show me", "take me"],
    },
}

def resolve_url(intent: str, target_hint: str, base_url: str) -> str:
    # First, check if intent directly maps to an action
    if intent in ACTION_GRAPH:
        return base_url.rstrip("/") + ACTION_GRAPH[intent]["url"]
    
    # If intent is "fill" but target_hint suggests signup/login, route accordingly
    if intent == "fill":
        hint_lower = target_hint.lower()
        if any(alias in hint_lower for alias in ["signup", "register", "create account", "sign up"]):
            return base_url.rstrip("/") + ACTION_GRAPH["signup"]["url"]
        if any(alias in hint_lower for alias in ["login", "sign in", "log in"]):
            return base_url.rstrip("/") + ACTION_GRAPH["login"]["url"]
    
    # Check if target_hint matches any action's aliases
    for key, val in ACTION_GRAPH.items():
        if any(alias in target_hint.lower() for alias in val["aliases"]):
            return base_url.rstrip("/") + val["url"]
    
    # Default to base URL
    return base_url

