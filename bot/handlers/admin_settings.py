from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.database.client import supabase
from bot.utils.permissions import (
    PERMISSION_MANAGE_SETTINGS,
    has_permission,
)


# ============================================================
# Conversation states
# ============================================================

(
    SETTINGS_MENU,
    SETTINGS_VALUE,
) = range(2)


# ============================================================
# Supported settings
# ============================================================

SETTING_REQUIRED_CHANNEL_ID = (
    "required_channel_id"
)

SETTING_STUDENT_GROUP_ID = (
    "student_group_id"
)

SETTING_MAINTENANCE_MODE = (
    "maintenance_mode"
)

SUPPORTED_SETTINGS = {
    SETTING_REQUIRED_CHANNEL_ID: {
        "title": "🔗 Required Channel ID",
        "description": (
            "معرّف القناة الإلزامية التي يجب على "
            "الطالب الاشتراك بها."
        ),
    },
    SETTING_STUDENT_GROUP_ID: {
        "title": "👥 Student Group ID",
        "description": (
            "معرّف مجموعة الطلاب الأساسية."
        ),
    },
    SETTING_MAINTENANCE_MODE: {
        "title": "🔧 Maintenance Mode",
        "description": (
            "وضع الصيانة العام للبوت."
        ),
    },
}


# ============================================================
# Permission
# ============================================================

async def _has_settings_permission(
    user_id: int,
) -> bool:
    return await has_permission(
        user_id,
        PERMISSION_MANAGE_SETTINGS,
    )


# ============================================================
# Database helpers
# ============================================================

async def _get_setting(
    key: str,
):
    try:
        response = (
            supabase
            .table("settings")
            .select(
                "id, key, value, updated_by, updated_at"
            )
            .eq("key", key)
            .limit(1)
            .execute()
        )

        rows = response.data or []

        if not rows:
            return None

        return rows[0]

    except Exception as exc:
        print(
            "GET SETTING ERROR:",
            type(exc).__name__,
            exc,
        )
        return None


async def _save_setting(
    key: str,
    value: str,
    user_id: int,
):
    existing = await _get_setting(key)

    if existing:
        response = (
            supabase
            .table("settings")
            .update({
                "value": value,
                "updated_by": user_id,
                "updated_at": "now()",
            })
            .eq(
                "key",
                key,
            )
            .execute()
        )

    else:
        response = (
            supabase
            .table("settings")
            .insert({
                "key": key,
                "value": value,
                "updated_by": user_id,
            })
            .execute()
        )

    return response.data or []


# ============================================================
# Environment fallback
# ============================================================

def _get_environment_fallback(
    key: str,
):
    if key == SETTING_REQUIRED_CHANNEL_ID:
        try:
            from bot.utils.config import (
                REQUIRED_CHANNEL_ID,
            )

            return REQUIRED_CHANNEL_ID

        except ImportError:
            return None

    if key == SETTING_STUDENT_GROUP_ID:
        try:
            from bot.utils.config import (
                STUDENT_GROUP_ID,
            )

            return STUDENT_GROUP_ID

        except ImportError:
            return None

    if key == SETTING_MAINTENANCE_MODE:
        return "false"

    return None


# ============================================================
# Display value
# ============================================================

async def _get_display_value(
    key: str,
):
    setting = await _get_setting(key)

    if setting is not None:
        value = setting.get("value")

        if value is not None and str(value).strip():
            return str(value)

    fallback = _get_environment_fallback(key)

    if fallback is None:
        return "غير مضبوط"

    return str(fallback)


# ============================================================
# Settings keyboard
# ============================================================

def _settings_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="🔗 Required Channel ID",
                callback_data=(
                    "setting_edit:"
                    f"{SETTING_REQUIRED_CHANNEL_ID}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="👥 Student Group ID",
                callback_data=(
                    "setting_edit:"
                    f"{SETTING_STUDENT_GROUP_ID}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="🔧 Maintenance Mode",
                callback_data=(
                    "setting_edit:"
                    f"{SETTING_MAINTENANCE_MODE}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 تحديث",
                callback_data="setting_refresh",
            ),
            InlineKeyboardButton(
                text="❌ إغلاق",
                callback_data="setting_cancel",
            ),
        ],
    ])


# ============================================================
# Settings screen
# ============================================================

async def _settings_text():
    channel_id = await _get_display_value(
        SETTING_REQUIRED_CHANNEL_ID
    )

    group_id = await _get_display_value(
        SETTING_STUDENT_GROUP_ID
    )

    maintenance = await _get_display_value(
        SETTING_MAINTENANCE_MODE
    )

    maintenance_lower = (
        maintenance.lower()
    )

    if maintenance_lower in (
        "true",
        "1",
        "yes",
        "on",
    ):
        maintenance_display = "🟢 مفعّل"

    elif maintenance_lower in (
        "false",
        "0",
        "no",
        "off",
    ):
        maintenance_display = "🔴 غير مفعّل"

    else:
        maintenance_display = maintenance

    return (
        "⚙️ إعدادات LabBase\n\n"
        "الإعدادات الحالية:\n\n"
        f"🔗 Required Channel ID:\n"
        f"`{channel_id}`\n\n"
        f"👥 Student Group ID:\n"
        f"`{group_id}`\n\n"
        f"🔧 Maintenance Mode:\n"
        f"{maintenance_display}\n\n"
        "اختر الإعداد الذي تريد تعديله:"
    )


# ============================================================
# Entry point
# ============================================================

async def admin_settings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return ConversationHandler.END

    if not await _has_settings_permission(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    context.user_data.pop(
        "admin_setting",
        None,
    )

    await query.answer()

    await query.edit_message_text(
        await _settings_text(),
        reply_markup=_settings_keyboard(),
        parse_mode="Markdown",
    )

    return SETTINGS_MENU


# ============================================================
# Refresh
# ============================================================

async def settings_refresh(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return ConversationHandler.END

    if not await _has_settings_permission(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    await query.answer(
        "🔄 تم تحديث الإعدادات."
    )

    await query.edit_message_text(
        await _settings_text(),
        reply_markup=_settings_keyboard(),
        parse_mode="Markdown",
    )

    return SETTINGS_MENU


# ============================================================
# Open setting editor
# ============================================================

async def setting_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return ConversationHandler.END

    if not await _has_settings_permission(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    data = query.data or ""

    parts = data.split(":", 1)

    if len(parts) != 2:
        await query.answer(
            "❌ إعداد غير صالح.",
            show_alert=True,
        )
        return SETTINGS_MENU

    key = parts[1]

    if key not in SUPPORTED_SETTINGS:
        await query.answer(
            "❌ هذا الإعداد غير مدعوم.",
            show_alert=True,
        )
        return SETTINGS_MENU

    current_value = await _get_display_value(
        key
    )

    context.user_data[
        "admin_setting"
    ] = {
        "key": key,
    }

    setting_info = SUPPORTED_SETTINGS[key]

    await query.answer()

    if key == SETTING_MAINTENANCE_MODE:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text="🟢 تفعيل",
                    callback_data=(
                        "setting_value:true"
                    ),
                ),
                InlineKeyboardButton(
                    text="🔴 تعطيل",
                    callback_data=(
                        "setting_value:false"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ رجوع",
                    callback_data="setting_back",
                )
            ],
        ])

        await query.edit_message_text(
            f"{setting_info['title']}\n\n"
            f"{setting_info['description']}\n\n"
            f"القيمة الحالية:\n"
            f"`{current_value}`\n\n"
            "اختر الحالة:",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

        return SETTINGS_VALUE

    await query.edit_message_text(
        f"{setting_info['title']}\n\n"
        f"{setting_info['description']}\n\n"
        f"القيمة الحالية:\n"
        f"`{current_value}`\n\n"
        "أرسل القيمة الجديدة:",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text="⬅️ إلغاء",
                    callback_data="setting_back",
                )
            ]
        ]),
        parse_mode="Markdown",
    )

    return SETTINGS_VALUE


# ============================================================
# Save predefined value
# ============================================================

async def setting_predefined_value(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return ConversationHandler.END

    if not await _has_settings_permission(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    data = query.data or ""

    if not data.startswith(
        "setting_value:"
    ):
        return SETTINGS_VALUE

    setting_data = context.user_data.get(
        "admin_setting"
    )

    if not setting_data:
        await query.answer(
            "❌ انتهت جلسة تعديل الإعداد.",
            show_alert=True,
        )
        return ConversationHandler.END

    key = setting_data.get(
        "key"
    )

    if key != SETTING_MAINTENANCE_MODE:
        return SETTINGS_VALUE

    value = data.split(
        ":",
        1,
    )[1]

    try:
        await _save_setting(
            key,
            value,
            query.from_user.id,
        )

    except Exception as exc:
        print(
            "SAVE SETTING ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ تعذر حفظ الإعداد.",
            show_alert=True,
        )
        return SETTINGS_VALUE

    context.user_data.pop(
        "admin_setting",
        None,
    )

    await query.answer(
        "✅ تم حفظ الإعداد."
    )

    await query.edit_message_text(
        await _settings_text(),
        reply_markup=_settings_keyboard(),
        parse_mode="Markdown",
    )

    return SETTINGS_MENU


# ============================================================
# Save text value
# ============================================================

async def setting_value(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if (
        message is None
        or message.from_user is None
    ):
        return ConversationHandler.END

    if not await _has_settings_permission(
        message.from_user.id
    ):
        return ConversationHandler.END

    setting_data = context.user_data.get(
        "admin_setting"
    )

    if not setting_data:
        return ConversationHandler.END

    key = setting_data.get(
        "key"
    )

    if key not in (
        SETTING_REQUIRED_CHANNEL_ID,
        SETTING_STUDENT_GROUP_ID,
    ):
        return SETTINGS_VALUE

    value = (
        message.text or ""
    ).strip()

    if not value:
        await message.reply_text(
            "❌ القيمة لا يمكن أن تكون فارغة.\n\n"
            "أرسل القيمة الجديدة:"
        )
        return SETTINGS_VALUE

    if len(value) > 100:
        await message.reply_text(
            "❌ القيمة طويلة جداً."
        )
        return SETTINGS_VALUE

    try:
        int(value)

    except ValueError:
        await message.reply_text(
            "❌ القيمة يجب أن تكون رقمية.\n\n"
            "أرسل Telegram ID صحيح:"
        )
        return SETTINGS_VALUE

    try:
        await _save_setting(
            key,
            value,
            message.from_user.id,
        )

    except Exception as exc:
        print(
            "SAVE SETTING ERROR:",
            type(exc).__name__,
            exc,
        )

        await message.reply_text(
            "❌ تعذر حفظ الإعداد."
        )

        return SETTINGS_VALUE

    context.user_data.pop(
        "admin_setting",
        None,
    )

    await message.reply_text(
        "✅ تم حفظ الإعداد.\n\n"
        "سيظهر الآن ضمن إعدادات LabBase."
    )

    await message.reply_text(
        await _settings_text(),
        reply_markup=_settings_keyboard(),
        parse_mode="Markdown",
    )

    return SETTINGS_MENU


# ============================================================
# Back to settings
# ============================================================

async def setting_back(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return ConversationHandler.END

    if not await _has_settings_permission(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    context.user_data.pop(
        "admin_setting",
        None,
    )

    await query.answer()

    await query.edit_message_text(
        await _settings_text(),
        reply_markup=_settings_keyboard(),
        parse_mode="Markdown",
    )

    return SETTINGS_MENU


# ============================================================
# Cancel
# ============================================================

async def settings_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    context.user_data.pop(
        "admin_setting",
        None,
    )

    if query is not None:
        await query.answer()

        await query.edit_message_text(
            "❌ تم إغلاق إعدادات LabBase."
        )

    return ConversationHandler.END


# ============================================================
# Conversation handler
# ============================================================

def settings_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                admin_settings,
                pattern=r"^admin_settings$",
            )
        ],
        states={
            SETTINGS_MENU: [
                CallbackQueryHandler(
                    setting_edit,
                    pattern=r"^setting_edit:",
                ),
                CallbackQueryHandler(
                    settings_refresh,
                    pattern=r"^setting_refresh$",
                ),
                CallbackQueryHandler(
                    settings_cancel,
                    pattern=r"^setting_cancel$",
                ),
            ],
            SETTINGS_VALUE: [
                CallbackQueryHandler(
                    setting_predefined_value,
                    pattern=r"^setting_value:",
                ),
                CallbackQueryHandler(
                    setting_back,
                    pattern=r"^setting_back$",
                ),
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    setting_value,
                ),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(
                settings_cancel,
                pattern=r"^setting_cancel$",
            ),
        ],
        per_user=True,
        per_chat=True,
        allow_reentry=True,
    )
