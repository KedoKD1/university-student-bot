from bot.utils.logging_security import log_error

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaAudio,
    InputMediaDocument,
)
from telegram.ext import ContextTypes

from bot.database.client import supabase
from bot.utils.content_access import active_subject
from bot.keyboards.subjects import back_stages_keyboard
from bot.keyboards.content import (
    content_keyboard,
    files_section_keyboard,
    summaries_section_keyboard,
    drawings_section_keyboard,
)


MAX_CAPTION_LENGTH = 1024
MEDIA_GROUP_LIMIT = 10


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
        "⛔ هذا الاختيار ليس لك.\n"
        "استخدم /start لفتح قائمتك الخاصة."
    )


def back_content_keyboard(subject_id, owner_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⬅️ رجوع إلى المادة",
                callback_data=f"back_content:{subject_id}:{owner_id}",
            )
        ],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data=f"back_main:{owner_id}")],
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


async def _content_heading(query, subject_id, title):
    try:
        subject = active_subject(supabase, subject_id)
    except Exception as exc:
        log_error('STUDENT CONTENT SUBJECT ERROR:', exc)
        await query.edit_message_text(
            "❌ تعذر تحميل المحتوى حاليًا. يمكنك العودة والمحاولة لاحقًا.",
            reply_markup=back_stages_keyboard(query.from_user.id),
        )
        return None
    if subject is None:
        await query.edit_message_text(
            "❌ هذه المادة غير متاحة حاليًا. اختر مادة أخرى.",
            reply_markup=back_stages_keyboard(query.from_user.id),
        )
        return None
    return f"{title}\n📘 المادة: {subject['name']}"


async def _read_content(query, builder, keyboard):
    try:
        return builder.execute().data or []
    except Exception as exc:
        log_error('STUDENT CONTENT READ ERROR:', exc)
        await query.edit_message_text(
            "❌ تعذر تحميل المحتوى حاليًا. يمكنك العودة والمحاولة لاحقًا.",
            reply_markup=keyboard,
        )
        return None


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


def _media_type(item):
    file_type = item.get("file_type")

    if file_type == "photo":
        return "photo"

    if file_type == "video":
        return "video"

    if file_type == "audio":
        return "audio"

    return "document"


def _build_media(item, icon):
    file_type = item.get("file_type")
    telegram_file_id = item.get("telegram_file_id")

    caption = build_caption(
        icon,
        item.get("name"),
        None,
    )

    if file_type == "photo":
        return InputMediaPhoto(
            media=telegram_file_id,
            caption=caption,
        )

    if file_type == "video":
        return InputMediaVideo(
            media=telegram_file_id,
            caption=caption,
        )

    if file_type == "audio":
        return InputMediaAudio(
            media=telegram_file_id,
            caption=caption,
        )

    return InputMediaDocument(
        media=telegram_file_id,
        caption=caption,
    )


async def send_content_collection(
    message,
    items,
    icon,
    subject_id,
):
    """
    إرسال مجموعة محتويات بشكل مجمع قدر الإمكان.

    Telegram يسمح بـ Media Group من نفس النوع:
    - صور
    - فيديوهات
    - صوتيات
    - مستندات

    لذلك نقسم المحتوى إلى مجموعات حسب النوع.
    كل مجموعة تحتوي بحد أقصى 10 عناصر.
    """

    valid_items = [
        item
        for item in items
        if item.get("telegram_file_id")
    ]

    if not valid_items:
        return 0, len(items)

    sent_count = 0
    failed_count = len(items) - len(valid_items)

    groups = []

    current_type = None
    current_group = []

    for item in valid_items:
        item_type = _media_type(item)

        if (
            current_type is None
            or item_type == current_type
        ):
            current_type = item_type
            current_group.append(item)

        else:
            groups.append(
                (current_type, current_group)
            )

            current_type = item_type
            current_group = [item]

    if current_group:
        groups.append(
            (current_type, current_group)
        )

    for group_type, group_items in groups:
        for start in range(
            0,
            len(group_items),
            MEDIA_GROUP_LIMIT,
        ):
            chunk = group_items[
                start:start + MEDIA_GROUP_LIMIT
            ]

            # Recheck per album, not per file, including changes during a send.
            try:
                available = active_subject(supabase, subject_id) is not None
            except Exception as exc:
                log_error('COLLECTION PARENT CHECK ERROR:', exc)
                available = False
            if not available:
                return sent_count, len(items) - sent_count

            # Telegram يدعم Media Group للصور والفيديو
            # وكذلك مجموعات مستقلة للصوتيات والمستندات.
            try:
                media = [
                    _build_media(item, icon)
                    for item in chunk
                ]

                await message.reply_media_group(
                    media=media
                )

                sent_count += len(chunk)

            except Exception as exc:
                log_error('MEDIA GROUP SEND ERROR:', exc)

                try:
                    available = active_subject(supabase, subject_id) is not None
                except Exception as parent_exc:
                    log_error('COLLECTION FALLBACK PARENT CHECK ERROR:', parent_exc)
                    available = False
                if not available:
                    return sent_count, len(items) - sent_count

                # إذا فشل الـ album، نحاول إرسال
                # العناصر بشكل منفرد حتى لا يضيع المحتوى.
                for item in chunk:
                    try:
                        sent = await send_content_item(
                            message,
                            item,
                            icon,
                            include_description=False,
                        )

                        if sent:
                            sent_count += 1
                        else:
                            failed_count += 1

                    except Exception as item_exc:
                        log_error('FALLBACK CONTENT SEND ERROR:', item_exc)
                        failed_count += 1

    return sent_count, failed_count


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
        log_error('COLLECTION DESCRIPTION READ ERROR:', exc)

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

    heading = await _content_heading(
        query, subject_id, "📄 جميع الملفات" if show_all else "📄 الملفات"
    )
    if heading is None:
        return

    if show_all:
        response = (
            supabase
            .table("files")
            .select("*")
            .eq("subject_id", subject_id)
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .order("sort_order")
        )

        files = await _read_content(
            query, response, back_content_keyboard(subject_id, owner_id)
        )
        if files is None:
            return

        if not files:
            await query.edit_message_text(
                f"{heading}\n\n"
                "لا توجد ملفات متاحة لهذه المادة حاليًا. يمكنك الرجوع واختيار نوع محتوى آخر.",
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
            f"{heading}\n\n"
            "⏳ جارٍ إرسال الملفات النظرية والعملية..."
        )

        if description:
            try:
                await query.message.reply_text(
                    description
                )
            except Exception as exc:
                log_error('ALL FILES DESCRIPTION SEND ERROR:', exc)

        sent_count, failed_count = (
            await send_content_collection(
                query.message,
                files,
                "📄",
                subject_id,
            )
        )

        result_text = (
            f"{heading}\n\n"
            f"✅ تم إرسال: {sent_count}"
        )

        if failed_count:
            result_text += (
                f"\n⚠️ تعذر إرسال: {failed_count}"
            )

        await query.edit_message_text(
            result_text,
            reply_markup=back_content_keyboard(
                subject_id,
                owner_id,
            ),
        )

        return

    await query.edit_message_text(
        f"{heading}\n\n"
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
    )

    files = await _read_content(
        query, response, back_section_keyboard(f"content:files:{subject_id}:{owner_id}", "⬅️ رجوع إلى الملفات")
    )
    if files is None:
        return

    section_name = (
        "النظري"
        if section_type == "theoretical"
        else "العملي"
    )

    heading = await _content_heading(query, subject_id, f"📄 الملفات — {section_name}")
    if heading is None:
        return

    if not files:
        await query.edit_message_text(
            f"{heading}\n\n"
            "لا توجد ملفات متاحة لهذا القسم حاليًا. يمكنك الرجوع واختيار قسم آخر.",
            reply_markup=back_section_keyboard(
                f"content:files:{subject_id}:{owner_id}",
                "⬅️ رجوع إلى الملفات",
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
            "⬅️ رجوع إلى الملفات",
            callback_data=(
                f"content:files:"
                f"{subject_id}:{owner_id}"
            ),
        )
    ])

    await query.edit_message_text(
        f"{heading}\n\n"
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
    )

    files = await _read_content(
        query, response, back_stages_keyboard(query.from_user.id)
    )
    if files is None:
        return

    if not files:
        await query.edit_message_text(
            "❌ هذا الملف غير متاح حاليًا. يمكنك الرجوع واختيار ملف آخر.",
            reply_markup=back_stages_keyboard(query.from_user.id),
        )
        return

    if await _content_heading(query, files[0].get('subject_id'), '📄 الملفات') is None:
        return

    recovery_keyboard = (
        back_content_keyboard(files[0]["subject_id"], owner_id)
        if files[0].get("subject_id") is not None
        else back_stages_keyboard(query.from_user.id)
    )

    try:
        sent = await send_content_item(
            query.message,
            files[0],
            "📄",
            include_description=True,
        )

        if not sent:
            await query.edit_message_text(
                "❌ هذا الملف غير متاح حاليًا. يمكنك الرجوع واختيار ملف آخر.",
                reply_markup=recovery_keyboard,
            )

    except Exception as exc:
        log_error('FILE SEND ERROR:', exc)

        await query.edit_message_text(
            "❌ تعذر إرسال الملف حاليًا. يمكنك العودة والمحاولة لاحقًا.",
            reply_markup=recovery_keyboard,
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

        heading = await _content_heading(query, subject_id, "📝 الملخصات")
        if heading is None:
            return

        await query.edit_message_text(
            f"{heading}\n\n"
            "اختر القسم:",
            reply_markup=summaries_section_keyboard(
                subject_id,
                query.from_user.id,
            ),
        )

        return

    if content_type == "drawings":
        await query.answer()

        heading = await _content_heading(query, subject_id, "🎨 الرسومات")
        if heading is None:
            return

        await query.edit_message_text(
            f"{heading}\n\n"
            "اختر عرض جميع الرسومات:",
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
    )

    summaries = await _read_content(
        query, response, back_section_keyboard(f"content:summaries:{subject_id}:{owner_id}", "⬅️ رجوع إلى الملخصات")
    )
    if summaries is None:
        return

    section_name = (
        "النظري"
        if section_type == "theoretical"
        else "العملي"
    )

    heading = await _content_heading(query, subject_id, f"📝 الملخصات — {section_name}")
    if heading is None:
        return

    if not summaries:
        await query.edit_message_text(
            f"{heading}\n\n"
            "لا توجد ملخصات متاحة لهذا القسم حاليًا. يمكنك الرجوع واختيار قسم آخر.",
            reply_markup=back_section_keyboard(
                f"content:summaries:{subject_id}:{owner_id}",
                "⬅️ رجوع إلى الملخصات",
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
            "⬅️ رجوع إلى الملخصات",
            callback_data=(
                f"content:summaries:"
                f"{subject_id}:{owner_id}"
            ),
        )
    ])

    await query.edit_message_text(
        f"{heading}\n\n"
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

    heading = await _content_heading(query, subject_id, "📝 جميع الملخصات")
    if heading is None:
        return

    response = (
        supabase
        .table("summaries")
        .select("*")
        .eq("subject_id", subject_id)
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .order("sort_order")
    )

    summaries = await _read_content(
        query, response, back_content_keyboard(subject_id, owner_id)
    )
    if summaries is None:
        return

    if not summaries:
        await query.edit_message_text(
            f"{heading}\n\n"
            "لا توجد ملخصات متاحة لهذه المادة حاليًا. يمكنك الرجوع واختيار نوع محتوى آخر.",
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
        f"{heading}\n\n"
        "⏳ جارٍ إرسال الملخصات النظرية والعملية..."
    )

    if description:
        try:
            await query.message.reply_text(
                description
            )
        except Exception as exc:
            log_error('ALL SUMMARIES DESCRIPTION SEND ERROR:', exc)

    sent_count, failed_count = (
        await send_content_collection(
            query.message,
            summaries,
            "📝",
            subject_id,
        )
    )

    result_text = (
        f"{heading}\n\n"
        f"✅ تم إرسال: {sent_count}"
    )

    if failed_count:
        result_text += (
            f"\n⚠️ تعذر إرسال: {failed_count}"
        )

    await query.edit_message_text(
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

    heading = await _content_heading(query, subject_id, "🎨 جميع الرسومات")
    if heading is None:
        return

    response = (
        supabase
        .table("drawings")
        .select("*")
        .eq("subject_id", subject_id)
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .order("sort_order")
    )

    drawings = await _read_content(
        query, response, back_content_keyboard(subject_id, owner_id)
    )
    if drawings is None:
        return

    if not drawings:
        await query.edit_message_text(
            f"{heading}\n\n"
            "لا توجد رسومات متاحة لهذه المادة حاليًا. يمكنك الرجوع واختيار نوع محتوى آخر.",
            reply_markup=back_content_keyboard(
                subject_id,
                owner_id,
            ),
        )
        return

    await query.edit_message_text(
        f"{heading}\n\n"
        "⏳ جارٍ إرسال الرسومات..."
    )

    sent_count, failed_count = (
        await send_content_collection(
            query.message,
            drawings,
            "🎨",
            subject_id,
        )
    )

    result_text = (
        f"{heading}\n\n"
        f"✅ تم إرسال: {sent_count}"
    )

    if failed_count:
        result_text += (
            f"\n⚠️ تعذر إرسال: {failed_count}"
        )

    await query.edit_message_text(
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

    if await _content_heading(query, subject_id, '🎨 الرسومات') is None:
        return

    response = (
        supabase
        .table("drawings")
        .select("*")
        .eq("subject_id", subject_id)
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .order("sort_order")
    )
    drawings = await _read_content(query, response, back_content_keyboard(subject_id, owner_id))
    if drawings is None:
        return

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
            "🎨 إرسال جميع الرسومات",
            callback_data=(
                f"content:drawings:all:"
                f"{subject_id}:{owner_id}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ رجوع إلى المادة",
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

    if await _content_heading(query, subject_id, f'{icon} المحتوى') is None:
        return

    response = (
        supabase
        .table(table_name)
        .select("*")
        .eq("id", item_id)
        .eq("subject_id", subject_id)
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .limit(1)
    )

    items = await _read_content(
        query, response, back_content_keyboard(subject_id, owner_id)
    )
    if items is None:
        return

    if not items:
        await query.edit_message_text(
            "❌ هذا المحتوى غير متاح حاليًا. يمكنك الرجوع واختيار محتوى آخر.",
            reply_markup=back_content_keyboard(subject_id, owner_id),
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
            await query.edit_message_text(
                "❌ هذا المحتوى غير متاح حاليًا. يمكنك الرجوع واختيار محتوى آخر.",
                reply_markup=back_content_keyboard(subject_id, owner_id),
            )

    except Exception as exc:
        log_error('STUDY ITEM SEND ERROR:', exc)

        await query.edit_message_text(
            "❌ تعذر إرسال المحتوى حاليًا. يمكنك العودة والمحاولة لاحقًا.",
            reply_markup=back_content_keyboard(subject_id, owner_id),
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

    await query.answer()

    try:
        subject = active_subject(supabase, subject_id)
    except Exception as exc:
        log_error('STUDENT CONTENT BACK ERROR:', exc)
        await query.edit_message_text(
            "❌ تعذر تحميل المادة حاليًا. يمكنك العودة والمحاولة لاحقًا.",
            reply_markup=back_stages_keyboard(query.from_user.id),
        )
        return

    if subject is None:
        await query.edit_message_text(
            "❌ هذه المادة غير متاحة حاليًا. اختر مادة أخرى.",
            reply_markup=back_stages_keyboard(query.from_user.id),
        )
        return

    stage_id = subject.get("stage_id")

    if stage_id is None:
        await query.edit_message_text(
            "❌ هذه المادة غير متاحة حاليًا. اختر مادة أخرى.",
            reply_markup=back_stages_keyboard(query.from_user.id),
        )
        return

    description = (
        subject.get("description")
        or "لا يوجد وصف للمادة حاليًا."
    )

    await query.edit_message_text(
        f"📘 المادة: {subject['name']}\n\n"
        f"{description}\n\n"
        "اختر نوع المحتوى:",
        reply_markup=content_keyboard(
            subject_id,
            query.from_user.id,
            stage_id,
        ),
    )
