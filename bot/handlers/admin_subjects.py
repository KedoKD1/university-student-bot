from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database.client import supabase
from bot.handlers.admin import is_admin


def stages_admin_keyboard(stages):
    keyboard = []

    for stage in stages:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📚 المرحلة {stage['stage_number']}",
                callback_data=f"manage_stage:{stage['id']}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للوحة الإدارة",
            callback_data="admin_back"
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def subjects_admin_keyboard(subjects, stage_id):
    keyboard = []

    for subject in subjects:
        status = "🟢" if subject["is_active"] else "🔴"

        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {subject['name']}",
                callback_data=(
                    f"manage_subject:{subject['id']}:{stage_id}"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="➕ إضافة مادة",
            callback_data=f"add_subject:{stage_id}"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للمراحل",
            callback_data="admin_subjects"
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def subject_manage_keyboard(
    subject_id,
    stage_id,
    is_active
):
    if is_active:
        toggle_text = "🔴 تعطيل المادة"
        toggle_callback = (
            f"disable_subject:{subject_id}:{stage_id}"
        )
    else:
        toggle_text = "🟢 تفعيل المادة"
        toggle_callback = (
            f"enable_subject:{subject_id}:{stage_id}"
        )

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="✏️ تعديل المادة",
                callback_data=(
                    f"edit_subject:{subject_id}:{stage_id}"
                )
            )
        ],
        [
            InlineKeyboardButton(
                text=toggle_text,
                callback_data=toggle_callback
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ رجوع للمواد",
                callback_data=(
                    f"manage_stage:{stage_id}"
                )
            )
        ],
    ])


async def admin_subjects(
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

    response = (
        supabase
        .table("stages")
        .select("id, stage_number, is_active")
        .order("stage_number")
        .execute()
    )

    stages = response.data

    await query.answer()

    if not stages:
        await query.edit_message_text(
            "❌ لا توجد مراحل في قاعدة البيانات."
        )
        return

    await query.edit_message_text(
        "📚 إدارة المواد\n\n"
        "اختر المرحلة:",
        reply_markup=stages_admin_keyboard(stages)
    )


async def manage_stage(
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

    parts = query.data.split(":")

    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True
        )
        return

    stage_id = parts[1]

    response = (
        supabase
        .table("subjects")
        .select(
            "id, name, description, sort_order, is_active"
        )
        .eq("stage_id", stage_id)
        .order("sort_order")
        .execute()
    )

    subjects = response.data

    await query.answer()

    await query.edit_message_text(
        "📚 مواد المرحلة\n\n"
        "اختر المادة لإدارتها أو أضف مادة جديدة:",
        reply_markup=subjects_admin_keyboard(
            subjects,
            stage_id
        )
    )


async def manage_subject(
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
        .select("*")
        .eq("id", subject_id)
        .single()
        .execute()
    )

    subject = response.data

    await query.answer()

    if not subject:
        await query.edit_message_text(
            "❌ المادة غير موجودة."
        )
        return

    status = (
        "🟢 مفعّلة"
        if subject["is_active"]
        else "🔴 معطّلة"
    )

    description = (
        subject.get("description")
        or "لا يوجد وصف."
    )

    await query.edit_message_text(
        f"📘 {subject['name']}\n\n"
        f"الوصف:\n{description}\n\n"
        f"الترتيب: {subject['sort_order']}\n"
        f"الحالة: {status}",
        reply_markup=subject_manage_keyboard(
            subject_id,
            stage_id,
            subject["is_active"]
        )
    )


async def disable_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await set_subject_status(
        update,
        active=False
    )


async def enable_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await set_subject_status(
        update,
        active=True
    )


async def set_subject_status(
    update: Update,
    active: bool,
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

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True
        )
        return

    subject_id = parts[1]
    stage_id = parts[2]

    (
        supabase
        .table("subjects")
        .update({"is_active": active})
        .eq("id", subject_id)
        .execute()
    )

    await query.answer(
        "✅ تم تفعيل المادة."
        if active
        else "✅ تم تعطيل المادة.",
        show_alert=True
    )

    response = (
        supabase
        .table("subjects")
        .select("*")
        .eq("id", subject_id)
        .single()
        .execute()
    )

    subject = response.data

    if not subject:
        await query.edit_message_text(
            "❌ المادة غير موجودة."
        )
        return

    status = (
        "🟢 مفعّلة"
        if subject["is_active"]
        else "🔴 معطّلة"
    )

    description = (
        subject.get("description")
        or "لا يوجد وصف."
    )

    await query.edit_message_text(
        f"📘 {subject['name']}\n\n"
        f"الوصف:\n{description}\n\n"
        f"الترتيب: {subject['sort_order']}\n"
        f"الحالة: {status}",
        reply_markup=subject_manage_keyboard(
            subject_id,
            stage_id,
            subject["is_active"]
        )
    )
