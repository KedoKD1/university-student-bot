from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database.client import supabase


async def is_admin(user_id: int) -> bool:
    response = (
        supabase
        .table("admins")
        .select("id, telegram_id, role, is_active")
        .eq("telegram_id", user_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    return bool(response.data)


def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📚 إدارة المواد",
                callback_data="admin_subjects"
            )
        ],
        [
            InlineKeyboardButton(
                "📄 إدارة الملفات",
                callback_data="admin_files"
            )
        ],
        [
            InlineKeyboardButton(
                "📝 إدارة الملخصات",
                callback_data="admin_summaries"
            )
        ],
        [
            InlineKeyboardButton(
                "🎨 إدارة الرسومات",
                callback_data="admin_drawings"
            )
        ],
        [
            InlineKeyboardButton(
                "📢 الإعلانات",
                callback_data="admin_announcements"
            )
        ],
        [
            InlineKeyboardButton(
                "⚙️ الإعدادات",
                callback_data="admin_settings"
            )
        ],
    ])


async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None or update.effective_user is None:
        return

    user_id = update.effective_user.id

    if not await is_admin(user_id):
        await update.message.reply_text(
            "⛔ عذراً، ليس لديك صلاحية الوصول إلى لوحة الإدارة."
        )
        return

    await update.message.reply_text(
        "🛠️ لوحة الإدارة\n\n"
        "أهلاً بك في لوحة إدارة بوت الطالب الجامعي.\n"
        "اختر القسم الذي تريد إدارته:",
        reply_markup=admin_keyboard()
    )


async def admin_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    user_id = query.from_user.id

    if not await is_admin(user_id):
        await query.answer(
            "⛔ ليس لديك صلاحية للوصول إلى لوحة الإدارة.",
            show_alert=True
        )
        return

    await query.answer()

    if query.data == "admin_subjects":
        await query.edit_message_text(
            "📚 إدارة المواد\n\n"
            "هذا القسم قيد الإنشاء."
        )

    elif query.data == "admin_files":
        await query.edit_message_text(
            "📄 إدارة الملفات\n\n"
            "هذا القسم قيد الإنشاء."
        )

    elif query.data == "admin_summaries":
        await query.edit_message_text(
            "📝 إدارة الملخصات\n\n"
            "هذا القسم قيد الإنشاء."
        )

    elif query.data == "admin_drawings":
        await query.edit_message_text(
            "🎨 إدارة الرسومات\n\n"
            "هذا القسم قيد الإنشاء."
        )

    elif query.data == "admin_announcements":
        await query.edit_message_text(
            "📢 الإعلانات\n\n"
            "هذا القسم قيد الإنشاء."
        )

    elif query.data == "admin_settings":
        await query.edit_message_text(
            "⚙️ الإعدادات\n\n"
            "هذا القسم قيد الإنشاء."
        )
