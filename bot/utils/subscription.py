"""A global, fail-closed subscription gate for student updates."""
import re
from time import monotonic
from urllib.parse import urlsplit

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationHandlerStop

from bot.database.client import supabase
from bot.utils.config import REQUIRED_CHANNEL_ID
from bot.utils.permissions import is_admin, permission_for_callback, require_callback_owner
from bot.utils.chat_access import is_member


CONFIG_TTL = 30
MEMBERSHIP_TTL = 30
FAILURE_TTL = 5


def invalidate_subscription(context):
    context.bot_data.pop("subscription", None)


async def subscription_membership_changed(update, context):
    event = update.chat_member or update.my_chat_member
    cache = context.bot_data.get("subscription", {})
    metadata = cache.get("channel")
    if event is None or not metadata or event.chat.id != metadata[2]:
        return
    user_id = event.new_chat_member.user.id
    if user_id == context.bot.id:
        invalidate_subscription(context)
        return
    members = cache.get("members", {})
    members.pop((metadata[1], user_id), None)


def _channel_reference(value):
    value = str(value or "").strip()
    if re.fullmatch(r"@[A-Za-z0-9_]{5,32}", value):
        return value
    try:
        number = int(value)
        return number if number < 0 else None
    except ValueError:
        return None


async def _required_channel(cache, force):
    cached = cache.get("config")
    if not force and cached and cached[0] > monotonic():
        return cached[1]
    try:
        rows = supabase.table("settings").select("value").eq(
            "key", "required_channel_id"
        ).limit(1).execute().data or []
        value = rows[0].get("value") if rows else None
        channel = _channel_reference(value if str(value or "").strip() else REQUIRED_CHANNEL_ID)
    except Exception as exc:
        # An environment fallback during a DB outage could use an obsolete channel.
        print("SUBSCRIPTION CONFIG ERROR:", type(exc).__name__)
        channel = None
    cache["config"] = (monotonic() + (CONFIG_TTL if channel else FAILURE_TTL), channel)
    return channel


def _join_link(chat):
    username = getattr(chat, "username", None)
    if username and re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        return f"https://t.me/{username}"
    link = getattr(chat, "invite_link", None)
    if isinstance(link, str):
        parts = urlsplit(link)
        if parts.scheme == "https" and parts.netloc == "t.me" and re.fullmatch(
            r"/(?:\+[A-Za-z0-9_-]+|joinchat/[A-Za-z0-9_-]+)", parts.path
        ) and not parts.query and not parts.fragment:
            return link
    return None


async def membership(context, user_id, *, force=False):
    """Return (subscribed, verified join URL, verification unavailable)."""
    cache = context.bot_data.setdefault("subscription", {})
    channel = await _required_channel(cache, force)
    if channel is None:
        return False, None, True
    members = cache.setdefault("members", {})
    key = (channel, user_id)
    cached = members.get(key)
    if not force and cached and cached[0] > monotonic():
        return cached[1]
    metadata = cache.get("channel")
    link = None
    result = (False, None, True)
    try:
        if force or not metadata or metadata[0] <= monotonic() or metadata[1] != channel:
            chat = await context.bot.get_chat(channel)
            link = _join_link(chat) if chat.type == "channel" else None
            own_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if chat.type != "channel" or own_member.status not in {"creator", "administrator"}:
                raise ValueError("Membership verification requires a channel administrator")
            metadata = (monotonic() + CONFIG_TTL, channel, chat.id, link)
            cache["channel"] = metadata
        else:
            link = metadata[3]
        member = await context.bot.get_chat_member(metadata[2], user_id)
        if member.status not in {"creator", "administrator", "member", "restricted", "left", "kicked"}:
            raise ValueError("Unavailable membership status")
        result = (is_member(member), link, False)
    except Exception as exc:
        print("SUBSCRIPTION CHECK ERROR:", type(exc).__name__)
        cache.pop("channel", None)
        result = (False, link, True)
    if len(members) >= 2048:
        members.clear()
    members[key] = (monotonic() + (MEMBERSHIP_TTL if result[0] else FAILURE_TTL), result)
    return result


async def _admin_access(user_id):
    try:
        return await is_admin(user_id)
    except Exception as exc:
        print("SUBSCRIPTION ROLE ERROR:", type(exc).__name__)
        return False


async def _prompt(update, result):
    subscribed, link, unavailable = result
    user = update.effective_user
    keyboard = []
    if link:
        keyboard.append([InlineKeyboardButton("📢 الاشتراك بالقناة", url=link)])
    keyboard.append([InlineKeyboardButton(
        "✅ التحقق من الاشتراك", callback_data=f"verify_subscription:{user.id}"
    )])
    text = (
        "⚠️ تعذر التحقق من الاشتراك حاليًا. حاول لاحقًا أو تواصل مع الإدارة."
        if unavailable else
        "📢 يجب الاشتراك في قناة LabBase أولًا للوصول إلى محتوى الطلاب.\n"
        "اشترك ثم اضغط «التحقق من الاشتراك»."
    )
    if not link and not unavailable:
        text += "\nرابط الانضمام غير متاح للبوت؛ اطلبه من الإدارة."
    if update.callback_query:
        await update.callback_query.answer("يرجى التحقق من الاشتراك أولًا.", show_alert=True)
    message = update.effective_message
    if message is not None:
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def subscription_guard(update, context):
    # Lifecycle/service updates must reach chat tracking even if the actor is a student.
    if update.my_chat_member is not None:
        return
    message = update.effective_message
    if message and (message.migrate_to_chat_id or message.migrate_from_chat_id):
        return
    query = update.callback_query
    if update.effective_user is None or (query is None and message is None):
        return
    if query is not None:
        data = query.data
        if isinstance(data, str) and (
            data.startswith("verify_subscription:") or permission_for_callback(data) is not None
        ):
            # Admin callbacks are independently checked by the permission guard/handlers.
            return
    elif message.text and message.text.split() and message.text.split()[0].split("@")[0] == "/admin":
        return
    if await _admin_access(update.effective_user.id):
        return
    result = await membership(context, update.effective_user.id)
    if result[0]:
        return
    try:
        await _prompt(update, result)
    finally:
        raise ApplicationHandlerStop


async def verify_subscription(update, context):
    query = update.callback_query
    if query is None or not isinstance(query.data, str) or not re.fullmatch(
        r"verify_subscription:\d+", query.data
    ) or not await require_callback_owner(query):
        return
    if not await _admin_access(query.from_user.id):
        result = await membership(context, query.from_user.id, force=True)
        if not result[0]:
            await _prompt(update, result)
            return
    from bot.handlers.main_menu import clear_user_navigation, main_menu_text
    from bot.keyboards.main_menu import main_menu_keyboard
    clear_user_navigation(context)
    await query.answer("✅ تم التحقق من الاشتراك.")
    await query.edit_message_text(main_menu_text(), reply_markup=main_menu_keyboard(query.from_user.id))
