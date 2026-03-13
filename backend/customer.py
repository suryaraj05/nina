import uuid
from database import db

# API key format: nina-{version}-{random_hex}
NINA_API_KEY_VERSION = "v1"

def create_customer(name: str, email: str) -> dict:
    uid = str(uuid.uuid4())[:8]
    raw_key = str(uuid.uuid4()).replace("-", "")
    api_key = f"nina-{NINA_API_KEY_VERSION}-{raw_key}"
    data = {
        "uid":     uid,
        "name":    name,
        "email":   email,
        "api_key": api_key
    }
    result = db.table("customers").insert(data).execute()
    return result.data[0]

def get_customer(uid: str) -> dict | None:
    result = db.table("customers").select("*").eq("uid", uid).execute()
    return result.data[0] if result.data else None

def get_customer_by_api_key(api_key: str) -> dict | None:
    result = db.table("customers").select("*").eq("api_key", api_key).execute()
    return result.data[0] if result.data else None

def add_site_to_customer(uid: str, base_url: str):
    customer = get_customer(uid)
    if not customer:
        return
    from urllib.parse import urlparse
    domain = urlparse(base_url).netloc
    db.table("sites").upsert({
        "customer_id": customer["id"],
        "domain":      domain,
        "base_url":    base_url
    }, on_conflict="customer_id,domain").execute()

def list_customers() -> list:
    result = db.table("customers").select("*").execute()
    return result.data



