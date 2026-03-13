import os
from typing import Optional, cast

from supabase import Client, create_client
from dotenv import load_dotenv

load_dotenv()

# Workaround for gotrue library bug: remove 'proxy' parameter from httpx.Client.__init__
# This is a known issue where gotrue passes 'proxy' but httpx expects 'proxies'
import httpx

_original_init = httpx.Client.__init__


def _patched_init(self, *args, **kwargs):
    # Remove 'proxy' if present and convert to 'proxies' if needed
    if "proxy" in kwargs:
        proxy_val = kwargs.pop("proxy")
        if proxy_val and "proxies" not in kwargs:
            kwargs["proxies"] = proxy_val
    return _original_init(self, *args, **kwargs)


httpx.Client.__init__ = _patched_init

_db: Optional[Client] = None


def get_db() -> Client:
    """Lazily create and return the Supabase client.

    This avoids failing at import time if env vars are missing.
    """
    global _db
    if _db is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in the environment")
        _db = create_client(url, key)
    return _db


class _DBProxy:
    """Proxy object so existing `db.table(...)` calls still work, but lazily create the client."""

    def __getattr__(self, name: str):
        return getattr(get_db(), name)


db = cast(Client, _DBProxy())

