from supabase import create_client, Client
from app.core.config import settings

def get_supabase_client() -> Client:
    url = settings.NEXT_PUBLIC_SUPABASE_URL
    key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.NEXT_PUBLIC_SUPABASE_ANON_KEY
    if not url or not key:
        raise ValueError("Supabase URL and API Key must be configured in environment variables.")
    return create_client(url, key)

supabase: Client = None

try:
    if settings.NEXT_PUBLIC_SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
        supabase = get_supabase_client()
except Exception as e:
    print(f"Supabase client initialization warning: {e}")
