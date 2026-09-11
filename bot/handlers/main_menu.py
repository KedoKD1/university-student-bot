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


async def show_main_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    context.user_data.pop(
        "search_mode",
        None,
    )

    context.user_data.pop(
        "search_owner_id",
        None,
    )

    user_id = update.effective_user.id

    await update.message.reply_text(
        main_menu_text(),
        reply_markup=main_menu_keyboard(
            user_id
        ),
    )


async def main_menu_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return

    parts = query.data.split(":")

    if len(parts) < 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    owner_id = parts[-1]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return

    section = parts[1]

    if (
        section == "grades"
        or section.startswith("grades_")
        or section == "grade_file"
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
        from bot.handlers.schedules import (
            show_schedules,
        )

        await show_schedules(
            update,
            context,
        )
        return

    if section == "exams":
        from bot.handlers.exam_dates import (
            show_exam_dates,
        )

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

    if section == "ai":
        await query.edit_message_text(
            "🤖 الذكاء الاصطناعي\n\n"
            "هذا القسم قيد الإنشاء وسيتم توفيره قريباً.",
            reply_markup=back_main_keyboard(
                query.from_user.id
            ),
        )
        return

    if section == "settings":
        await query.edit_message_text(
            "⚙️ الإعدادات\n\n"
            "هذا القسم قيد الإنشاء وسيتم توفيره قريباً.",
            reply_markup=back_main_keyboard(
                query.from_user.id
            ),
        )
        return

    await query.edit_message_text(
        main_menu_text(),
        reply_markup=main_menu_keyboard(
            query.from_user.id
        ),
    )


async def back_main(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
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

    context.user_data.pop(
        "search_mode",
        None,
    )

    context.user_data.pop(
        "search_owner_id",
        None,
    )

    await query.answer()

    await query.edit_message_text(
        main_menu_text(),
        reply_markup=main_menu_keyboard(
            query.from_user.id
        ),
    )
