from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from bot.database.client import supabase
from bot.utils.chat_access import accessible_chat, can_deliver, mark_chat_inactive, record_chat


async def track_user(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    chat = update.effective_chat

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
        membership = update.my_chat_member
        if membership is not None:
            if membership.new_chat_member.user.id == context.bot.id:
                from bot.utils.subscription import subscription_membership_changed
                await subscription_membership_changed(update, context)
                record_chat(chat, can_deliver(membership.new_chat_member, chat))
            return

        message = update.effective_message
        if message and message.migrate_to_chat_id:
            mark_chat_inactive(chat.id)
            migrated = await accessible_chat(context.bot, message.migrate_to_chat_id)
            if migrated:
                record_chat(migrated, True)
            return
        if message and message.migrate_from_chat_id:
            mark_chat_inactive(message.migrate_from_chat_id)
            verified = await accessible_chat(context.bot, chat.id)
            if verified:
                record_chat(verified, True)
            return

        try:
            rows = supabase.table("bot_chats").select("is_active").eq(
                "chat_id", chat.id
            ).limit(1).execute().data or []
            if rows:
                # An old message/callback cannot reactivate a removed bot's chat.
                record_chat(chat, rows[0].get("is_active") is True)
            else:
                verified = await accessible_chat(context.bot, chat.id)
                if verified:
                    record_chat(verified, True)

        except Exception as exc:
            print(
                "CHAT TRACKING ERROR:",
                type(exc).__name__,
                exc,
            )
