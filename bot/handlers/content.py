from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.database.client import supabase
from bot.keyboards.content import (
    content_keyboard,
    files_section_keyboard,
    summaries_section_keyboard,
    drawings_section_keyboard,
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
                callback_data=f"back_content:{subject_id}:{owner_id}",
            )
        ]
    ])


def back_section_keyboard(callback_data, text):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text,
                callback_data=callback_data,
            )
        ]
    ])


async def send_content_item(
    message,
    item,
    icon,
    include_description=True,
):
    telegram_file_id = item.get("telegram_file_id")

    if not telegram_file_id:
        return False

    description = (
        item.get("description")
        if include_description
        else None
    )

    caption = build_caption(
        icon,
        item.get("name"),
        description,
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


async def get_collection_description(
    subject_id,
    content_type,
):
    try:
        response = (
            supabase
            .table("content_bundle_descriptions")
            .select("description")
            .eq("subject_id", subject_id)
            .eq("content_type", content_type)
            .limit(1)
            .execute()
        )

        rows = response.data or []

        if rows:
            return (
                rows[0].get("description")
                or ""
            ).strip()

    except Exception as exc:
        print(
            "COLLECTION DESCRIPTION READ ERROR:",
            type(exc).__name__,
            exc,
        )

    return ""


async def show_files(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

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

        description = await get_collection_description(
            subject_id,
            "files",
        )

        await query.edit_message_text(
            "📚 جميع الملفات\n\n"
            "⏳ جاري إرسال الملفات النظرية والعملية..."
        )

        if description:
            try:
                await query.message.reply_text(
                    description
                )
            except Exception as exc:
                print(
                    "ALL FILES DESCRIPTION SEND ERROR:",
                    type(exc).__name__,
                    exc,
                )

        sent_count = 0
        failed_count = 0

        for item in files:
            try:
                sent = await send_content_item(
                    query.message,
                    item,
                    "📄",
                    include_description=False,
                )

                if sent:
                    sent_count += 1
                else:
                    failed_count += 1

            except Exception as exc:
                print(
                    "ALL FILES SEND ERROR:",
                    type(exc).__name__,
                    exc,
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
            reply_markup=back_section_keyboard(
                f"content:files:{subject_id}:{owner_id}",
                "⬅️ رجوع للملفات",
            ),
        )
        return

    keyboard = []

    for item in files:
        keyboard.append([
            InlineKeyboardButton(
                f"📄 {item['name']}",
                callback_data=(
                    f"file:"
                    f"{item['id']}:"
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
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
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

    try:
        sent = await send_content_item(
            query.message,
            files[0],
            "📄",
            include_description=True,
        )

        if not sent:
            await query.message.reply_text(
                "⚠️ هذا الملف غير مرتبط بملف Telegram."
            )

    except Exception as exc:
        print(
            "FILE SEND ERROR:",
            type(exc).__name__,
            exc,
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

    if content_type == "drawings":
        await query.answer()

        await query.edit_message_text(
            "🎨 الرسومات\n\n"
            "اختر العملية:",
            reply_markup=drawings_section_keyboard(
                subject_id,
                query.from_user.id,
            ),
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
            reply_markup=back_section_keyboard(
                f"content:summaries:{subject_id}:{owner_id}",
                "⬅️ رجوع للملخصات",
            ),
        )
        return

    keyboard = []

    for item in summaries:
        keyboard.append([
            InlineKeyboardButton(
                f"📝 {item['name']}",
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
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def show_all_summaries(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

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

    description = await get_collection_description(
        subject_id,
        "summaries",
    )

    await query.edit_message_text(
        "📚 جميع الملخصات\n\n"
        "⏳ جاري إرسال الملخصات النظرية والعملية..."
    )

    if description:
        try:
            await query.message.reply_text(
                description
            )
        except Exception as exc:
            print(
                "ALL SUMMARIES DESCRIPTION SEND ERROR:",
                type(exc).__name__,
                exc,
            )

    sent_count = 0
    failed_count = 0

    for item in summaries:
        try:
            sent = await send_content_item(
                query.message,
                item,
                "📝",
                include_description=False,
            )

            if sent:
                sent_count += 1
            else:
                failed_count += 1

        except Exception as exc:
            print(
                "ALL SUMMARIES SEND ERROR:",
                type(exc).__name__,
                exc,
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


async def show_all_drawings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    if (
        len(parts) != 5
        or parts[0] != "content"
        or parts[1] != "drawings"
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
            "🎨 جميع الرسومات\n\n"
            "⚠️ لا توجد رسومات مضافة لهذه المادة حاليًا.",
            reply_markup=back_content_keyboard(
                subject_id,
                owner_id,
            ),
        )
        return

    await query.edit_message_text(
        "🎨 جميع الرسومات\n\n"
        "⏳ جاري إرسال جميع الرسومات..."
    )

    sent_count = 0
    failed_count = 0

    for item in drawings:
        try:
            sent = await send_content_item(
                query.message,
                item,
                "🎨",
                include_description=False,
            )

            if sent:
                sent_count += 1
            else:
                failed_count += 1

        except Exception as exc:
            print(
                "ALL DRAWINGS SEND ERROR:",
                type(exc).__name__,
                exc,
            )
            failed_count += 1

    result_text = (
        "🎨 تم إرسال جميع الرسومات.\n\n"
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
                f"🎨 {item['name']}",
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
            "📚 إرسال جميع الرسومات",
            callback_data=(
                f"content:drawings:all:"
                f"{subject_id}:{owner_id}"
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
        "اختر الرسم أو إرسالها كلها:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
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

    try:
        sent = await send_content_item(
            query.message,
            items[0],
            icon,
            include_description=True,
        )

        if not sent:
            await query.message.reply_text(
                "⚠️ هذا المحتوى غير مرتبط بملف Telegram."
            )

    except Exception as exc:
        print(
            "STUDY ITEM SEND ERROR:",
            type(exc).__name__,
            exc,
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
