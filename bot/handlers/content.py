from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database.client import supabase
from bot.keyboards.content import content_keyboard
async def show_files(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    parts = query.data.split(":")
    if len(parts) != 4:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True
        )
        return
    section_type = parts[1]
    subject_id = parts[2]
    owner_id = parts[3]
    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.\n"
            "استخدم /start حتى تحصل على قائمتك الخاصة.",
            show_alert=True
        )
        return
    if section_type not in ("theory", "practical"):
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True
        )
        return
    await query.answer()
    response = (
        supabase
        .table("files")
        .select("*")
        .eq("subject_id", subject_id)
        .eq("section_type", section_type)
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )
    files = response.data
    section_name = (
        "📖 النظري"
        if section_type == "theory"
        else "🧪 العملي"
    )
    if not files:
        await query.edit_message_text(
            f"{section_name}\n\n"
            "لا توجد ملفات مضافة لهذا القسم حالياً.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        text="⬅️ رجوع للمادة",
                        callback_data=(
                            f"back_content:{subject_id}:{owner_id}"
                        )
                    )
                ]
            ])
        )
        return
    keyboard = []
    for file in files:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📄 {file['name']}",
                callback_data=(
                    f"file:{file['id']}:{owner_id}"
                )
            )
        ])
    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للمادة",
            callback_data=(
                f"back_content:{subject_id}:{owner_id}"
            )
        )
    ])
    await query.edit_message_text(
        f"{section_name}\n\n"
        "اختر الملف:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
async def file_button(
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
            show_alert=True
        )
        return
    file_id = parts[1]
    owner_id = parts[2]
    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True
        )
        return
    await query.answer()
    response = (
        supabase
        .table("files")
        .select("*")
        .eq("id", file_id)
        .eq("is_active", True)
        .single()
        .execute()
    )
    file = response.data
    if not file:
        await query.message.reply_text(
            "❌ الملف غير موجود."
        )
        return
    telegram_file_id = file.get("telegram_file_id")
    if not telegram_file_id:
        await query.message.reply_text(
            "⚠️ هذا الملف لم يتم ربطه بملف Telegram بعد."
        )
        return
    await query.message.reply_document(
        document=telegram_file_id,
        caption=f"📄 {file['name']}"
    )
async def back_to_content(
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
            show_alert=True
        )
        return
    subject_id = parts[1]
    owner_id = parts[2]
    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True
        )
        return
    response = (
        supabase
        .table("subjects")
        .select("*")
        .eq("id", subject_id)
        .eq("is_active", True)
        .single()
        .execute()
    )
    subject = response.data
    if not subject:
        await query.answer(
            "❌ المادة غير موجودة.",
            show_alert=True
        )
        return
    stage_id = subject.get("stage_id")
    if stage_id is None:
        await query.answer(
            "❌ تعذر تحديد المرحلة الخاصة بالمادة.",
            show_alert=True
        )
        return
    await query.answer()
    description = (
        subject.get("description")
        or "لا يوجد وصف للمادة حالياً."
    )
    await query.edit_message_text(
        f"📘 {subject['name']}\n\n"
        f"{description}\n\n"
        "اختر القسم:",
        reply_markup=content_keyboard(
            subject_id,
            query.from_user.id,
            stage_id
        )
    )
