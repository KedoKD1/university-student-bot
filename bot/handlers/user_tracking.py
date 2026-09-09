from datetime import datetime, timezone

from telegram import Update
from telegram.ext import (
    ContextTypes,
    ApplicationHandlerStop,
)

from bot.database.client import supabase


async def track_user(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    chat = update.effective_chat

    # ========================================================
    # Search text routing
    # ========================================================

    if (
        update.message is not None
        and update.message.text is not None
        and not update.message.text.startswith("/")
        and context.user_data.get("search_mode")
    ):
        try:
            from bot.handlers.search import (
                handle_search_text,
            )

            handled = await handle_search_text(
                update,
                context,
            )

            if handled:
                raise ApplicationHandlerStop

        except ApplicationHandlerStop:
            raise

        except Exception as exc:
            print(
                "SEARCH ROUTING ERROR:",
                type(exc).__name__,
                exc,
            )

    now = datetime.now(
        timezone.utc
    ).isoformat()

    # ========================================================
    # Track Telegram users
    # ========================================================

    if user is not None and not user.is_bot:
        try:
            supabase.table(
                "telegram_users"
            ).upsert(
                {
                    "telegram_id": user.id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "last_seen_at": now,
                },
                on_conflict="telegram_id",
            ).execute()

        except Exception as exc:
            print(
                "USER TRACKING ERROR:",
                type(exc).__name__,
                exc,
            )

    # ========================================================
    # Track groups / supergroups / channels
    # ========================================================

    if chat is not None and chat.type in (
        "group",
        "supergroup",
        "channel",
    ):
        try:
            supabase.table(
                "bot_chats"
            ).upsert(
                {
                    "chat_id": chat.id,
                    "chat_type": chat.type,
                    "title": chat.title,
                    "username": chat.username,
                    "last_seen_at": now,
                    "is_active": True,
                },
                on_conflict="chat_id",
            ).execute()

        except Exception as exc:
            print(
                "CHAT TRACKING ERROR:",
                type(exc).__name__,
                exc,
            )
