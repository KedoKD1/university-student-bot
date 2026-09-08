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
    summaries_section_keyboard,
)


MAX_CAPTION_LENGTH = 1024


def build_caption(icon, name, description=None):
    name = name or "ملف"

    caption = f"{icon} {name}"

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


def owner_error():
    return (
        "⛔ هذا الاختيار مو إلك.\n"
        "استخدم /start حتى تحصل على قائمتك الخاصة."
    )


def back_content_keyboard(subject_id, owner_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⬅️ رجوع للمادة",
                callback_data=(
                    f"back_content:"
                    f"{subject_id}:{owner_id}"
                ),
            )
        ]
    ])


async def send_content_item(message, item, icon):
    telegram_file_id = item.get("telegram_file_id")

    if not telegram_file_id:
        return False

    caption = build_caption(
        icon,
        item.get("name"),
        item.get("description"),
    )

    file_type = item.get("file_type")

    if file_type == "photo":
        await message.reply_photo(
            photo=telegram_file_id,
            caption=caption,
        )

    elif file_type == "video":
        await message.reply_video(
            video=telegram_file_id,
            caption=caption,
        )

    elif file_type == "audio":
        await message.reply_audio(
            audio=telegram_file_id,
            caption=caption,
        )

    else:
        await message.reply_document(
            document=telegram_file_id,
            caption=caption,
        )

    return True


async def show_files(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    # content:files:subject_id:user_id
    # content:files:all:subject_id:user_id

    if len(parts) == 4:
        subject_id = parts[2]
        owner_id = parts[3]
        show_all = False

    elif len(parts) == 5 and parts[2] == "all":
        subject_id = parts[3]
        owner_id = parts[4]
        show_all = True

    else:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    if str(query.from_user.id) != owner_id:
        await query.answer(
            owner_error(),
            show_alert=True,
        )
        return

    await query.answer()

    # =========================
    # جميع الملفات
    # =========================

    if show_all:
        response = (
            supabase
            .table("files")
            .select("*")
            .eq("subject_id", subject_id)
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .order("sort_order")
            .execute()
        )

        files = response.data or []

        if not files:
            await query.edit_message_text(
                "📚 جميع الملفات\n\n"
                "⚠️ لا توجد ملفات مضافة لهذه المادة حاليًا.",
                reply_markup=back_content_keyboard(
                    subject_id,
                    owner_id,
                ),
            )
            return

        await query.edit_message_text(
            "📚 جميع الملفات\n\n"
            "⏳ جاري إرسال الملفات النظرية والعملية..."
        )

        sent_count = 0
        failed_count = 0

        for file in files:
            try:
                sent = await send_content_item(
                    query.message,
                    file,
                    "📄",
                )

                if sent:
                    sent_count += 1
                else:
                    failed_count += 1

            except Exception as exc:
                print(
                    f"ALL FILES SEND ERROR: {exc}"
                )
                failed_count += 1

        result_text = (
            "📚 تم إرسال جميع الملفات.\n\n"
            f"✅ تم إرسال: {sent_count}"
        )

        if failed_count:
            result_text += (
                f"\n⚠️ تعذر إرسال: {failed_count}"
            )

        await query.message.reply_text(
            result_text,
            reply_markup=back_content_keyboard(
                subject_id,
                owner_id,
            ),
        )

        return

    # =========================
    # قائمة الملفات
    # =========================

    await query.edit_message_text(
        "📄 الملفات\n\n"
        "اختر القسم:",
        reply_markup=files_section_keyboard(
            subject_id,
            query.from_user.id,
        ),
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
            show_alert=True,
        )
        return

    section_type = parts[1]
    subject_id = parts[2]
    owner_id = parts[3]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            owner_error(),
            show_alert=True,
        )
        return

    if section_type not in (
        "theoretical",
        "practical",
    ):
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True,
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
            "لا توجد ملفات مضافة لهذا القسم حاليًا.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ رجوع للملفات",
                        callback_data=(
                            f"content:files:"
                            f"{subject_id}:{owner_id}"
                        ),
                    )
                ]
            ]),
        )
        return

    keyboard = []

    for file in files:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📄 {file['name']}",
                callback_data=(
                    f"file:"
                    f"{file['id']}:"
                    f"{owner_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ رجوع للملفات",
            callback_data=(
                f"content:files:"
                f"{subject_id}:{owner_id}"
            ),
        )
    ])

    await query.edit_message_text(
        f"📄 الملفات — {section_name}\n\n"
        "اختر الملف:",
        reply_markup=InlineKeyboardMarkup(keyboard),
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
            show_alert=True,
        )
        return

    file_id = parts[1]
    owner_id = parts[2]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            owner_error(),
            show_alert=True,
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

    try:
        sent = await send_content_item(
            query.message,
            file,
            "📄",
        )

        if not sent:
            await query.message.reply_text(
                "⚠️ هذا الملف غير مرتبط بملف Telegram."
            )

    except Exception as exc:
        print(
            f"FILE SEND ERROR: {exc}"
        )

        await query.message.reply_text(
            "❌ حدث خطأ أثناء إرسال الملف."
        )


async def show_summaries_or_drawings(
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
            show_alert=True,
        )
        return

    content_type = parts[1]
    subject_id = parts[2]
    owner_id = parts[3]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            owner_error(),
            show_alert=True,
        )
        return

    # =========================
    # الملخصات
    # =========================

    if content_type == "summaries":
        await query.answer()

        await query.edit_message_text(
            "📝 الملخصات\n\n"
            "اختر القسم:",
            reply_markup=summaries_section_keyboard(
                subject_id,
                query.from_user.id,
            ),
        )

        return

    # =========================
    # الرسومات
    # =========================

    if content_type == "drawings":
        await show_drawings(
            update,
            context,
        )
        return

    await query.answer(
        "❌ القسم غير صالح.",
        show_alert=True,
    )


async def show_summary_section(
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
            show_alert=True,
        )
        return

    section_type = parts[1]
    subject_id = parts[2]
    owner_id = parts[3]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            owner_error(),
            show_alert=True,
        )
        return

    if section_type not in (
        "theoretical",
        "practical",
    ):
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True,
        )
        return

    await query.answer()

    response = (
        supabase
        .table("summaries")
        .select("*")
        .eq("subject_id", subject_id)
        .eq("section_type", section_type)
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .order("sort_order")
        .execute()
    )

    summaries = response.data or []

    section_name = (
        "📖 النظري"
        if section_type == "theoretical"
        else "🧪 العملي"
    )

    if not summaries:
        await query.edit_message_text(
            f"📝 الملخصات — {section_name}\n\n"
            "لا توجد ملخصات مضافة لهذا القسم حاليًا.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ رجوع للملخصات",
                        callback_data=(
                            f"content:summaries:"
                            f"{subject_id}:{owner_id}"
                        ),
                    )
                ]
            ]),
        )
        return

    keyboard = []

    for item in summaries:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📝 {item['name']}",
                callback_data=(
                    f"study_item:"
                    f"summaries:"
                    f"{item['id']}:"
                    f"{subject_id}:"
                    f"{owner_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ رجوع للملخصات",
            callback_data=(
                f"content:summaries:"
                f"{subject_id}:{owner_id}"
            ),
        )
    ])

    await query.edit_message_text(
        f"📝 الملخصات — {section_name}\n\n"
        "اختر الملخص:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_all_summaries(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    # content:summaries:all:subject_id:user_id

    if (
        len(parts) != 5
        or parts[0] != "content"
        or parts[1] != "summaries"
        or parts[2] != "all"
    ):
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    subject_id = parts[3]
    owner_id = parts[4]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            owner_error(),
            show_alert=True,
        )
        return

    await query.answer()

    response = (
        supabase
        .table("summaries")
        .select("*")
        .eq("subject_id", subject_id)
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .order("sort_order")
        .execute()
    )

    summaries = response.data or []

    if not summaries:
        await query.edit_message_text(
            "📚 جميع الملخصات\n\n"
            "⚠️ لا توجد ملخصات مضافة لهذه المادة حاليًا.",
            reply_markup=back_content_keyboard(
                subject_id,
                owner_id,
            ),
        )
        return

    await query.edit_message_text(
        "📚 جميع الملخصات\n\n"
        "⏳ جاري إرسال الملخصات النظرية والعملية..."
    )

    sent_count = 0
    failed_count = 0

    for item in summaries:
        try:
            sent = await send_content_item(
                query.message,
                item,
                "📝",
            )

            if sent:
                sent_count += 1
            else:
                failed_count += 1

        except Exception as exc:
            print(
                f"ALL SUMMARIES SEND ERROR: {exc}"
            )
            failed_count += 1

    result_text = (
        "📚 تم إرسال جميع الملخصات.\n\n"
        f"✅ تم إرسال: {sent_count}"
    )

    if failed_count:
        result_text += (
            f"\n⚠️ تعذر إرسال: {failed_count}"
        )

    await query.message.reply_text(
        result_text,
        reply_markup=back_content_keyboard(
            subject_id,
            owner_id,
        ),
    )


async def show_drawings(
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
            show_alert=True,
        )
        return

    subject_id = parts[2]
    owner_id = parts[3]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            owner_error(),
            show_alert=True,
        )
        return

    await query.answer()

    response = (
        supabase
        .table("drawings")
        .select("*")
        .eq("subject_id", subject_id)
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .order("sort_order")
        .execute()
    )

    drawings = response.data or []

    if not drawings:
        await query.edit_message_text(
            "🎨 الرسومات\n\n"
            "لا توجد رسومات مضافة حاليًا.",
            reply_markup=back_content_keyboard(
                subject_id,
                owner_id,
            ),
        )
        return

    keyboard = []

    for item in drawings:
        keyboard.append([
            InlineKeyboardButton(
                text=f"🎨 {item['name']}",
                callback_data=(
                    f"study_item:"
                    f"drawings:"
                    f"{item['id']}:"
                    f"{subject_id}:"
                    f"{owner_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ رجوع للمادة",
            callback_data=(
                f"back_content:"
                f"{subject_id}:{owner_id}"
            ),
        )
    ])

    await query.edit_message_text(
        "🎨 الرسومات\n\n"
        "اختر الرسم:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def study_item_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    if len(parts) != 5:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    content_type = parts[1]
    item_id = parts[2]
    subject_id = parts[3]
    owner_id = parts[4]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            owner_error(),
            show_alert=True,
        )
        return

    if content_type == "summaries":
        table_name = "summaries"
        icon = "📝"

    elif content_type == "drawings":
        table_name = "drawings"
        icon = "🎨"

    else:
        await query.answer(
            "❌ القسم غير صالح.",
            show_alert=True,
        )
        return

    await query.answer()

    response = (
        supabase
        .table(table_name)
        .select("*")
        .eq("id", item_id)
        .eq("subject_id", subject_id)
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )

    items = response.data or []

    if not items:
        await query.message.reply_text(
            "❌ المحتوى غير موجود."
        )
        return

    item = items[0]

    try:
        sent = await send_content_item(
            query.message,
            item,
            icon,
        )

        if not sent:
            await query.message.reply_text(
                "⚠️ هذا المحتوى غير مرتبط بملف Telegram."
            )

    except Exception as exc:
        print(
            f"STUDY ITEM SEND ERROR: {exc}"
        )

        await query.message.reply_text(
            "❌ حدث خطأ أثناء إرسال المحتوى."
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
            show_alert=True,
        )
        return

    subject_id = parts[1]
    owner_id = parts[2]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            owner_error(),
            show_alert=True,
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
            show_alert=True,
        )
        return

    subject = subjects[0]
    stage_id = subject.get("stage_id")

    if stage_id is None:
        await query.answer(
            "❌ تعذر تحديد المرحلة الخاصة بالمادة.",
            show_alert=True,
        )
        return

    await query.answer()

    description = (
        subject.get("description")
        or "لا يوجد وصف للمادة حاليًا."
    )

    await query.edit_message_text(
        f"📘 {subject['name']}\n\n"
        f"{description}\n\n"
        "اختر القسم:",
        reply_markup=content_keyboard(
            subject_id,
            query.from_user.id,
            stage_id,
        ),
    )
