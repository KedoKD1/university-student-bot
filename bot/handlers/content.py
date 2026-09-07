from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes

from bot.database.client import supabase
from bot.keyboards.content import (
    content_keyboard,
    files_section_keyboard,
)


MAX_CAPTION_LENGTH = 1024


def build_file_caption(name, description):
    name = name or "ملف"

    caption = f"📄 {name}"

    if description:
        description = str(description).strip()

        if description:
            caption += f"\n\n📝 {description}"

    if len(caption) > MAX_CAPTION_LENGTH:
        caption = (
            caption[:MAX_CAPTION_LENGTH - 3].rstrip()
            + "..."
        )

    return caption


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

    subject_id = parts[2]
    owner_id = parts[3]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.\n"
            "استخدم /start حتى تحصل على قائمتك الخاصة.",
            show_alert=True
        )
        return

    await query.answer()

    await query.edit_message_text(
        "📄 الملفات\n\n"
        "اختر القسم:",
        reply_markup=files_section_keyboard(
            subject_id,
            query.from_user.id,
        )
    )


async def show_file_section(
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

    if section_type not in (
        "theoretical",
        "practical",
    ):
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
        .is_("deleted_at", "null")
        .order("sort_order")
        .execute()
    )

    files = response.data or []

    section_name = (
        "📖 النظري"
        if section_type == "theoretical"
        else "🧪 العملي"
    )

    if not files:
        await query.edit_message_text(
            f"📄 الملفات — {section_name}\n\n"
            "لا توجد ملفات مضافة لهذا القسم حالياً.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        text="⬅️ رجوع للملفات",
                        callback_data=(
                            f"content:files:"
                            f"{subject_id}:{owner_id}"
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
            text="⬅️ رجوع للملفات",
            callback_data=(
                f"content:files:"
                f"{subject_id}:{owner_id}"
            )
        )
    ])

    await query.edit_message_text(
        f"📄 الملفات — {section_name}\n\n"
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
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )

    files = response.data or []

    if not files:
        await query.message.reply_text(
            "❌ الملف غير موجود."
        )
        return

    file = files[0]

    telegram_file_id = file.get(
        "telegram_file_id"
    )

    if not telegram_file_id:
        await query.message.reply_text(
            "⚠️ هذا الملف لم يتم ربطه بملف Telegram بعد."
        )
        return

    file_type = file.get("file_type")
    name = file.get("name") or "ملف"
    description = file.get("description")

    caption = build_file_caption(
        name,
        description,
    )

    if file_type == "photo":
        await query.message.reply_photo(
            photo=telegram_file_id,
            caption=caption,
        )

    elif file_type == "video":
        await query.message.reply_video(
            video=telegram_file_id,
            caption=caption,
        )

    elif file_type == "audio":
        await query.message.reply_audio(
            audio=telegram_file_id,
            caption=caption,
        )

    else:
        await query.message.reply_document(
            document=telegram_file_id,
            caption=caption,
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
        .limit(1)
        .execute()
    )

    subjects = response.data or []

    if not subjects:
        await query.answer(
            "❌ المادة غير موجودة.",
            show_alert=True
        )
        return

    subject = subjects[0]

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


async def content_placeholder(
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

    section = parts[1]
    subject_id = parts[2]
    owner_id = parts[3]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True
        )
        return

    if section == "summaries":
        title = "📝 الملخصات"
    elif section == "drawings":
        title = "🎨 الرسومات"
    else:
        await query.answer(
            "❌ القسم غير صالح.",
            show_alert=True
        )
        return

    await query.answer()

    await query.edit_message_text(
        f"{title}\n\n"
        "هذا القسم قيد الإنشاء وسيتم توفير محتواه قريباً.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text="⬅️ رجوع للمادة",
                    callback_data=(
                        f"back_content:"
                        f"{subject_id}:{owner_id}"
                    )
                )
            ]
        ])
    )
