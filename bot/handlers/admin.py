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
    DEFAULT_ROLE_PERMISSIONS,
    get_admin,
    get_role_permissions,
    is_admin,
    has_permission,
)


# ============================================================
# Admin permission snapshot
# ============================================================

async def get_admin_permissions(user_id: int):
    """
    تحميل صلاحيات الأدمن مرة واحدة فقط عند بناء لوحة الإدارة.

    هذا يمنع admin_keyboard من تنفيذ استعلام Supabase
    لكل زر بشكل منفصل.
    """

    admin = await get_admin(user_id)

    if not admin:
        return None, set()

    role = admin.get("role")

    if role == "owner":
        return admin, {
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
        }

    permissions = set(
        DEFAULT_ROLE_PERMISSIONS.get(
            role,
            set(),
        )
    )

    database_permissions = await get_role_permissions(role)

    if database_permissions:
        permissions.update(database_permissions)

    return admin, permissions


# ============================================================
# Admin check
# ============================================================

async def is_admin_user(user_id: int) -> bool:
    """
    فحص الأدمن باستخدام نظام الـ cache الموحد.
    """

    return await is_admin(user_id)


# ============================================================
# Admin keyboard
# ============================================================

async def admin_keyboard(user_id: int):
    """
    بناء لوحة الإدارة باستعلامات قليلة جداً.

    سابقاً كان يتم استدعاء has_permission لكل زر،
    مما يسبب عدة عمليات قراءة من Supabase.

    الآن يتم تحميل بيانات الأدمن والصلاحيات مرة واحدة.
    """

    admin, permissions = await get_admin_permissions(user_id)

    if admin is None:
        return InlineKeyboardMarkup([])

    keyboard = []

    if PERMISSION_MANAGE_SUBJECTS in permissions:
        keyboard.append([
            InlineKeyboardButton(
                "📚 إدارة المواد",
                callback_data="admin_subjects",
            )
        ])

    if PERMISSION_MANAGE_FILES in permissions:
        keyboard.append([
            InlineKeyboardButton(
                "📄 إدارة الملفات",
                callback_data="admin_files",
            )
        ])

    if PERMISSION_MANAGE_SUMMARIES in permissions:
        keyboard.append([
            InlineKeyboardButton(
                "📝 إدارة الملخصات",
                callback_data="admin_summaries",
            )
        ])

    if PERMISSION_MANAGE_DRAWINGS in permissions:
        keyboard.append([
            InlineKeyboardButton(
                "🎨 إدارة الرسومات",
                callback_data="admin_drawings",
            )
        ])

    if PERMISSION_MANAGE_SCHEDULES in permissions:
        keyboard.append([
            InlineKeyboardButton(
                "📅 إدارة الجداول",
                callback_data="admin_schedules",
            )
        ])

    if PERMISSION_MANAGE_GRADES in permissions:
        keyboard.append([
            InlineKeyboardButton(
                "📝 إدارة الدرجات",
                callback_data="admin_grades",
            )
        ])

    has_tools = (
        PERMISSION_VIEW_STATISTICS in permissions
        or PERMISSION_MANAGE_ADMINS in permissions
        or PERMISSION_MANAGE_DESCRIPTIONS in permissions
    )

    if has_tools:
        keyboard.append([
            InlineKeyboardButton(
                "🧰 أدوات الإدارة",
                callback_data="admin_tools",
            )
        ])

    if PERMISSION_MANAGE_ANNOUNCEMENTS in permissions:
        keyboard.append([
            InlineKeyboardButton(
                "📢 الإعلانات",
                callback_data="admin_announcements",
            )
        ])

    if PERMISSION_MANAGE_SETTINGS in permissions:
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

    # يستخدم cache بدلاً من استعلام admins جديد كل مرة.
    admin = await get_admin(user_id)

    if admin is None:
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

    # الـ cache يمنع إعادة قراءة admins من Supabase
    # إذا كان المستخدم فُحص قبل لحظات.
    admin = await get_admin(user_id)

    if admin is None:
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

    # استخدام cache هنا أيضاً يمنع استعلام admins
    # في كل ضغطة على أزرار الإدارة.
    admin = await get_admin(user_id)

    if admin is None:
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
