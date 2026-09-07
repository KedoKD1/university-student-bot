from telegram import Update
from telegram.ext import ContextTypes

from bot.database.client import supabase
from bot.keyboards.stages import stages_keyboard
from bot.handlers.subjects import show_subjects


async def show_stages(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    edit_message=False,
):
    user = update.effective_user

    if user is None:
        return

    user_id = user.id

    response = (
        supabase
        .table("stages")
        .select("*")
        .order("stage_number")
        .execute()
    )

    stages = response.data or []

    text = (
        "🎓 المراحل الدراسية\n\n"
        "اختر المرحلة الدراسية:"
    )

    if edit_message and update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=stages_keyboard(
                stages,
                user_id,
            ),
        )
        return

    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=stages_keyboard(
                stages,
                user_id,
            ),
        )


async def stage_button(
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
            show_alert=True,
        )
        return

    stage_id = parts[1]
    owner_id = parts[2]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.\n"
            "استخدم /start حتى تحصل على قائمتك الخاصة.",
            show_alert=True,
        )
        return

    await query.answer()

    response = (
        supabase
        .table("stages")
        .select("*")
        .eq("id", stage_id)
        .limit(1)
        .execute()
    )

    stages = response.data or []

    if not stages:
        await query.edit_message_text(
            "❌ تعذر العثور على هذه المرحلة."
        )
        return

    stage = stages[0]

    if not stage["is_active"]:
        await query.answer(
            "🔒 هذه المرحلة غير متاحة حالياً.",
            show_alert=True,
        )
        return

    await show_subjects(
        update,
        context,
        stage_id,
    )


async def locked_stage_button(
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
            show_alert=True,
        )
        return

    owner_id = parts[2]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.\n"
            "استخدم /start حتى تحصل على قائمتك الخاصة.",
            show_alert=True,
        )
        return

    await query.answer(
        "🔒 هذه المرحلة غير متاحة حالياً.",
        show_alert=True,
    )
