from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)

from telegram.ext import ContextTypes

from bot.database.client import supabase

from bot.utils.permissions import (
    PERMISSION_MANAGE_SUBJECTS,
    PERMISSION_MANAGE_FILES,
    PERMISSION_MANAGE_SUMMARIES,
    PERMISSION_MANAGE_DRAWINGS,
    PERMISSION_MANAGE_SCHEDULES,
    PERMISSION_MANAGE_GRADES,
    PERMISSION_MANAGE_DESCRIPTIONS,
    PERMISSION_VIEW_STATISTICS,
    PERMISSION_MANAGE_ADMINS,
    PERMISSION_MANAGE_ANNOUNCEMENTS,
    PERMISSION_MANAGE_SETTINGS,
    has_permission,
)


# ============================================================
# Admin check
# ============================================================

async def is_admin(user_id: int) -> bool:
    response = (
        supabase
        .table("admins")
        .select(
            "id, telegram_id, role, is_active"
        )
        .eq("telegram_id", user_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    return bool(response.data)


# ============================================================
# Admin keyboard
# ============================================================

async def admin_keyboard(user_id: int):
    keyboard = []

    if await has_permission(
        user_id,
        PERMISSION_MANAGE_SUBJECTS,
    ):
        keyboard.append([
            InlineKeyboardButton(
                "📚 إدارة المواد",
                callback_data="admin_subjects",
            )
        ])

    if await has_permission(
        user_id,
        PERMISSION_MANAGE_FILES,
    ):
        keyboard.append([
            InlineKeyboardButton(
                "📄 إدارة الملفات",
                callback_data="admin_files",
            )
        ])

    if await has_permission(
        user_id,
        PERMISSION_MANAGE_SUMMARIES,
    ):
        keyboard.append([
            InlineKeyboardButton(
                "📝 إدارة الملخصات",
                callback_data="admin_summaries",
            )
        ])

    if await has_permission(
        user_id,
        PERMISSION_MANAGE_DRAWINGS,
    ):
        keyboard.append([
            InlineKeyboardButton(
                "🎨 إدارة الرسومات",
                callback_data="admin_drawings",
            )
        ])

    if await has_permission(
        user_id,
        PERMISSION_MANAGE_SCHEDULES,
    ):
        keyboard.append([
            InlineKeyboardButton(
                "📅 إدارة الجداول",
                callback_data="admin_schedules",
            )
        ])

    if await has_permission(
        user_id,
        PERMISSION_MANAGE_GRADES,
    ):
        keyboard.append([
            InlineKeyboardButton(
                "📝 إدارة الدرجات",
                callback_data="admin_grades",
            )
        ])

    has_tools = (
        await has_permission(
            user_id,
            PERMISSION_VIEW_STATISTICS,
        )
        or await has_permission(
            user_id,
            PERMISSION_MANAGE_ADMINS,
        )
        or await has_permission(
            user_id,
            PERMISSION_MANAGE_DESCRIPTIONS,
        )
    )

    if has_tools:
        keyboard.append([
            InlineKeyboardButton(
                "🧰 أدوات الإدارة",
                callback_data="admin_tools",
            )
        ])

    if await has_permission(
        user_id,
        PERMISSION_MANAGE_ANNOUNCEMENTS,
    ):
        keyboard.append([
            InlineKeyboardButton(
                "📢 الإعلانات",
                callback_data="admin_announcements",
            )
        ])

    if await has_permission(
        user_id,
        PERMISSION_MANAGE_SETTINGS,
    ):
        keyboard.append([
            InlineKeyboardButton(
                "⚙️ الإعدادات",
                callback_data="admin_settings",
            )
        ])

    return InlineKeyboardMarkup(keyboard)


# ============================================================
# Admin command
# ============================================================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    user_id = update.effective_user.id

    if not await is_admin(user_id):
        await update.message.reply_text(
            "⛔ عذراً، ليس لديك صلاحية "
            "الوصول إلى لوحة الإدارة."
        )
        return

    keyboard = await admin_keyboard(user_id)

    await update.message.reply_text(
        "🛠️ لوحة الإدارة\n\n"
        "أهلاً بك في لوحة إدارة LabBase.\n"
        "اختر القسم الذي تريد إدارته:",
        reply_markup=keyboard,
    )


# ============================================================
# Admin back
# ============================================================

async def admin_back(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return

    user_id = query.from_user.id

    if not await is_admin(user_id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    await query.answer()

    keyboard = await admin_keyboard(user_id)

    await query.edit_message_text(
        "🛠️ لوحة الإدارة\n\n"
        "أهلاً بك في لوحة إدارة LabBase.\n"
        "اختر القسم الذي تريد إدارته:",
        reply_markup=keyboard,
    )


# ============================================================
# Delete subject
# ============================================================

async def delete_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return

    user_id = query.from_user.id

    if not await has_permission(
        user_id,
        PERMISSION_MANAGE_SUBJECTS,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    subject_id = parts[1]
    stage_id = parts[2]

    response = (
        supabase
        .table("subjects")
        .select("id, name")
        .eq("id", subject_id)
        .eq("stage_id", stage_id)
        .limit(1)
        .execute()
    )

    subjects = response.data or []

    if not subjects:
        await query.answer(
            "❌ المادة غير موجودة.",
            show_alert=True,
        )
        return

    subject = subjects[0]

    await query.answer()

    await query.edit_message_text(
        "⚠️ تأكيد تعطيل المادة\n\n"
        f"📘 المادة: {subject['name']}\n\n"
        "هل أنت متأكد من تعطيل هذه المادة؟\n\n"
        "ℹ️ سيتم إخفاؤها عن الطلاب بدون حذف "
        "بياناتها نهائياً.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔒 نعم، عطّل المادة",
                    callback_data=(
                        "admin_confirm_delete_subject:"
                        f"{subject_id}:{stage_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data=(
                        "manage_subject:"
                        f"{subject_id}:{stage_id}"
                    ),
                )
            ],
        ]),
    )


# ============================================================
# Confirm subject disable
# ============================================================

async def confirm_delete_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return

    user_id = query.from_user.id

    if not await has_permission(
        user_id,
        PERMISSION_MANAGE_SUBJECTS,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    subject_id = parts[1]
    stage_id = parts[2]

    response = (
        supabase
        .table("subjects")
        .select(
            "id, name, is_active"
        )
        .eq("id", subject_id)
        .eq("stage_id", stage_id)
        .limit(1)
        .execute()
    )

    subjects = response.data or []

    if not subjects:
        await query.answer(
            "❌ المادة غير موجودة.",
            show_alert=True,
        )
        return

    subject = subjects[0]

    await query.answer(
        "⏳ جارٍ تعطيل المادة..."
    )

    try:
        (
            supabase
            .table("subjects")
            .update({
                "is_active": False,
            })
            .eq("id", subject_id)
            .eq("stage_id", stage_id)
            .execute()
        )

    except Exception as exc:
        print(
            "DISABLE SUBJECT ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.edit_message_text(
            "❌ تعذر تعطيل المادة.\n\n"
            "لم يتم إجراء أي تغيير."
        )
        return

    await query.edit_message_text(
        "✅ تم تعطيل المادة بنجاح.\n\n"
        f"📘 المادة: {subject['name']}\n\n"
        "🔒 تم إخفاؤها عن الطلاب.\n"
        "📦 البيانات المرتبطة بالمادة لم تُحذف.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ العودة إلى المواد",
                    callback_data=(
                        f"admin_stage_subjects:{stage_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "🛠️ لوحة الإدارة",
                    callback_data="admin_back",
                )
            ],
        ]),
    )


# ============================================================
# Generic admin buttons
# ============================================================

async def admin_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return

    user_id = query.from_user.id

    if not await is_admin(user_id):
        await query.answer(
            "⛔ ليس لديك صلاحية للوصول "
            "إلى لوحة الإدارة.",
            show_alert=True,
        )
        return

    if query.data.startswith(
        "admin_delete_subject:"
    ):
        await delete_subject(
            update,
            context,
        )
        return

    if query.data.startswith(
        "admin_confirm_delete_subject:"
    ):
        await confirm_delete_subject(
            update,
            context,
        )
        return

    await query.answer()

    if query.data == "admin_announcements":
        await query.edit_message_text(
            "📢 الإعلانات\n\n"
            "هذا القسم قيد الإنشاء."
        )

    elif query.data == "admin_settings":
        await query.edit_message_text(
            "⚙️ الإعدادات\n\n"
            "هذا القسم قيد الإنشاء."
        )
