from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from bot.database.client import supabase


async def track_user(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    if user is None or user.is_bot:
        return

    try:
        supabase.table("telegram_users").upsert(
            {
                "telegram_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "last_seen_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            },
            on_conflict="telegram_id",
        ).execute()

    except Exception as exc:
        print(
            "USER TRACKING ERROR:",
            type(exc).__name__,
            exc,
        )
