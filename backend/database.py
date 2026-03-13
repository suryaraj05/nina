import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Workaround for gotrue library bug: remove 'proxy' parameter from httpx.Client.__init__
# This is a known issue where gotrue passes 'proxy' but httpx expects 'proxies'
import httpx
_original_init = httpx.Client.__init__

def _patched_init(self, *args, **kwargs):
    # Remove 'proxy' if present and convert to 'proxies' if needed
    if 'proxy' in kwargs:
        proxy_val = kwargs.pop('proxy')
        if proxy_val and 'proxies' not in kwargs:
            kwargs['proxies'] = proxy_val
    return _original_init(self, *args, **kwargs)

httpx.Client.__init__ = _patched_init

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

db: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

