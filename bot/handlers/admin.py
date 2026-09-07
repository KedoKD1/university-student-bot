from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database.client import supabase


# =========================
# Admin Check
# =========================

async def is_admin(user_id: int) -> bool:
    response = (
        supabase
        .table("admins")
        .select("id, telegram_id, role, is_active")
        .eq("telegram_id", user_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    return bool(response.data)


# =========================
# Admin Keyboard
# =========================

def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📚 إدارة المواد",
                callback_data="admin_subjects"
            )
        ],
        [
            InlineKeyboardButton(
                "📄 إدارة الملفات",
                callback_data="admin_files"
            )
        ],
        [
            InlineKeyboardButton(
                "📝 إدارة الملخصات",
                callback_data="admin_summaries"
            )
        ],
        [
            InlineKeyboardButton(
                "🎨 إدارة الرسومات",
                callback_data="admin_drawings"
            )
        ],
        [
            InlineKeyboardButton(
                "📢 الإعلانات",
                callback_data="admin_announcements"
            )
        ],
        [
            InlineKeyboardButton(
                "⚙️ الإعدادات",
                callback_data="admin_settings"
            )
        ],
    ])


# =========================
# Admin Command
# =========================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None or update.effective_user is None:
        return

    user_id = update.effective_user.id

    if not await is_admin(user_id):
        await update.message.reply_text(
            "⛔ عذراً، ليس لديك صلاحية الوصول إلى لوحة الإدارة."
        )
        return

    await update.message.reply_text(
        "🛠️ لوحة الإدارة\n\n"
        "أهلاً بك في لوحة إدارة بوت الطالب الجامعي.\n"
        "اختر القسم الذي تريد إدارته:",
        reply_markup=admin_keyboard()
    )


# =========================
# Back To Admin
# =========================

async def admin_back(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True
        )
        return

    await query.answer()

    await query.edit_message_text(
        "🛠️ لوحة الإدارة\n\n"
        "أهلاً بك في لوحة إدارة بوت الطالب الجامعي.\n"
        "اختر القسم الذي تريد إدارته:",
        reply_markup=admin_keyboard()
    )


# =========================
# Delete Subject
# =========================

async def delete_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    user_id = query.from_user.id

    if not await is_admin(user_id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True
        )
        return

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True
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
            show_alert=True
        )
        return

    subject = subjects[0]

    await query.answer()

    await query.edit_message_text(
        "⚠️ تأكيد حذف المادة\n\n"
        f"📘 المادة: {subject['name']}\n\n"
        "هل أنت متأكد من حذف هذه المادة؟\n\n"
        "⚠️ سيتم حذف الملفات المرتبطة بالمادة أيضاً.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🗑️ نعم، احذف المادة",
                    callback_data=(
                        f"admin_confirm_delete_subject:"
                        f"{subject_id}:{stage_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data=(
                        f"manage_subject:"
                        f"{subject_id}:{stage_id}"
                    ),
                )
            ],
        ])
    )


# =========================
# Confirm Delete Subject
# =========================

async def confirm_delete_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    user_id = query.from_user.id

    if not await is_admin(user_id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True
        )
        return

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True
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
            "❌ المادة غير موجودة أو تم حذفها مسبقاً.",
            show_alert=True
        )
        return

    subject_name = subjects[0]["name"]

    await query.answer(
        "⏳ جارٍ حذف المادة..."
    )

    try:
        # حذف الملفات المرتبطة بالمادة أولاً
        supabase.table("files").delete().eq(
            "subject_id",
            subject_id,
        ).execute()

        # حذف المادة
        supabase.table("subjects").delete().eq(
            "id",
            subject_id,
        ).eq(
            "stage_id",
            stage_id,
        ).execute()

    except Exception:
        await query.edit_message_text(
            "❌ تعذر حذف المادة.\n\n"
            "قد تكون هناك بيانات أخرى مرتبطة بهذه المادة "
            "تمنع حذفها.\n\n"
            "لم يتم إكمال عملية الحذف."
        )
        return

    await query.edit_message_text(
        "✅ تم حذف المادة بنجاح.\n\n"
        f"📘 المادة: {subject_name}\n\n"
        "تم حذف الملفات المرتبطة بها أيضاً.",
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
        ])
    )


# =========================
# Admin Button
# =========================

async def admin_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    user_id = query.from_user.id

    if not await is_admin(user_id):
        await query.answer(
            "⛔ ليس لديك صلاحية للوصول إلى لوحة الإدارة.",
            show_alert=True
        )
        return

    # =========================
    # Delete Subject
    # =========================

    if query.data.startswith("admin_delete_subject:"):
        await delete_subject(
            update,
            context,
        )
        return

    if query.data.startswith("admin_confirm_delete_subject:"):
        await confirm_delete_subject(
            update,
            context,
        )
        return

    await query.answer()

    # =========================
    # Admin Sections
    # =========================

    if query.data == "admin_files":
        await query.edit_message_text(
            "📄 إدارة الملفات\n\n"
            "هذا القسم قيد الإنشاء."
        )

    elif query.data == "admin_summaries":
        await query.edit_message_text(
            "📝 إدارة الملخصات\n\n"
            "هذا القسم قيد الإنشاء."
        )

    elif query.data == "admin_drawings":
        await query.edit_message_text(
            "🎨 إدارة الرسومات\n\n"
            "هذا القسم قيد الإنشاء."
        )

    elif query.data == "admin_announcements":
        await query.edit_message_text(
            "📢 الإعلانات\n\n"
            "هذا القسم قيد الإنشاء."
        )

    elif query.data == "admin_settings":
        await query.edit_message_text(
            "⚙️ الإعدادات\n\n"
            "هذا القسم قيد الإنشاء."
        )
