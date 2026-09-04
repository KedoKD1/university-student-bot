from telegram import Update
from telegram.ext import ContextTypes

from bot.database.client import supabase


# ضع Telegram ID الخاص بك هنا مؤقتاً للاختبار
ADMIN_USER_ID = 0


async def receive_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None or update.effective_user is None:
        return

    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        return

    document = update.message.document

    if document is None:
        await update.message.reply_text(
            "❌ أرسل الملف كمستند Document."
        )
        return

    await update.message.reply_text(
        "📄 تم استلام الملف.\n\n"
        f"الاسم: {document.file_name}\n"
        f"الحجم: {document.file_size} بايت\n\n"
        "⏳ جاري تسجيل الملف..."
    )

    context.user_data["pending_file"] = {
        "telegram_file_id": document.file_id,
        "name": document.file_name,
        "file_size": document.file_size,
        "mime_type": document.mime_type,
    }

    await update.message.reply_text(
        "✅ تم حفظ بيانات الملف مؤقتاً.\n\n"
        "الخطوة التالية ستكون اختيار المادة والقسم."
    )
