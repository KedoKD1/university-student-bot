"""Telegram chat accessibility using the existing bot_chats records."""
from datetime import datetime, timezone

from telegram.error import BadRequest, ChatMigrated, Forbidden, TelegramError

from bot.database.client import supabase


def is_member(member):
    return member.status in {"creator", "administrator", "member"} or (
        member.status == "restricted" and member.is_member
    )


def can_deliver(member, chat):
    if not is_member(member):
        return False
    if chat.type == "channel":
        return member.status == "creator" or (
            member.status == "administrator" and member.can_post_messages is True
        )
    if member.status == "restricted":
        return member.can_send_messages is True
    if member.status == "member" and getattr(chat, "permissions", None):
        return chat.permissions.can_send_messages is not False
    return True


def mark_chat_inactive(chat_id):
    try:
        supabase.table("bot_chats").update({"is_active": False}).eq(
            "chat_id", chat_id
        ).execute()
    except Exception as exc:
        print("CHAT STATUS ERROR:", type(exc).__name__)


def record_chat(chat, active):
    try:
        supabase.table("bot_chats").upsert({
            "chat_id": chat.id,
            "chat_type": chat.type,
            "title": chat.title,
            "username": chat.username,
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
            "is_active": active,
        }, on_conflict="chat_id").execute()
    except Exception as exc:
        print("CHAT TRACKING ERROR:", type(exc).__name__)


async def accessible_chat(bot, chat_id, audience_type=None, *, migrated=False):
    """Return a verified destination; transient errors never deactivate records."""
    try:
        numeric_id = int(chat_id)
        if numeric_id >= 0:
            raise ValueError
    except (TypeError, ValueError):
        mark_chat_inactive(chat_id)
        return None

    try:
        chat = await bot.get_chat(numeric_id)
        expected = {"group", "supergroup"} if audience_type == "group" else {"channel"}
        if audience_type is not None and chat.type not in expected:
            return None
        if chat.type not in {"group", "supergroup", "channel"}:
            return None
        member = await bot.get_chat_member(chat.id, bot.id)
        if not can_deliver(member, chat):
            mark_chat_inactive(numeric_id)
            return None
        if migrated:
            record_chat(chat, True)
        return chat
    except ChatMigrated as exc:
        mark_chat_inactive(numeric_id)
        if not migrated:
            return await accessible_chat(bot, exc.new_chat_id, audience_type, migrated=True)
    except (Forbidden, BadRequest):
        mark_chat_inactive(numeric_id)
    except TelegramError as exc:
        print("CHAT ACCESS ERROR:", type(exc).__name__)
    except Exception as exc:
        print("CHAT ACCESS ERROR:", type(exc).__name__)
    return None
