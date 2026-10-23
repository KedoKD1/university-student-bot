from bot.utils.logging_security import log_error

from telegram import Update
from telegram.ext import ContextTypes

from bot.database.client import supabase
from bot.keyboards.stages import stages_keyboard
from bot.keyboards.subjects import back_stages_keyboard
from bot.handlers.subjects import show_subjects


def stages_back_keyboard(user_id):
    return back_stages_keyboard(user_id)


async def show_stages(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    edit_message=False,
):
    user = update.effective_user

    if user is None:
        return

    user_id = user.id

    try:
        response = (
            supabase
            .table("stages")
            .select("*")
            .order("stage_number")
            .execute()
        )
        stages = response.data or []
        text = "📚 المراحل الدراسية\n\n" + (
            "اختر مرحلتك لعرض المواد والمحتوى الدراسي."
            if stages else "لا توجد مراحل دراسية متاحة حاليًا. يمكنك المحاولة لاحقًا."
        )
    except Exception as exc:
        log_error('STUDENT STAGES ERROR:', exc)
        stages = []
        text = "❌ تعذر تحميل المراحل حاليًا. يمكنك العودة والمحاولة لاحقًا."

    keyboard = stages_keyboard(
        stages,
        user_id,
    )

    if edit_message and update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=keyboard,
        )
        return

    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=keyboard,
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
            "⛔ هذا الاختيار ليس لك.\n"
            "استخدم /start لفتح قائمتك الخاصة.",
            show_alert=True,
        )
        return

    try:
        response = (
            supabase
            .table("stages")
            .select("*")
            .eq("id", stage_id)
            .limit(1)
            .execute()
        )
        stages = response.data or []
    except Exception as exc:
        log_error('STUDENT STAGE ERROR:', exc)
        await query.answer()
        await query.edit_message_text(
            "❌ تعذر تحميل المرحلة حاليًا. يمكنك العودة والمحاولة لاحقًا.",
            reply_markup=stages_back_keyboard(query.from_user.id),
        )
        return

    if not stages:
        await query.answer()
        await query.edit_message_text(
            "❌ هذه المرحلة غير متاحة حاليًا. اختر مرحلة أخرى.",
            reply_markup=stages_back_keyboard(
                query.from_user.id
            ),
        )
        return

    stage = stages[0]

    if not stage["is_active"]:
        await query.answer()
        await query.edit_message_text(
            "🔒 هذه المرحلة غير متاحة حاليًا. اختر مرحلة أخرى.",
            reply_markup=stages_back_keyboard(query.from_user.id),
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
            "⛔ هذا الاختيار ليس لك.\n"
            "استخدم /start لفتح قائمتك الخاصة.",
            show_alert=True,
        )
        return

    await query.answer(
        "🔒 هذه المرحلة غير متاحة حاليًا.",
        show_alert=True,
    )
