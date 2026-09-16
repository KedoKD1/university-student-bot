import asyncio

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.error import (
    Forbidden,
    BadRequest,
    RetryAfter,
    TelegramError,
)
from telegram.ext import (
    ConversationHandler,
    ContextTypes,
)

from bot.database.client import supabase
from bot.utils.permissions import (
    PERMISSION_MANAGE_ANNOUNCEMENTS,
    has_permission,
)


# ============================================================
# Conversation states
# ============================================================

NOTIFICATION_TITLE = 1
NOTIFICATION_CONTENT = 2
NOTIFICATION_TARGET_VALUE = 3


# ============================================================
# Helpers
# ============================================================

def _menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="➕ تبليغ جديد",
                callback_data="admin_notify_new",
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ لوحة الإدارة",
                callback_data="admin_back",
            )
        ],
    ])


def _audience_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="👥 جميع المستخدمين",
                callback_data="admin_notify_audience:all_users",
            )
        ],
        [
            InlineKeyboardButton(
                text="👤 مستخدم محدد",
                callback_data="admin_notify_audience:user",
            )
        ],
        [
            InlineKeyboardButton(
                text="👥 مجموعة محددة",
                callback_data="admin_notify_audience:group",
            )
        ],
        [
            InlineKeyboardButton(
                text="📢 قناة محددة",
                callback_data="admin_notify_audience:channel",
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ إلغاء",
                callback_data="admin_notify_cancel",
            )
        ],
    ])


def _preview_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="📤 إرسال التبليغ",
                callback_data="admin_notify_send",
            )
        ],
        [
            InlineKeyboardButton(
                text="🗑️ حذف المسودة",
                callback_data="admin_notify_delete",
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ إلغاء",
                callback_data="admin_notify_cancel",
            )
        ],
    ])


def _audience_name(
    audience_type: str,
    audience_value=None,
):
    if audience_type == "all_users":
        return "جميع المستخدمين المسجلين"

    if audience_type == "user":
        return f"المستخدم: {audience_value}"

    if audience_type == "group":
        return f"المجموعة: {audience_value}"

    if audience_type == "channel":
        return f"القناة: {audience_value}"

    return "غير معروف"


async def _check_permission(
    update: Update,
):
    user = update.effective_user

    if user is None:
        return False

    return await has_permission(
        user.id,
        PERMISSION_MANAGE_ANNOUNCEMENTS,
    )


# ============================================================
# Main announcements section
# ============================================================

async def admin_notifications(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    if not await _check_permission(update):
        await query.answer(
            "⛔ ليس لديك صلاحية إدارة التبليغات.",
            show_alert=True,
        )
        return

    await query.answer()

    await query.edit_message_text(
        "📢 إدارة التبليغات\n\n"
        "يمكنك إنشاء تبليغ جديد وإرساله "
        "إلى المستخدمين أو إلى مجموعة/قناة محددة.",
        reply_markup=_menu_keyboard(),
    )


# ============================================================
# Start new notification
# ============================================================

async def notification_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return ConversationHandler.END

    if not await _check_permission(update):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    context.user_data["notification"] = {}

    await query.answer()

    await query.edit_message_text(
        "➕ إنشاء تبليغ جديد\n\n"
        "أرسل عنوان التبليغ:",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text="❌ إلغاء",
                    callback_data="admin_notify_cancel",
                )
            ]
        ]),
    )

    return NOTIFICATION_TITLE


# ============================================================
# Receive title
# ============================================================

async def notification_title(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if (
        update.message is None
        or update.effective_user is None
    ):
        return NOTIFICATION_TITLE

    if not await _check_permission(update):
        await update.message.reply_text(
            "⛔ ليس لديك صلاحية."
        )
        return ConversationHandler.END

    title = (
        update.message.text or ""
    ).strip()

    if not title:
        await update.message.reply_text(
            "❌ العنوان لا يمكن أن يكون فارغاً.\n\n"
            "أرسل عنوان التبليغ:"
        )
        return NOTIFICATION_TITLE

    if len(title) > 200:
        await update.message.reply_text(
            "❌ العنوان طويل جداً.\n"
            "الحد الأقصى 200 حرف.\n\n"
            "أرسل عنواناً أقصر:"
        )
        return NOTIFICATION_TITLE

    context.user_data.setdefault(
        "notification",
        {},
    )["title"] = title

    await update.message.reply_text(
        "📝 أرسل محتوى التبليغ الآن.\n\n"
        "يمكنك استخدام نص عادي."
    )

    return NOTIFICATION_CONTENT


# ============================================================
# Receive content
# ============================================================

async def notification_content(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if (
        update.message is None
        or update.effective_user is None
    ):
        return NOTIFICATION_CONTENT

    if not await _check_permission(update):
        await update.message.reply_text(
            "⛔ ليس لديك صلاحية."
        )
        return ConversationHandler.END

    content = (
        update.message.text or ""
    ).strip()

    if not content:
        await update.message.reply_text(
            "❌ المحتوى لا يمكن أن يكون فارغاً.\n\n"
            "أرسل محتوى التبليغ:"
        )
        return NOTIFICATION_CONTENT

    context.user_data.setdefault(
        "notification",
        {},
    )["content"] = content

    await update.message.reply_text(
        "🎯 اختر الجمهور المستهدف:",
        reply_markup=_audience_keyboard(),
    )

    return NOTIFICATION_TARGET_VALUE


# ============================================================
# Audience selection
# ============================================================

async def notification_audience(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return ConversationHandler.END

    if not await _check_permission(update):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    parts = (
        query.data or ""
    ).split(":", 1)

    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return NOTIFICATION_TARGET_VALUE

    audience_type = parts[1]

    notification = context.user_data.setdefault(
        "notification",
        {},
    )

    notification["audience_type"] = audience_type

    if audience_type == "all_users":
        notification["audience_value"] = None

        await query.answer()

        return await _create_draft_and_preview(
            update,
            context,
        )

    labels = {
        "user": "Telegram User ID",
        "group": "Chat ID الخاص بالمجموعة",
        "channel": "Chat ID الخاص بالقناة",
    }

    label = labels.get(
        audience_type,
        "القيمة",
    )

    await query.answer()

    await query.edit_message_text(
        f"🎯 الجمهور: {_audience_name(audience_type)}\n\n"
        f"أرسل {label} الآن.\n\n"
        "مثال:\n"
        "`123456789`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text="❌ إلغاء",
                    callback_data="admin_notify_cancel",
                )
            ]
        ]),
    )

    return NOTIFICATION_TARGET_VALUE


# ============================================================
# Receive specific audience value
# ============================================================

async def notification_target_value(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if (
        update.message is None
        or update.effective_user is None
    ):
        return NOTIFICATION_TARGET_VALUE

    if not await _check_permission(update):
        await update.message.reply_text(
            "⛔ ليس لديك صلاحية."
        )
        return ConversationHandler.END

    value = (
        update.message.text or ""
    ).strip()

    try:
        int(value)
    except ValueError:
        await update.message.reply_text(
            "❌ يجب إرسال رقم Telegram/Chat ID صحيح."
        )
        return NOTIFICATION_TARGET_VALUE

    notification = context.user_data.setdefault(
        "notification",
        {},
    )

    notification["audience_value"] = value

    return await _create_draft_and_preview(
        update,
        context,
    )


# ============================================================
# Create draft
# ============================================================

async def _create_draft_and_preview(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    if user is None:
        return ConversationHandler.END

    notification = context.user_data.get(
        "notification"
    )

    if not notification:
        return ConversationHandler.END

    try:
        response = (
            supabase
            .table("notifications")
            .insert({
                "title": notification["title"],
                "content": notification["content"],
                "audience_type": notification[
                    "audience_type"
                ],
                "audience_value": notification.get(
                    "audience_value"
                ),
                "status": "draft",
                "created_by": user.id,
            })
            .execute()
        )

        rows = response.data or []

        if not rows:
            raise RuntimeError(
                "Notification draft was not created."
            )

        notification["id"] = rows[0]["id"]

    except Exception as exc:
        print(
            "CREATE NOTIFICATION DRAFT ERROR:",
            type(exc).__name__,
            exc,
        )

        message = (
            "❌ تعذر إنشاء مسودة التبليغ.\n\n"
            "لم يتم إنشاء أي إرسال."
        )

        if update.callback_query is not None:
            await update.callback_query.answer(
                "❌ تعذر إنشاء المسودة.",
                show_alert=True,
            )
            await update.callback_query.edit_message_text(
                message
            )
        elif update.message is not None:
            await update.message.reply_text(
                message
            )

        context.user_data.pop(
            "notification",
            None,
        )

        return ConversationHandler.END

    text = (
        "📋 معاينة التبليغ\n\n"
        f"🆔 المسودة: #{notification['id']}\n\n"
        f"📌 العنوان:\n"
        f"{notification['title']}\n\n"
        f"📝 المحتوى:\n"
        f"{notification['content']}\n\n"
        f"🎯 الجمهور:\n"
        f"{_audience_name("
        f"notification['audience_type'], "
        f"notification.get('audience_value')"
        f")}\n\n"
        "⚠️ التبليغ محفوظ كمسودة ولم يتم إرساله بعد."
    )

    if update.callback_query is not None:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=_preview_keyboard(),
        )
        await update.callback_query.answer()

    elif update.message is not None:
        await update.message.reply_text(
            text,
            reply_markup=_preview_keyboard(),
        )

    return ConversationHandler.END


# ============================================================
# Send notification
# ============================================================

async def send_notification(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    if not await _check_permission(update):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    notification = context.user_data.get(
        "notification"
    )

    if not notification:
        await query.answer(
            "❌ لا توجد مسودة نشطة.",
            show_alert=True,
        )
        return

    notification_id = notification.get("id")

    if not notification_id:
        await query.answer(
            "❌ رقم المسودة غير موجود.",
            show_alert=True,
        )
        return

    await query.answer(
        "⏳ جارٍ تجهيز الإرسال..."
    )

    try:
        response = (
            supabase
            .table("notifications")
            .select("*")
            .eq("id", notification_id)
            .limit(1)
            .execute()
        )

        rows = response.data or []

        if not rows:
            await query.edit_message_text(
                "❌ المسودة غير موجودة."
            )
            return

        row = rows[0]

        if row.get("status") != "draft":
            await query.edit_message_text(
                "⚠️ هذه المسودة لم تعد قابلة للإرسال."
            )
            return

        recipients = await _get_recipients(
            row
        )

        if not recipients:
            await query.edit_message_text(
                "⚠️ لم يتم العثور على أي مستلمين.\n\n"
                "تأكد من أن المستخدمين تفاعلوا مع "
                "البوت مسبقاً أو أن Chat ID صحيح."
            )
            return

        await query.edit_message_text(
            "📤 جارٍ إرسال التبليغ...\n\n"
            f"عدد المستلمين: {len(recipients)}"
        )

        successful = 0
        failed = 0

        for recipient in recipients:
            try:
                await _send_to_recipient(
                    context,
                    recipient,
                    row["title"],
                    row["content"],
                )

                successful += 1

            except RetryAfter as exc:
                retry_seconds = int(
                    getattr(
                        exc,
                        "retry_after",
                        1,
                    )
                )

                await asyncio.sleep(
                    retry_seconds
                )

                try:
                    await _send_to_recipient(
                        context,
                        recipient,
                        row["title"],
                        row["content"],
                    )
                    successful += 1
                except Exception:
                    failed += 1

            except (
                Forbidden,
                BadRequest,
                TelegramError,
            ):
                failed += 1

            except Exception as exc:
                print(
                    "NOTIFICATION SEND ERROR:",
                    type(exc).__name__,
                    exc,
                )
                failed += 1

            await asyncio.sleep(0.05)

        status = (
            "sent"
            if failed == 0
            else "partial"
            if successful > 0
            else "failed"
        )

        (
            supabase
            .table("notifications")
            .update({
                "status": status,
                "total_recipients": len(
                    recipients
                ),
                "successful_sends": successful,
                "failed_sends": failed,
                "sent_at": (
                    "now()"
                ),
            })
            .eq("id", notification_id)
            .execute()
        )

        await query.edit_message_text(
            "✅ اكتمل إرسال التبليغ.\n\n"
            f"🆔 المسودة: #{notification_id}\n"
            f"👥 إجمالي المستلمين: {len(recipients)}\n"
            f"✅ نجح: {successful}\n"
            f"❌ فشل: {failed}\n\n"
            f"📊 الحالة: {status}"
        )

        context.user_data.pop(
            "notification",
            None,
        )

    except Exception as exc:
        print(
            "SEND NOTIFICATION ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.edit_message_text(
            "❌ حدث خطأ أثناء إرسال التبليغ.\n\n"
            "لم يتم إخفاء تفاصيل الخطأ للمستخدم "
            "لحماية معلومات النظام."
        )


# ============================================================
# Get recipients
# ============================================================

async def _get_recipients(notification):
    audience_type = notification.get(
        "audience_type"
    )

    audience_value = notification.get(
        "audience_value"
    )

    if audience_type == "all_users":
        response = (
            supabase
            .table("telegram_users")
            .select("telegram_id")
            .execute()
        )

        return [
            row["telegram_id"]
            for row in (
                response.data or []
            )
            if row.get("telegram_id")
        ]

    if audience_type == "user":
        return [int(audience_value)]

    if audience_type in (
        "group",
        "channel",
    ):
        return [int(audience_value)]

    return []


# ============================================================
# Telegram send helper
# ============================================================

async def _send_to_recipient(
    context,
    recipient,
    title,
    content,
):
    text = (
        f"📢 {title}\n\n"
        f"{content}"
    )

    await context.bot.send_message(
        chat_id=recipient,
        text=text,
    )


# ============================================================
# Delete draft
# ============================================================

async def delete_notification(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    if not await _check_permission(update):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    notification = context.user_data.get(
        "notification"
    )

    if not notification:
        await query.answer(
            "❌ لا توجد مسودة نشطة.",
            show_alert=True,
        )
        return

    notification_id = notification.get(
        "id"
    )

    try:
        (
            supabase
            .table("notifications")
            .delete()
            .eq("id", notification_id)
            .eq("status", "draft")
            .execute()
        )

        context.user_data.pop(
            "notification",
            None,
        )

        await query.answer(
            "🗑️ تم حذف المسودة."
        )

        await query.edit_message_text(
            "🗑️ تم حذف مسودة التبليغ بنجاح."
        )

    except Exception as exc:
        print(
            "DELETE NOTIFICATION ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ تعذر حذف المسودة.",
            show_alert=True,
        )


# ============================================================
# Cancel
# ============================================================

async def cancel_notification(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.callback_query is not None:
        query = update.callback_query

        if not await _check_permission(update):
            await query.answer(
                "⛔ ليس لديك صلاحية.",
                show_alert=True,
            )
            return ConversationHandler.END

        context.user_data.pop(
            "notification",
            None,
        )

        await query.answer()

        await query.edit_message_text(
            "❌ تم إلغاء إنشاء التبليغ."
        )

        return ConversationHandler.END

    if update.message is not None:
        context.user_data.pop(
            "notification",
            None,
        )

        await update.message.reply_text(
            "❌ تم إلغاء إنشاء التبليغ."
        )

    return ConversationHandler.END


# ============================================================
# Conversation Handler
# ============================================================

def notification_conversation_handler():
    return ConversationHandler(
        entry_points=[
            __import__(
                "telegram.ext",
                fromlist=[
                    "CallbackQueryHandler"
                ],
            ).CallbackQueryHandler(
                notification_start,
                pattern=r"^admin_notify_new$",
            )
        ],
        states={
            NOTIFICATION_TITLE: [
                __import__(
                    "telegram.ext",
                    fromlist=[
                        "MessageHandler"
                    ],
                ).MessageHandler(
                    __import__(
                        "telegram.ext",
                        fromlist=[
                            "filters"
                        ],
                    ).filters.TEXT
                    & ~__import__(
                        "telegram.ext",
                        fromlist=[
                            "filters"
                        ],
                    ).filters.COMMAND,
                    notification_title,
                )
            ],
            NOTIFICATION_CONTENT: [
                __import__(
                    "telegram.ext",
                    fromlist=[
                        "MessageHandler"
                    ],
                ).MessageHandler(
                    __import__(
                        "telegram.ext",
                        fromlist=[
                            "filters"
                        ],
                    ).filters.TEXT
                    & ~__import__(
                        "telegram.ext",
                        fromlist=[
                            "filters"
                        ],
                    ).filters.COMMAND,
                    notification_content,
                )
            ],
            NOTIFICATION_TARGET_VALUE: [
                __import__(
                    "telegram.ext",
                    fromlist=[
                        "CallbackQueryHandler"
                    ],
                ).CallbackQueryHandler(
                    notification_audience,
                    pattern=r"^admin_notify_audience:",
                ),
                __import__(
                    "telegram.ext",
                    fromlist=[
                        "MessageHandler"
                    ],
                ).MessageHandler(
                    __import__(
                        "telegram.ext",
                        fromlist=[
                            "filters"
                        ],
                    ).filters.TEXT
                    & ~__import__(
                        "telegram.ext",
                        fromlist=[
                            "filters"
                        ],
                    ).filters.COMMAND,
                    notification_target_value,
                ),
            ],
        },
        fallbacks=[
            __import__(
                "telegram.ext",
                fromlist=[
                    "CallbackQueryHandler"
                ],
            ).CallbackQueryHandler(
                cancel_notification,
                pattern=r"^admin_notify_cancel$",
            )
        ],
        allow_reentry=False,
    )
