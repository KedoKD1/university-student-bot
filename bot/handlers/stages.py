from telegram import Update
from telegram.ext import ContextTypes

from bot.database.client import supabase
from bot.keyboards.stages import stages_keyboard


async def show_stages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.effective_user is None:
        return

    user_id = update.effective_user.id

    response = (
        supabase
        .table("stages")
        .select("*")
        .order("stage_number")
        .execute()
    )

    stages = response.data

    await update.message.reply_text(
        "🎓 أهلاً بك في بوت الطالب الجامعي\n\n"
        "اختر المرحلة الدراسية:",
        reply_markup=stages_keyboard(stages, user_id)
    )


async def stage_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer("❌ اختيار غير صالح.", show_alert=True)
        return

    stage_id = parts[1]
    owner_id = parts[2]
    current_user_id = str(query.from_user.id)

    if current_user_id != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.\n"
            "استخدم /start حتى تحصل على قائمتك الخاصة.",
            show_alert=True
        )
        return

    await query.answer()

    response = (
        supabase
        .table("stages")
        .select("*")
        .eq("id", stage_id)
        .single()
        .execute()
    )

    stage = response.data

    if not stage:
        await query.edit_message_text(
            "❌ تعذر العثور على هذه المرحلة."
        )
        return

    if not stage["is_active"]:
        await query.answer(
            "🔒 هذه المرحلة غير متاحة حالياً.",
            show_alert=True
        )
        return

    await query.edit_message_text(
        f"📚 المرحلة {stage['stage_number']}\n\n"
        "اختر من القائمة التالية:"
    )


async def locked_stage_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer("❌ اختيار غير صالح.", show_alert=True)
        return

    owner_id = parts[2]
    current_user_id = str(query.from_user.id)

    if current_user_id != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.\n"
            "استخدم /start حتى تحصل على قائمتك الخاصة.",
            show_alert=True
        )
        return

    await query.answer(
        "🔒 هذه المرحلة غير متاحة حالياً.",
        show_alert=True
    )
