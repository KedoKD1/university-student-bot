from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards.main_menu import (
    main_menu_keyboard,
    back_main_keyboard,
)
from bot.handlers.stages import show_stages
from bot.handlers.search import start_search
from bot.handlers.grades import grades_callback
from bot.handlers.student_settings import (
    show_student_settings,
    student_settings_callback,
)


# ============================================================
# Main Menu Text
# ============================================================

def main_menu_text():
    return (
        "🏠 القائمة الرئيسية\n\n"
        "أهلاً بك في LabBase.\n"
        "اختر القسم الذي تريد الوصول إليه:"
    )


# ============================================================
# Clear User Navigation
# ============================================================

def clear_user_navigation(context):
    for key in (
        "search_mode",
        "search_owner_id",
    ):
        context.user_data.pop(key, None)


# ============================================================
# Show Main Menu
# ============================================================

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


# ============================================================
# Main Menu Button
# ============================================================

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

    if len(parts) < 3 or parts[0] != "main":
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    section = parts[1]

    owner_id = parts[-1]

    try:
        owner_id = int(owner_id)

    except (TypeError, ValueError):
        await query.answer(
            "❌ المستخدم غير صالح.",
            show_alert=True,
        )
        return

    if query.from_user.id != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return

    # --------------------------------------------------------
    # Grades
    #
    # Grades callbacks contain extra parameters.
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Student Settings
    #
    # All student settings callbacks use:
    # main:settings:...
    # --------------------------------------------------------

    if section == "settings":
        await student_settings_callback(
            update,
            context,
        )
        return

    # --------------------------------------------------------
    # Normal main menu callbacks
    # --------------------------------------------------------

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    await query.answer()

    # --------------------------------------------------------
    # Stages
    # --------------------------------------------------------

    if section == "stages":
        await show_stages(
            update,
            context,
            edit_message=True,
        )
        return

    # --------------------------------------------------------
    # Schedule
    # --------------------------------------------------------

    if section == "schedule":
        from bot.handlers.schedules import show_schedules

        await show_schedules(
            update,
            context,
        )
        return

    # --------------------------------------------------------
    # Exam Dates
    # --------------------------------------------------------

    if section == "exams":
        from bot.handlers.exam_dates import show_exam_dates

        await show_exam_dates(
            update,
            context,
        )
        return

    # --------------------------------------------------------
    # Search
    # --------------------------------------------------------

    if section == "search":
        await start_search(
            update,
            context,
        )
        return

    # --------------------------------------------------------
    # Unknown section
    # --------------------------------------------------------

    await query.edit_message_text(
        main_menu_text(),
        reply_markup=main_menu_keyboard(
            owner_id,
        ),
    )


# ============================================================
# Back To Main Menu
# ============================================================

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

    if len(parts) != 2 or parts[0] != "back_main":
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    owner_id = parts[1]

    try:
        owner_id = int(owner_id)

    except (TypeError, ValueError):
        await query.answer(
            "❌ المستخدم غير صالح.",
            show_alert=True,
        )
        return

    if query.from_user.id != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return

    clear_user_navigation(context)

    await query.answer()

    await query.edit_message_text(
        main_menu_text(),
        reply_markup=main_menu_keyboard(
            owner_id,
        ),
    )
