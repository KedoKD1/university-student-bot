from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)

from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from bot.database.client import supabase
from bot.utils.permissions import (
    PERMISSION_MANAGE_SETTINGS,
    has_permission,
)


SETTING_VALUE = 1


ALLOWED_SETTINGS = {
    "required_channel_id": (
        "📢 Required Channel ID"
    ),
    "student_group_id": (
        "👥 Student Group ID"
    ),
    "maintenance_mode": (
        "🔧 Maintenance Mode"
    ),
}


async def _has_permission(
    update: Update,
):
    user = update.effective_user

    if user is None:
        return False

    return await has_permission(
        user.id,
        PERMISSION_MANAGE_SETTINGS,
    )


def _settings_keyboard(settings):
    keyboard = []

    for key, label in ALLOWED_SETTINGS.items():
        value = settings.get(key)

        if value is None:
            display = "غير مضبوط"
        else:
            display = str(value)

        keyboard.append([
            InlineKeyboardButton(
                text=f"{label}: {display}",
                callback_data=f"admin_setting_edit:{key}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ لوحة الإدارة",
            callback_data="admin_back",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


async def _load_settings():
    response = (
        supabase
        .table("settings")
        .select("key, value")
        .execute()
    )

    result = {}

    for row in response.data or []:
        key = row.get("key")

        if key in ALLOWED_SETTINGS:
            result[key] = row.get("value")

    return result


async def admin_settings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    if not await _has_permission(update):
        await query.answer(
            "⛔ ليس لديك صلاحية إدارة الإعدادات.",
            show_alert=True,
        )
        return

    try:
        settings = await _load_settings()

    except Exception as exc:
        print(
            "LOAD SETTINGS ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ تعذر تحميل الإعدادات.",
            show_alert=True,
        )
        return

    await query.answer()

    await query.edit_message_text(
        "⚙️ إعدادات LabBase\n\n"
        "هذه القيم محفوظة في قاعدة البيانات.\n"
        "تعديلها هنا لا يغيّر Railway Environment "
        "Variables تلقائياً.",
        reply_markup=_settings_keyboard(
            settings
        ),
    )


async def setting_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return ConversationHandler.END

    if not await _has_permission(update):
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
            "❌ إعداد غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    key = parts[1]

    if key not in ALLOWED_SETTINGS:
        await query.answer(
            "❌ إعداد غير مسموح.",
            show_alert=True,
        )
        return ConversationHandler.END

    context.user_data[
        "editing_setting"
    ] = key

    await query.answer()

    await query.edit_message_text(
        f"⚙️ تعديل الإعداد\n\n"
        f"{ALLOWED_SETTINGS[key]}\n\n"
        "أرسل القيمة الجديدة.\n\n"
        "للـ Maintenance Mode استخدم:\n"
        "`true` أو `false`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text="❌ إلغاء",
                    callback_data="admin_setting_cancel",
                )
            ]
        ]),
    )

    return SETTING_VALUE


async def setting_receive_value(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if (
        update.message is None
        or update.effective_user is None
    ):
        return SETTING_VALUE

    if not await _has_permission(update):
        await update.message.reply_text(
            "⛔ ليس لديك صلاحية."
        )
        return ConversationHandler.END

    key = context.user_data.get(
        "editing_setting"
    )

    if key not in ALLOWED_SETTINGS:
        await update.message.reply_text(
            "❌ لا يوجد إعداد قيد التعديل."
        )
        return ConversationHandler.END

    value = (
        update.message.text or ""
    ).strip()

    if not value:
        await update.message.reply_text(
            "❌ القيمة لا يمكن أن تكون فارغة."
        )
        return SETTING_VALUE

    if key == "maintenance_mode":
        normalized = value.lower()

        if normalized not in (
            "true",
            "false",
        ):
            await update.message.reply_text(
                "❌ يجب أن تكون القيمة:\n"
                "`true` أو `false`",
                parse_mode="Markdown",
            )
            return SETTING_VALUE

        value = normalized

    if len(value) > 500:
        await update.message.reply_text(
            "❌ القيمة طويلة جداً."
        )
        return SETTING_VALUE

    try:
        (
            supabase
            .table("settings")
            .upsert(
                {
                    "key": key,
                    "value": value,
                    "updated_by": (
                        update.effective_user.id
                    ),
                },
                on_conflict="key",
            )
            .execute()
        )

    except Exception as exc:
        print(
            "UPDATE SETTING ERROR:",
            type(exc).__name__,
            exc,
        )

        await update.message.reply_text(
            "❌ تعذر حفظ الإعداد."
        )
        return ConversationHandler.END

    context.user_data.pop(
        "editing_setting",
        None,
    )

    settings = await _load_settings()

    await update.message.reply_text(
        "✅ تم تحديث الإعداد بنجاح.",
        reply_markup=_settings_keyboard(
            settings
        ),
    )

    return ConversationHandler.END


async def setting_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return ConversationHandler.END

    context.user_data.pop(
        "editing_setting",
        None,
    )

    await query.answer()

    try:
        settings = await _load_settings()

        await query.edit_message_text(
            "⚙️ إعدادات LabBase",
            reply_markup=_settings_keyboard(
                settings
            ),
        )

    except Exception as exc:
        print(
            "SETTING CANCEL ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.edit_message_text(
            "⚙️ إعدادات LabBase"
        )

    return ConversationHandler.END


def settings_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                setting_edit,
                pattern=r"^admin_setting_edit:",
            )
        ],
        states={
            SETTING_VALUE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    setting_receive_value,
                )
            ]
        },
        fallbacks=[
            CallbackQueryHandler(
                setting_cancel,
                pattern=r"^admin_setting_cancel$",
            )
        ],
        allow_reentry=False,
    )
