from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters,
)

from bot.database.client import supabase
from bot.handlers.admin import is_admin


DESC_STAGE = 21
DESC_SUBJECT = 22
DESC_TEXT = 23


def description_type_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📄 وصف جميع الملفات",
                callback_data="bundle_desc_type:files",
            )
        ],
        [
            InlineKeyboardButton(
                "📝 وصف جميع الملخصات",
                callback_data="bundle_desc_type:summaries",
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ أدوات الإدارة",
                callback_data="admin_tools",
            )
        ],
    ])


async def bundle_descriptions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    await query.answer()

    await query.edit_message_text(
        "📝 أوصاف الإرسال\n\n"
        "اختر الوصف الذي تريد إدارته:",
        reply_markup=description_type_keyboard(),
    )


async def choose_description_type(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    if not await is_admin(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    parts = query.data.split(":")

    if (
        len(parts) != 2
        or parts[1] not in (
            "files",
            "summaries",
        )
    ):
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    content_type = parts[1]

    context.user_data[
        "bundle_desc_type"
    ] = content_type

    await query.answer()

    response = (
        supabase
        .table("stages")
        .select(
            "id, stage_number, is_active"
        )
        .order("stage_number")
        .execute()
    )

    stages = response.data or []

    keyboard = []

    for stage in stages:
        keyboard.append([
            InlineKeyboardButton(
                (
                    f"{'🟢' if stage.get('is_active') else '🔴'} "
                    f"المرحلة {stage['stage_number']}"
                ),
                callback_data=(
                    f"bundle_desc_stage:"
                    f"{stage['id']}"
                ),
            )
        ])

    title = (
        "الملفات"
        if content_type == "files"
        else "الملخصات"
    )

    await query.edit_message_text(
        f"📝 وصف جميع {title}\n\n"
        "اختر المرحلة:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )

    return DESC_STAGE


async def choose_description_stage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    if not await is_admin(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    parts = query.data.split(":")

    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return DESC_STAGE

    stage_id = parts[1]

    content_type = context.user_data.get(
        "bundle_desc_type"
    )

    if content_type not in (
        "files",
        "summaries",
    ):
        await query.answer(
            "❌ انتهت بيانات العملية.",
            show_alert=True,
        )
        return ConversationHandler.END

    context.user_data[
        "bundle_desc_stage_id"
    ] = stage_id

    await query.answer()

    response = (
        supabase
        .table("subjects")
        .select(
            "id, name, stage_id, is_active"
        )
        .eq("stage_id", stage_id)
        .order("id")
        .execute()
    )

    subjects = response.data or []

    keyboard = []

    for subject in subjects:
        if subject.get("is_active"):
            keyboard.append([
                InlineKeyboardButton(
                    f"📘 {subject['name']}",
                    callback_data=(
                        f"bundle_desc_subject:"
                        f"{subject['id']}"
                    ),
                )
            ])

    await query.edit_message_text(
        "📘 اختر المادة:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )

    return DESC_SUBJECT


async def choose_description_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    if not await is_admin(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    parts = query.data.split(":")

    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return DESC_SUBJECT

    subject_id = parts[1]

    content_type = context.user_data.get(
        "bundle_desc_type"
    )

    stage_id = context.user_data.get(
        "bundle_desc_stage_id"
    )

    if (
        content_type not in (
            "files",
            "summaries",
        )
        or not stage_id
    ):
        await query.answer(
            "❌ انتهت بيانات العملية.",
            show_alert=True,
        )
        return ConversationHandler.END

    context.user_data[
        "bundle_desc_subject_id"
    ] = subject_id

    await query.answer()

    current = ""

    try:
        response = (
            supabase
            .table(
                "content_bundle_descriptions"
            )
            .select("description")
            .eq(
                "subject_id",
                subject_id,
            )
            .eq(
                "content_type",
                content_type,
            )
            .limit(1)
            .execute()
        )

        rows = response.data or []

        if rows:
            current = (
                rows[0].get(
                    "description"
                )
                or ""
            ).strip()

    except Exception as exc:
        print(
            "BUNDLE DESCRIPTION READ ERROR:",
            type(exc).__name__,
            exc,
        )

    title = (
        "الملفات"
        if content_type == "files"
        else "الملخصات"
    )

    current_text = (
        current
        if current
        else "لا يوجد وصف محفوظ حاليًا."
    )

    await query.edit_message_text(
        f"📝 وصف جميع {title}\n\n"
        f"الوصف الحالي:\n"
        f"{current_text}\n\n"
        "أرسل الوصف الجديد الآن.\n"
        "لإزالة الوصف بالكامل اكتب:\n"
        "بدون وصف"
    )

    return DESC_TEXT


async def receive_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ConversationHandler.END

    description = (
        update.message.text or ""
    ).strip()

    if description == "بدون وصف":
        description = ""

    content_type = context.user_data.get(
        "bundle_desc_type"
    )

    stage_id = context.user_data.get(
        "bundle_desc_stage_id"
    )

    subject_id = context.user_data.get(
        "bundle_desc_subject_id"
    )

    if (
        content_type not in (
            "files",
            "summaries",
        )
        or not stage_id
        or not subject_id
    ):
        await update.message.reply_text(
            "❌ انتهت بيانات العملية.\n"
            "ابدأ من أدوات الإدارة مرة ثانية."
        )

        return ConversationHandler.END

    try:
        (
            supabase
            .table(
                "content_bundle_descriptions"
            )
            .upsert(
                {
                    "stage_id": stage_id,
                    "subject_id": subject_id,
                    "content_type": content_type,
                    "description": description,
                },
                on_conflict=(
                    "stage_id,"
                    "subject_id,"
                    "content_type"
                ),
            )
            .execute()
        )

    except Exception as exc:
        print(
            "BUNDLE DESCRIPTION SAVE ERROR:",
            type(exc).__name__,
            exc,
        )

        await update.message.reply_text(
            "❌ تعذر حفظ الوصف.\n"
            "تأكد أنك أنشأت جدول "
            "content_bundle_descriptions "
            "في Supabase."
        )

        return ConversationHandler.END

    title = (
        "الملفات"
        if content_type == "files"
        else "الملخصات"
    )

    await update.message.reply_text(
        f"✅ تم حفظ وصف جميع {title} "
        "للمادة بنجاح."
    )

    for key in (
        "bundle_desc_type",
        "bundle_desc_stage_id",
        "bundle_desc_subject_id",
    ):
        context.user_data.pop(
            key,
            None,
        )

    return ConversationHandler.END


async def cancel_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    for key in (
        "bundle_desc_type",
        "bundle_desc_stage_id",
        "bundle_desc_subject_id",
    ):
        context.user_data.pop(
            key,
            None,
        )

    if update.message:
        await update.message.reply_text(
            "❌ تم إلغاء العملية."
        )

    return ConversationHandler.END


def bundle_description_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                choose_description_type,
                pattern=r"^bundle_desc_type:",
            )
        ],
        states={
            DESC_STAGE: [
                CallbackQueryHandler(
                    choose_description_stage,
                    pattern=r"^bundle_desc_stage:",
                )
            ],
            DESC_SUBJECT: [
                CallbackQueryHandler(
                    choose_description_subject,
                    pattern=r"^bundle_desc_subject:",
                )
            ],
            DESC_TEXT: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_description,
                )
            ],
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_description,
            )
        ],
        allow_reentry=True,
    )
