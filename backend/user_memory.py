from database import db
from customer import get_customer

def record_action(uid: str, session_id: str, command: str,
                  intent: str, url: str, success: bool):
    customer = get_customer(uid)
    if not customer:
        return
    db.table("user_actions").insert({
        "customer_id": customer["id"],
        "session_id":  session_id,
        "command":     command,
        "intent":      intent,
        "page_url":    url,
        "success":     success
    }).execute()

def get_user_context(uid: str, session_id: str) -> str:
    customer = get_customer(uid)
    if not customer:
        return "No previous actions."
    result = db.table("user_actions") \
        .select("command, page_url") \
        .eq("customer_id", customer["id"]) \
        .eq("session_id",  session_id) \
        .eq("success",     True) \
        .order("created_at", desc=True) \
        .limit(3) \
        .execute()
    if not result.data:
        return "No previous actions."
    lines = [f"- {a['command']} → {a['page_url']}" for a in result.data]
    return "\n".join(lines)


from database import db
from customer import get_customer

def record_action(uid: str, session_id: str, command: str,
                  intent: str, url: str, success: bool):
    customer = get_customer(uid)
    if not customer:
        return
    db.table("user_actions").insert({
        "customer_id": customer["id"],
        "session_id":  session_id,
        "command":     command,
        "intent":      intent,
        "page_url":    url,
        "success":     success
    }).execute()

def get_user_context(uid: str, session_id: str) -> str:
    customer = get_customer(uid)
    if not customer:
        return "No previous actions."
    result = db.table("user_actions") \
        .select("command, page_url") \
        .eq("customer_id", customer["id"]) \
        .eq("session_id",  session_id) \
        .eq("success",     True) \
        .order("created_at", desc=True) \
        .limit(3) \
        .execute()
    if not result.data:
        return "No previous actions."
    lines = [f"- {a['command']} → {a['page_url']}" for a in result.data]
    return "\n".join(lines)

