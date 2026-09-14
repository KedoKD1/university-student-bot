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


def check_owner(query, owner_id):
    if query.from_user is None:
        return False

    return str(query.from_user.id) == str(owner_id)


async def show_main_menu(update, context):
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


async def main_menu_button(update, context):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
        or not query.data
    ):
        return

    parts = query.data.split(":")

    # ========================================================
    # Grades callbacks have 4 or 5 parts.
    # They must be routed BEFORE the normal 3-part check.
    # ========================================================

    if (
        len(parts) >= 2
        and parts[0] == "main"
        and parts[1].startswith("grades")
        or (
            len(parts) >= 2
            and parts[0] == "main"
            and parts[1] == "grade_file"
        )
    ):
        await grades_callback(
            update,
            context,
        )
        return

    # ========================================================
    # Normal main menu callback:
    # main:section:user_id
    # ========================================================

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    if parts[0] != "main":
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    section = parts[1]
    owner_id = parts[2]

    if not check_owner(query, owner_id):
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return

    try:
        user_id = int(owner_id)
    except (TypeError, ValueError):
        await query.answer(
            "❌ المستخدم غير صالح.",
            show_alert=True,
        )
        return

    await query.answer()

    # ========================================================
    # Stages
    # ========================================================

    if section == "stages":
        await show_stages(
            update,
            context,
            edit_message=True,
        )
        return

    # ========================================================
    # Schedule
    # ========================================================

    if section == "schedule":
        from bot.handlers.schedules import show_schedules

        await show_schedules(
            update,
            context,
        )
        return

    # ========================================================
    # Exams
    # ========================================================

    if section == "exams":
        from bot.handlers.exam_dates import show_exam_dates

        await show_exam_dates(
            update,
            context,
        )
        return

    # ========================================================
    # Search
    # ========================================================

    if section == "search":
        await start_search(
            update,
            context,
        )
        return

    # ========================================================
    # Quizzes
    # ========================================================

    if section == "quizzes":
        from bot.handlers.quizzes import show_quizzes

        await show_quizzes(
            update,
            context,
        )
        return

    # ========================================================
    # AI
    # ========================================================

    if section == "ai":
        await query.edit_message_text(
            "🤖 الذكاء الاصطناعي\n\n"
            "هذا القسم قيد الإنشاء وسيتم توفيره قريباً.",
            reply_markup=back_main_keyboard(
                user_id
            ),
        )
        return

    # ========================================================
    # Settings
    # ========================================================

    if section == "settings":
        await query.edit_message_text(
            "⚙️ الإعدادات\n\n"
            "هذا القسم قيد الإنشاء وسيتم توفيره قريباً.",
            reply_markup=back_main_keyboard(
                user_id
            ),
        )
        return

    # ========================================================
    # Unknown
    # ========================================================

    await query.edit_message_text(
        main_menu_text(),
        reply_markup=main_menu_keyboard(
            user_id
        ),
    )


async def back_main(update, context):
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

    if parts[0] != "back_main":
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    owner_id = parts[1]

    if not check_owner(query, owner_id):
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return

    try:
        user_id = int(owner_id)
    except (TypeError, ValueError):
        await query.answer(
            "❌ المستخدم غير صالح.",
            show_alert=True,
        )
        return

    clear_user_navigation(context)

    await query.answer()

    await query.edit_message_text(
        main_menu_text(),
        reply_markup=main_menu_keyboard(
            user_id
        ),
    )
