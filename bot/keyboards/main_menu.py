from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)


def main_menu_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="📚 المراحل الدراسية",
                callback_data=f"main:stages:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="📅 الجداول",
                callback_data=f"main:schedule:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 الدرجات",
                callback_data=f"main:grades:{user_id}",
            ),
            InlineKeyboardButton(
                text="🔎 البحث",
                callback_data=f"main:search:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🤖 الذكاء الاصطناعي",
                callback_data=f"main:ai:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="⚙️ الإعدادات",
                callback_data=f"main:settings:{user_id}",
            )
        ],
    ])


def back_main_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="🏠 القائمة الرئيسية",
                callback_data=f"back_main:{user_id}",
            )
        ]
    ])


async def main_menu_button(update, context):
    query = update.callback_query
    await query.answer()

    data = query.data.split(":")
    section = data[1]

    if section == "grades":
        from bot.handlers.grades import show_grades

        await show_grades(
            update,
            context,
        )
        return

    if section == "ai":
        # المنطق الخاص بالذكاء الاصطناعي هنا
        pass
