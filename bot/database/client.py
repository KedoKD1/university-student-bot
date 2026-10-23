from bot.utils.logging_security import configure_logging, log_error

configure_logging()

from supabase import Client, create_client

from bot.utils.config import SUPABASE_KEY, SUPABASE_URL


if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL is not configured.")

if not SUPABASE_KEY:
    raise ValueError("SUPABASE_KEY is not configured.")


try:
    supabase: Client = create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
    )
except Exception as exc:
    log_error("SUPABASE CLIENT INITIALIZATION ERROR", exc)
    raise RuntimeError("Unable to initialize the database client.") from None


def test_database_connection():
    response = supabase.table("stages").select("id").limit(1).execute()
    return response.data
