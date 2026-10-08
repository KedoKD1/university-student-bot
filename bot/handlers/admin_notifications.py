import asyncio
from datetime import datetime, timezone

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.error import (
    BadRequest,
    ChatMigrated,
    Forbidden,
    RetryAfter,
    TelegramError,
)
from telegram.ext import (
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.database.client import supabase
from bot.utils.chat_access import accessible_chat, mark_chat_inactive
from bot.utils.permissions import (
    PERMISSION_MANAGE_ANNOUNCEMENTS,
    has_permission,
    require_callback_owner,
)


# ============================================================
# Conversation states
# ============================================================

(
    NOTIFICATION_AUDIENCE,
    NOTIFICATION_TITLE,
    NOTIFICATION_CONTENT,
    NOTIFICATION_CONFIRM,
) = range(4)


# ============================================================
# Permission
# ============================================================

async def _has_notification_permission(
    user_id: int,
) -> bool:
    return await has_permission(
        user_id,
        PERMISSION_MANAGE_ANNOUNCEMENTS,
        refresh=True,
    )


# ============================================================
# Owner protection
# ============================================================

def _get_notification_owner(
    context: ContextTypes.DEFAULT_TYPE,
):
    notification = context.admin_data.get(
        "admin_notification"
    )

    if not isinstance(notification, dict):
        return None

    return notification.get(
        "owner_id"
    )


def _is_notification_owner(
    user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    owner_id = _get_notification_owner(
        context
    )

    return (
        owner_id is not None
        and owner_id == user_id
    )


# ============================================================
# Audience keyboard
# ============================================================

def _cancel_keyboard(owner_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ إلغاء", callback_data=f"notify_cancel:{owner_id}")
    ]])


def _audience_keyboard(owner_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="👥 جميع المستخدمين",
                callback_data=(
                    f'notify_audience:all:{owner_id}'
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="👤 مستخدم محدد",
                callback_data=(
                    f'notify_audience:user:{owner_id}'
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="👥 مجموعة محددة",
                callback_data=(
                    f'notify_audience:group:{owner_id}'
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="📢 قناة محددة",
                callback_data=(
                    f'notify_audience:channel:{owner_id}'
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ إلغاء",
                callback_data=f'notify_cancel:{owner_id}',
            )
        ],
    ])


# ============================================================
# Chat selection keyboard
# ============================================================

async def _get_chats(
    chat_type: str,
    bot,
):
    try:
        if chat_type == "group":
            response = (
                supabase
                .table("bot_chats")
                .select(
                    "chat_id, chat_type, title, username"
                )
                .in_(
                    "chat_type",
                    [
                        "group",
                        "supergroup",
                    ],
                )
                .eq("is_active", True)
                .order("title")
                .execute()
            )

        else:
            response = (
                supabase
                .table("bot_chats")
                .select(
                    "chat_id, chat_type, title, username"
                )
                .eq("chat_type", "channel")
                .eq("is_active", True)
                .order("title")
                .execute()
            )

        available = {}
        for row in response.data or []:
            chat = await accessible_chat(bot, row.get("chat_id"), chat_type)
            if chat is not None:
                available[chat.id] = {
                    "chat_id": chat.id, "chat_type": chat.type,
                    "title": chat.title, "username": chat.username,
                }
        return list(available.values())

    except Exception as exc:
        print(
            "GET NOTIFICATION CHATS ERROR:",
            type(exc).__name__,
            exc,
        )
        return []


def _chat_display_name(
    chat: dict,
) -> str:
    title = chat.get("title")

    if title:
        return str(title)

    username = chat.get("username")

    if username:
        return f"@{username}"

    return str(
        chat.get("chat_id")
    )


def _chat_keyboard(
    chats,
    audience_type: str,
    owner_id,
):
    keyboard = []

    for chat in chats:
        chat_id = chat.get("chat_id")

        if chat_id is None:
            continue

        keyboard.append([
            InlineKeyboardButton(
                text=_chat_display_name(chat),
                callback_data=(
                    f'notify_chat:{audience_type}:{chat_id}:{owner_id}'
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="❌ إلغاء",
            callback_data=f'notify_cancel:{owner_id}',
        )
    ])

    return InlineKeyboardMarkup(keyboard)


# ============================================================
# Notification state helpers
# ============================================================

def _get_notification(
    context: ContextTypes.DEFAULT_TYPE,
):
    return context.admin_data.get(
        "admin_notification"
    )


def _clear_notification(
    context: ContextTypes.DEFAULT_TYPE,
):
    context.admin_data.pop(
        "admin_notification",
        None,
    )


# ============================================================
# Entry point
# ============================================================

async def admin_notifications(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return ConversationHandler.END

    user_id = query.from_user.id

    if not await _has_notification_permission(
        user_id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    _clear_notification(context)

    context.admin_data[
        "admin_notification"
    ] = {
        "owner_id": user_id,
    }

    await query.answer()

    await query.edit_message_text(
        "📢 إدارة التبليغات\n\n"
        "اختر الجمهور الذي تريد إرسال التبليغ إليه:",
        reply_markup=_audience_keyboard(user_id),
    )

    return NOTIFICATION_AUDIENCE


# ============================================================
# Audience selection
# ============================================================

async def notification_audience(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not await require_callback_owner(query):
        return None

    if (
        query is None
        or query.from_user is None
    ):
        return ConversationHandler.END

    user_id = query.from_user.id

    if not await _has_notification_permission(
        user_id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    notification = _get_notification(
        context
    )

    if notification is None:
        return ConversationHandler.END

    if not _is_notification_owner(
        user_id,
        context,
    ):
        await query.answer(
            "⛔ هذه العملية مو إلك.",
            show_alert=True,
        )
        return NOTIFICATION_AUDIENCE

    data = (query.data or "").rsplit(":", 1)[0]

    if data == "notify_cancel":
        await query.answer()

        _clear_notification(context)

        await query.edit_message_text(
            "❌ تم إلغاء إنشاء التبليغ."
        )

        return ConversationHandler.END

    if not data.startswith(
        "notify_audience:"
    ):
        return NOTIFICATION_AUDIENCE

    audience = data.split(
        ":",
        1,
    )[1]

    if audience == "all":
        notification[
            "audience_type"
        ] = "all_users"

        notification[
            "audience_value"
        ] = None

        context.admin_data[
            "admin_notification"
        ] = notification

        await query.answer()

        await query.edit_message_text(
            "📝 أرسل عنوان التبليغ:",
            reply_markup=_cancel_keyboard(user_id),
        )

        return NOTIFICATION_TITLE

    if audience == "user":
        notification[
            "audience_type"
        ] = "user"

        notification[
            "audience_value"
        ] = None

        context.admin_data[
            "admin_notification"
        ] = notification

        await query.answer()

        await query.edit_message_text(
            "👤 مستخدم محدد\n\n"
            "أرسل Telegram User ID للمستخدم:",
            reply_markup=_cancel_keyboard(user_id),
        )

        return NOTIFICATION_AUDIENCE

    if audience == "group":
        chats = await _get_chats(
            "group", context.bot,
        )

        if not chats:
            await query.answer(
                "❌ لا توجد مجموعات مسجلة.",
                show_alert=True,
            )
            return NOTIFICATION_AUDIENCE

        await query.answer()

        await query.edit_message_text(
            "👥 اختر المجموعة:",
            reply_markup=_chat_keyboard(
                chats,
                "group",
                user_id,
            ),
        )

        return NOTIFICATION_AUDIENCE

    if audience == "channel":
        chats = await _get_chats(
            "channel", context.bot,
        )

        if not chats:
            await query.answer(
                "❌ لا توجد قنوات مسجلة.",
                show_alert=True,
            )
            return NOTIFICATION_AUDIENCE

        await query.answer()

        await query.edit_message_text(
            "📢 اختر القناة:",
            reply_markup=_chat_keyboard(
                chats,
                "channel",
                user_id,
            ),
        )

        return NOTIFICATION_AUDIENCE

    return NOTIFICATION_AUDIENCE


# ============================================================
# Specific user ID
# ============================================================

async def notification_user_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if (
        message is None
        or message.from_user is None
    ):
        return ConversationHandler.END

    user_id = message.from_user.id

    if not await _has_notification_permission(
        user_id
    ):
        if _is_notification_owner(user_id, context):
            _clear_notification(context)
        await message.reply_text("⛔ لم تعد لديك صلاحية إنشاء التبليغ.")
        return ConversationHandler.END

    if not _is_notification_owner(
        user_id,
        context,
    ):
        return ConversationHandler.END

    notification = _get_notification(
        context
    )

    if notification is None:
        return ConversationHandler.END

    raw_user_id = (
        message.text or ""
    ).strip()

    try:
        target_user_id = int(
            raw_user_id
        )
        if target_user_id <= 0:
            raise ValueError

    except ValueError:
        await message.reply_text(
            "❌ Telegram User ID غير صالح.\n\n"
            "أرسل الرقم فقط.",
            reply_markup=_cancel_keyboard(user_id),
        )
        return NOTIFICATION_AUDIENCE

    notification[
        "audience_type"
    ] = "user"

    notification[
        "audience_value"
    ] = str(target_user_id)

    context.admin_data[
        "admin_notification"
    ] = notification

    await message.reply_text(
        "📝 أرسل عنوان التبليغ:",
        reply_markup=_cancel_keyboard(user_id),
    )

    return NOTIFICATION_TITLE


# ============================================================
# Specific group/channel
# ============================================================

async def notification_chat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not await require_callback_owner(query):
        return None

    if (
        query is None
        or query.from_user is None
    ):
        return ConversationHandler.END

    user_id = query.from_user.id

    if not await _has_notification_permission(
        user_id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    if not _is_notification_owner(
        user_id,
        context,
    ):
        await query.answer(
            "⛔ هذه العملية مو إلك.",
            show_alert=True,
        )
        return NOTIFICATION_AUDIENCE

    data = (query.data or "").rsplit(":", 1)[0]

    parts = data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return NOTIFICATION_AUDIENCE

    audience_type = parts[1]
    audience_value = parts[2]

    if audience_type not in (
        "group",
        "channel",
    ):
        await query.answer(
            "❌ نوع الجمهور غير صالح.",
            show_alert=True,
        )
        return NOTIFICATION_AUDIENCE

    try:
        target_id = int(audience_value)
        if target_id >= 0:
            raise ValueError

    except ValueError:
        await query.answer(
            "❌ Chat ID غير صالح.",
            show_alert=True,
        )
        return NOTIFICATION_AUDIENCE

    try:
        rows = supabase.table("bot_chats").select("chat_id").eq(
            "chat_id", target_id
        ).eq("is_active", True).execute().data or []
        target = await accessible_chat(context.bot, target_id, audience_type) if rows else None
    except Exception as exc:
        print("NOTIFICATION DESTINATION ERROR:", type(exc).__name__)
        target = None
    if target is None:
        await query.answer("❌ هذه المحادثة غير متاحة للتبليغات.", show_alert=True)
        return NOTIFICATION_AUDIENCE
    audience_value = str(target.id)

    notification = _get_notification(
        context
    )

    if notification is None:
        return ConversationHandler.END

    notification[
        "audience_type"
    ] = audience_type

    notification[
        "audience_value"
    ] = audience_value

    context.admin_data[
        "admin_notification"
    ] = notification

    await query.answer()

    await query.edit_message_text(
        "📝 أرسل عنوان التبليغ:",
        reply_markup=_cancel_keyboard(user_id),
    )

    return NOTIFICATION_TITLE


# ============================================================
# Title
# ============================================================

async def notification_title(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if (
        message is None
        or message.from_user is None
    ):
        return ConversationHandler.END

    user_id = message.from_user.id

    if not await _has_notification_permission(
        user_id
    ):
        if _is_notification_owner(user_id, context):
            _clear_notification(context)
        await message.reply_text("⛔ لم تعد لديك صلاحية إنشاء التبليغ.")
        return ConversationHandler.END

    if not _is_notification_owner(
        user_id,
        context,
    ):
        return ConversationHandler.END

    title = (
        message.text or ""
    ).strip()

    if not title:
        await message.reply_text(
            "❌ العنوان لا يمكن أن يكون فارغاً.\n\n"
            "أرسل عنوان التبليغ:",
            reply_markup=_cancel_keyboard(user_id),
        )
        return NOTIFICATION_TITLE

    if len(title) > 200:
        await message.reply_text(
            "❌ العنوان طويل جداً.\n\n"
            "الحد الأقصى 200 حرف.",
            reply_markup=_cancel_keyboard(user_id),
        )
        return NOTIFICATION_TITLE

    notification = _get_notification(
        context
    )

    if notification is None:
        return ConversationHandler.END

    notification[
        "title"
    ] = title

    context.admin_data[
        "admin_notification"
    ] = notification

    await message.reply_text(
        "📝 أرسل محتوى التبليغ:\n\n"
        "الحد الأقصى 3800 حرف.",
        reply_markup=_cancel_keyboard(user_id),
    )

    return NOTIFICATION_CONTENT


# ============================================================
# Content
# ============================================================

async def notification_content(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if (
        message is None
        or message.from_user is None
    ):
        return ConversationHandler.END

    user_id = message.from_user.id

    if not await _has_notification_permission(
        user_id
    ):
        if _is_notification_owner(user_id, context):
            _clear_notification(context)
        await message.reply_text("⛔ لم تعد لديك صلاحية إنشاء التبليغ.")
        return ConversationHandler.END

    if not _is_notification_owner(
        user_id,
        context,
    ):
        return ConversationHandler.END

    content = (
        message.text or ""
    ).strip()

    if not content:
        await message.reply_text(
            "❌ محتوى التبليغ لا يمكن أن يكون فارغاً.\n\n"
            "أرسل المحتوى:",
            reply_markup=_cancel_keyboard(user_id),
        )
        return NOTIFICATION_CONTENT

    if len(content) > 3800:
        await message.reply_text(
            "❌ المحتوى طويل جداً.\n\n"
            "الحد الأقصى 3800 حرف.",
            reply_markup=_cancel_keyboard(user_id),
        )
        return NOTIFICATION_CONTENT

    notification = _get_notification(
        context
    )

    if notification is None:
        return ConversationHandler.END

    title = notification.get(
        "title",
        "",
    )

    final_text = (
        f"📢 {title}\n\n"
        f"{content}"
    )

    if len(final_text) > 4096:
        await message.reply_text(
            "❌ التبليغ يتجاوز الحد المسموح به في Telegram.\n\n"
            "اختصر العنوان أو المحتوى.",
            reply_markup=_cancel_keyboard(user_id),
        )
        return NOTIFICATION_CONTENT

    notification[
        "content"
    ] = content

    context.admin_data[
        "admin_notification"
    ] = notification

    audience_type = notification.get(
        "audience_type"
    )

    audience_value = notification.get(
        "audience_value"
    )

    if audience_type == "all_users":
        audience_text = "👥 جميع المستخدمين"

    elif audience_type == "user":
        audience_text = (
            "👤 مستخدم محدد\n"
            f"ID: {audience_value}"
        )

    elif audience_type == "group":
        audience_text = (
            "👥 مجموعة محددة\n"
            f"Chat ID: {audience_value}"
        )

    elif audience_type == "channel":
        audience_text = (
            "📢 قناة محددة\n"
            f"Chat ID: {audience_value}"
        )

    else:
        audience_text = "❓ غير معروف"

    owner_id = user_id
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="🚀 إرسال التبليغ",
                callback_data=f'notify_confirm:{owner_id}',
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ إلغاء",
                callback_data=f'notify_cancel:{owner_id}',
            )
        ],
    ])

    await message.reply_text(
        "📢 معاينة التبليغ\n\n"
        f"🎯 الجمهور:\n{audience_text}\n\n"
        f"📝 العنوان:\n{title}\n\n"
        "━━━━━━━━━━━━━━\n\n"
        f"{content}\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "هل تريد إرسال هذا التبليغ؟",
        reply_markup=keyboard,
    )

    return NOTIFICATION_CONFIRM


# ============================================================
# Confirm
# ============================================================

async def notification_confirm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not await require_callback_owner(query):
        return None

    if (
        query is None
        or query.from_user is None
    ):
        return ConversationHandler.END

    user_id = query.from_user.id

    if not await _has_notification_permission(
        user_id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    if not _is_notification_owner(
        user_id,
        context,
    ):
        await query.answer(
            "⛔ هذا التبليغ مو إلك.",
            show_alert=True,
        )
        return NOTIFICATION_CONFIRM

    notification = _get_notification(
        context
    )

    if not notification:
        await query.answer(
            "❌ انتهت جلسة إنشاء التبليغ.",
            show_alert=True,
        )
        return ConversationHandler.END

    if query.data.rsplit(":", 1)[0] == "notify_cancel":
        await query.answer()

        _clear_notification(context)

        await query.edit_message_text(
            "❌ تم إلغاء التبليغ."
        )

        return ConversationHandler.END

    if query.data.rsplit(":", 1)[0] != "notify_confirm":
        return NOTIFICATION_CONFIRM

    await query.answer(
        "⏳ جارٍ تجهيز التبليغ..."
    )

    audience_type = notification.get(
        "audience_type"
    )

    audience_value = notification.get(
        "audience_value"
    )

    title = notification.get(
        "title"
    )

    content = notification.get(
        "content"
    )

    if not all([
        audience_type,
        title,
        content,
    ]):
        await query.edit_message_text(
            "❌ بيانات التبليغ غير مكتملة."
        )

        _clear_notification(context)

        return ConversationHandler.END

    try:
        row = await _create_notification(
            user_id,
            title,
            content,
            audience_type,
            audience_value,
        )

    except Exception as exc:
        print(
            "CREATE NOTIFICATION ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.edit_message_text(
            "❌ تعذر إنشاء التبليغ في قاعدة البيانات."
        )

        _clear_notification(context)

        return ConversationHandler.END

    notification_id = row.get(
        "id"
    )

    await query.edit_message_text(
        "⏳ جارٍ إرسال التبليغ...\n\n"
        "يرجى الانتظار حتى انتهاء العملية."
    )

    try:
        (
            total,
            successful,
            failed,
            status,
        ) = await _send_notification(
            notification_id,
            context.bot,
            audience_type,
            audience_value,
            title,
            content,
        )

    except Exception as exc:
        print(
            "SEND NOTIFICATION ERROR:",
            type(exc).__name__,
            exc,
        )

        try:
            (
                supabase
                .table("notifications")
                .update({
                    "status": "failed",
                })
                .eq(
                    "id",
                    notification_id,
                )
                .execute()
            )

        except Exception as update_exc:
            print(
                "UPDATE FAILED NOTIFICATION ERROR:",
                type(update_exc).__name__,
                update_exc,
            )

        await query.edit_message_text(
            "❌ حدث خطأ أثناء إرسال التبليغ."
        )

        _clear_notification(context)

        return ConversationHandler.END

    if status == "sent":
        result_title = (
            "✅ تم إرسال التبليغ بنجاح."
        )

    else:
        result_title = (
            "⚠️ اكتمل إرسال التبليغ مع وجود أخطاء."
        )

    await query.edit_message_text(
        f"{result_title}\n\n"
        f"📊 إجمالي المستلمين: {total}\n"
        f"✅ تم الإرسال: {successful}\n"
        f"❌ فشل الإرسال: {failed}\n\n"
        f"🆔 Notification ID: {notification_id}",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text="⬅️ لوحة الإدارة",
                    callback_data="admin_back",
                )
            ]
        ]),
    )

    _clear_notification(context)

    return ConversationHandler.END


# ============================================================
# Create notification
# ============================================================

async def _create_notification(
    user_id: int,
    title: str,
    content: str,
    audience_type: str,
    audience_value=None,
):
    response = (
        supabase
        .table("notifications")
        .insert({
            "title": title,
            "content": content,
            "audience_type": audience_type,
            "audience_value": audience_value,
            "status": "draft",
            "total_recipients": 0,
            "successful_sends": 0,
            "failed_sends": 0,
            "created_by": user_id,
        })
        .execute()
    )

    rows = response.data or []

    if not rows:
        raise RuntimeError(
            "Notification row was not created."
        )

    return rows[0]


# ============================================================
# Get recipients
# ============================================================

async def _get_recipients(
    audience_type: str,
    audience_value=None,
):
    if audience_type == "all_users":
        response = (
            supabase
            .table("telegram_users")
            .select("telegram_id")
            .execute()
        )

        recipients = []

        for row in response.data or []:
            telegram_id = row.get(
                "telegram_id"
            )

            if telegram_id is None:
                continue

            try:
                recipients.append(
                    int(telegram_id)
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

        return list(
            dict.fromkeys(
                recipients
            )
        )

    if audience_type in (
        "user",
        "group",
        "channel",
    ):
        if audience_value is None:
            return []

        try:
            target = int(audience_value)
            if (audience_type == "user" and target <= 0) or (audience_type != "user" and target >= 0):
                return []
            return [target]

        except (
            TypeError,
            ValueError,
        ):
            return []

    return []


# ============================================================
# Send notification
# ============================================================

async def _send_notification(
    notification_id: int,
    bot,
    audience_type: str,
    audience_value,
    title: str,
    content: str,
):
    recipients = await _get_recipients(
        audience_type,
        audience_value,
    )

    total = len(recipients)

    (
        supabase
        .table("notifications")
        .update({
            "status": "sending",
            "total_recipients": total,
            "successful_sends": 0,
            "failed_sends": 0,
        })
        .eq(
            "id",
            notification_id,
        )
        .execute()
    )

    if total == 0:
        (
            supabase
            .table("notifications")
            .update({
                "status": "failed",
                "sent_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            })
            .eq(
                "id",
                notification_id,
            )
            .execute()
        )

        return (
            0,
            0,
            0,
            "failed",
        )

    text = (
        f"📢 {title}\n\n"
        f"{content}"
    )

    successful = 0
    failed = 0

    for chat_id in recipients:
        sent = False

        if audience_type in {"group", "channel"}:
            destination = await accessible_chat(bot, chat_id, audience_type)
            if destination is None:
                failed += 1
                continue
            chat_id = destination.id

        for attempt in range(2):
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                )

                successful += 1
                sent = True
                break

            except RetryAfter as exc:
                if attempt == 0:
                    await asyncio.sleep(
                        float(
                            exc.retry_after
                        )
                    )
                    continue

                break

            except ChatMigrated as exc:
                if audience_type not in {"group", "channel"}:
                    break
                mark_chat_inactive(chat_id)
                destination = await accessible_chat(bot, exc.new_chat_id, audience_type, migrated=True)
                if destination is None:
                    break
                chat_id = destination.id
                continue

            except Forbidden:
                if audience_type in {"group", "channel"}:
                    mark_chat_inactive(chat_id)
                break

            except BadRequest as exc:
                if audience_type in {"group", "channel"} and any(
                    reason in str(exc).lower() for reason in (
                        "chat not found", "group chat was deleted", "bot was kicked",
                        "bot is not a member", "channel_private",
                    )
                ):
                    mark_chat_inactive(chat_id)
                break

            except TelegramError:
                break

            except Exception as exc:
                print(
                    "NOTIFICATION SEND ERROR:",
                    type(exc).__name__,
                    exc,
                )
                break

        if not sent:
            failed += 1

        await asyncio.sleep(0.05)

    if failed == 0:
        status = "sent"

    elif successful == 0:
        status = "failed"

    else:
        status = "completed_with_errors"

    (
        supabase
        .table("notifications")
        .update({
            "status": status,
            "successful_sends": successful,
            "failed_sends": failed,
            "sent_at": datetime.now(
                timezone.utc
            ).isoformat(),
        })
        .eq(
            "id",
            notification_id,
        )
        .execute()
    )

    return (
        total,
        successful,
        failed,
        status,
    )


# ============================================================
# Conversation handler
# ============================================================

async def back_from_notification_operation(update, context):
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or _get_notification_owner(context) != user.id:
        return None
    allowed = await _has_notification_permission(user.id)
    _clear_notification(context)
    if not allowed:
        await query.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return ConversationHandler.END
    from bot.handlers.admin import admin_back
    await admin_back(update, context)
    return ConversationHandler.END


def notification_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                admin_notifications,
                pattern=r"^admin_announcements$",
            )
        ],
        states={
            NOTIFICATION_AUDIENCE: [
                CallbackQueryHandler(
                    notification_audience,
                    pattern=(
                        r"^notify_audience:"
                    ),
                ),
                CallbackQueryHandler(
                    notification_chat,
                    pattern=r"^notify_chat:",
                ),
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    notification_user_id,
                ),
            ],
            NOTIFICATION_TITLE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    notification_title,
                ),
            ],
            NOTIFICATION_CONTENT: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    notification_content,
                ),
            ],
            NOTIFICATION_CONFIRM: [
                CallbackQueryHandler(
                    notification_confirm,
                    pattern=(
                        r"^notify_confirm:"
                    ),
                ),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(back_from_notification_operation, pattern=r"^admin_back$"),
            CallbackQueryHandler(
                notification_cancel,
                pattern=r"^notify_cancel:",
            ),
        ],
        per_user=True,
        per_chat=True,
        allow_reentry=True,
    )


# ============================================================
# Cancel
# ============================================================

async def notification_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not await require_callback_owner(query):
        return None

    if query is None or query.from_user is None:
        return None

    user_id = query.from_user.id

    if not _is_notification_owner(
        user_id,
        context,
    ):
        await query.answer(
            "⛔ هذا التبليغ مو إلك.",
            show_alert=True,
        )
        return None

    if query.data.split(":") != ["notify_cancel", str(user_id)]:
        return None

    try:
        allowed = await _has_notification_permission(user_id)
    except Exception as exc:
        print("NOTIFICATION CANCEL PERMISSION ERROR:", type(exc).__name__)
        allowed = False

    _clear_notification(context)

    await query.answer()

    await query.edit_message_text(
        "❌ تم إلغاء التبليغ." if allowed else "❌ تم إلغاء التبليغ. لم تعد لديك صلاحية الإرسال."
    )

    return ConversationHandler.END
