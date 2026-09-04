from bot.keyboards.content import content_keyboard
from telegram import Update
from telegram.ext import ContextTypes

from bot.database.client import supabase
from bot.keyboards.subjects import subjects_keyboard
from bot.keyboards.stages import stages_keyboard


async def show_subjects(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    stage_id: str,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    user_id = query.from_user.id

    response = (
        supabase
        .table("subjects")
        .select("*")
        .eq("stage_id", stage_id)
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )

    subjects = response.data

    await query.answer()

    if not subjects:
        await query.edit_message_text(
            "📚 مواد المرحلة\n\n"
            "لا توجد مواد مضافة لهذه المرحلة حالياً."
        )
        return

    await query.edit_message_text(
        "📚 مواد المرحلة\n\n"
        "اختر المادة:",
        reply_markup=subjects_keyboard(
            subjects,
            user_id
        )
    )


async def subject_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True
        )
        return

    subject_id = parts[1]
    owner_id = parts[2]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.\n"
            "استخدم /start حتى تحصل على قائمتك الخاصة.",
            show_alert=True
        )
        return

    await query.answer()

    response = (
        supabase
        .table("subjects")
        .select("*")
        .eq("id", subject_id)
        .eq("is_active", True)
        .single()
        .execute()
    )

    subject = response.data

    if not subject:
        await query.edit_message_text(
            "❌ تعذر العثور على هذه المادة."
        )
        return

    description = subject.get("description") or "لا يوجد وصف للمادة حالياً."

    await query.edit_message_text(
        f"📘 {subject['name']}\n\n"
        f"{description}\n\n"
        "اختر ما تريد:"
    )


async def back_to_stages(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True
        )
        return

    owner_id = parts[1]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True
        )
        return

    response = (
        supabase
        .table("stages")
        .select("*")
        .order("stage_number")
        .execute()
    )

    await query.answer()

    await query.edit_message_text(
        "🎓 اختر المرحلة الدراسية:",
        reply_markup=stages_keyboard(
            response.data,
            query.from_user.id
        )
    )
