from telegram import Update
from telegram.ext import ContextTypes
from bot.keyboards.main_menu import (
    main_menu_keyboard,
    back_main_keyboard,
)
from bot.handlers.stages import show_stages
from bot.handlers.search import start_search
from bot.handlers.grades import grades_callback
def main_menu_text():
    return (
        "🏠 القائمة الرئيسية\n\n"
        "أهلاً بك في LabBase.\n"
        "اختر القسم الذي تريد الوصول إليه:"
    )
def clear_user_navigation(context):
    for key in (
        "search_mode",
        "search_owner_id",
        "quiz_state",
    ):
        context.user_data.pop(key, None)
async def show_main_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if (
        update.message is None
        or update.effective_user is None
    ):
        return
    clear_user_navigation(context)
    user_id = update.effective_user.id
    await update.message.reply_text(
        main_menu_text(),
        reply_markup=main_menu_keyboard(user_id),
    )
async def main_menu_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if (
        query is None
        or query.from_user is None
        or not query.data
    ):
        return
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return
    section = parts[1]
    owner_id = parts[2]
    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return
    try:
        user_id = int(owner_id)
    except ValueError:
        await query.answer(
            "❌ المستخدم غير صالح.",
            show_alert=True,
        )
        return
    if section in (
        "grades",
        "grades_stage",
        "grades_locked",
        "grade_file",
        "grades_all",
        "grades_back",
    ):
        await grades_callback(
            update,
            context,
        )
        return
    await query.answer()
    if section == "stages":
        await show_stages(
            update,
            context,
            edit_message=True,
        )
        return
    if section == "schedule":
        from bot.handlers.schedules import show_schedules
        await show_schedules(
            update,
            context,
        )
        return
    if section == "exams":
        from bot.handlers.exam_dates import show_exam_dates
        await show_exam_dates(
            update,
            context,
        )
        return
    if section == "search":
        await start_search(
            update,
            context,
        )
        return
    if section == "quizzes":
        from bot.handlers.quizzes import show_quizzes
        await show_quizzes(
            update,
            context,
        )
        return
    if section == "leaderboard":
        from bot.handlers.leaderboard import show_leaderboard
        await show_leaderboard(
            update,
            context,
        )
        return
    if section == "ai":
        await query.edit_message_text(
            "🤖 الذكاء الاصطناعي\n\n"
            "هذا القسم قيد الإنشاء وسيتم توفيره قريباً.",
            reply_markup=back_main_keyboard(user_id),
        )
        return
    if section == "settings":
        await query.edit_message_text(
            "⚙️ الإعدادات\n\n"
            "هذا القسم قيد الإنشاء وسيتم توفيره قريباً.",
            reply_markup=back_main_keyboard(user_id),
        )
        return
    await query.edit_message_text(
        main_menu_text(),
        reply_markup=main_menu_keyboard(user_id),
    )
async def back_main(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if (
        query is None
        or query.from_user is None
        or not query.data
    ):
        return
    parts = query.data.split(":")
    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return
    owner_id = parts[1]
    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return
    try:
        user_id = int(owner_id)
    except ValueError:
        await query.answer(
            "❌ المستخدم غير صالح.",
            show_alert=True,
        )
        return
    clear_user_navigation(context)
    await query.answer()
    await query.edit_message_text(
        main_menu_text(),
        reply_markup=main_menu_keyboard(user_id),
    )
