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
from bot.utils.permissions import (
    has_permission,
    PERMISSION_MANAGE_DESCRIPTIONS,
)


DESC_STAGE = 21
DESC_SUBJECT = 22
DESC_TEXT = 23


def description_type_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="📄 وصف جميع الملفات",
                callback_data="bundle_desc_type:files",
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 وصف جميع الملخصات",
                callback_data="bundle_desc_type:summaries",
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ أدوات الإدارة",
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

    user_id = query.from_user.id

    if not await has_permission(
        user_id,
        PERMISSION_MANAGE_DESCRIPTIONS,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    context.user_data["bundle_desc_owner_id"] = user_id

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

    user_id = query.from_user.id

    if not await has_permission(
        user_id,
        PERMISSION_MANAGE_DESCRIPTIONS,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    owner_id = context.user_data.get(
        "bundle_desc_owner_id"
    )

    if (
        owner_id is not None
        and user_id != owner_id
    ):
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
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

    context.user_data["bundle_desc_type"] = content_type

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
                text=(
                    f"{'🟢' if stage.get('is_active') else '🔴'} "
                    f"المرحلة {stage['stage_number']}"
                ),
                callback_data=(
                    f"bundle_desc_stage:{stage['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="❌ إلغاء",
            callback_data="bundle_desc_cancel",
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
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return DESC_STAGE


async def choose_description_stage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    user_id = query.from_user.id

    owner_id = context.user_data.get(
        "bundle_desc_owner_id"
    )

    if (
        owner_id is not None
        and user_id != owner_id
    ):
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return DESC_STAGE

    if not await has_permission(
        user_id,
        PERMISSION_MANAGE_DESCRIPTIONS,
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
        .eq("is_active", True)
        .order("sort_order")
        .order("id")
        .execute()
    )

    subjects = response.data or []

    keyboard = []

    for subject in subjects:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📘 {subject['name']}",
                callback_data=(
                    f"bundle_desc_subject:{subject['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع",
            callback_data="bundle_desc_back_stage",
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            text="❌ إلغاء",
            callback_data="bundle_desc_cancel",
        )
    ])

    if not subjects:
        await query.edit_message_text(
            "📘 لا توجد مواد فعالة لهذه المرحلة.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return DESC_SUBJECT

    await query.edit_message_text(
        "📘 اختر المادة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return DESC_SUBJECT


async def choose_description_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    user_id = query.from_user.id

    owner_id = context.user_data.get(
        "bundle_desc_owner_id"
    )

    if (
        owner_id is not None
        and user_id != owner_id
    ):
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return DESC_SUBJECT

    if not await has_permission(
        user_id,
        PERMISSION_MANAGE_DESCRIPTIONS,
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

    subject_response = (
        supabase
        .table("subjects")
        .select("id, name")
        .eq("id", subject_id)
        .eq("stage_id", stage_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    subjects = subject_response.data or []

    if not subjects:
        await query.answer(
            "❌ المادة غير موجودة.",
            show_alert=True,
        )
        return DESC_SUBJECT

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
                "stage_id",
                stage_id,
            )
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
            current = str(
                rows[0].get("description")
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
        f"📘 المادة: {subjects[0]['name']}\n\n"
        f"الوصف الحالي:\n"
        f"{current_text}\n\n"
        "أرسل الوصف الجديد الآن.\n"
        "لإزالة الوصف بالكامل اكتب:\n"
        "بدون وصف\n\n"
        "❌ للإلغاء أرسل /cancel"
    )

    return DESC_TEXT


async def receive_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return DESC_TEXT

    user = update.effective_user

    if user is None:
        return ConversationHandler.END

    owner_id = context.user_data.get(
        "bundle_desc_owner_id"
    )

    if (
        owner_id is not None
        and user.id != owner_id
    ):
        return DESC_TEXT

    if not await has_permission(
        user.id,
        PERMISSION_MANAGE_DESCRIPTIONS,
    ):
        await update.message.reply_text(
            "⛔ ليس لديك صلاحية."
        )
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
            "❌ تعذر حفظ الوصف."
        )

        return ConversationHandler.END

    title = (
        "الملفات"
        if content_type == "files"
        else "الملخصات"
    )

    await update.message.reply_text(
        f"✅ تم حفظ وصف جميع {title} للمادة بنجاح."
    )

    for key in (
        "bundle_desc_type",
        "bundle_desc_stage_id",
        "bundle_desc_subject_id",
        "bundle_desc_owner_id",
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
    user = update.effective_user

    if user is not None:
        if not await has_permission(
            user.id,
            PERMISSION_MANAGE_DESCRIPTIONS,
        ):
            if update.message:
                await update.message.reply_text(
                    "⛔ ليس لديك صلاحية."
                )
            return ConversationHandler.END

        owner_id = context.user_data.get(
            "bundle_desc_owner_id"
        )

        if (
            owner_id is not None
            and user.id != owner_id
        ):
            if update.message:
                await update.message.reply_text(
                    "⛔ هذه العملية مو إلك."
                )
            return DESC_TEXT

    for key in (
        "bundle_desc_type",
        "bundle_desc_stage_id",
        "bundle_desc_subject_id",
        "bundle_desc_owner_id",
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


async def bundle_description_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    user_id = query.from_user.id

    owner_id = context.user_data.get(
        "bundle_desc_owner_id"
    )

    if (
        owner_id is not None
        and user_id != owner_id
    ):
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return DESC_STAGE

    if not await has_permission(
        user_id,
        PERMISSION_MANAGE_DESCRIPTIONS,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    await query.answer()

    for key in (
        "bundle_desc_type",
        "bundle_desc_stage_id",
        "bundle_desc_subject_id",
        "bundle_desc_owner_id",
    ):
        context.user_data.pop(
            key,
            None,
        )

    await query.edit_message_text(
        "❌ تم إلغاء العملية."
    )

    return ConversationHandler.END


async def bundle_description_back_stage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    user_id = query.from_user.id

    owner_id = context.user_data.get(
        "bundle_desc_owner_id"
    )

    if (
        owner_id is not None
        and user_id != owner_id
    ):
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return DESC_SUBJECT

    if not await has_permission(
        user_id,
        PERMISSION_MANAGE_DESCRIPTIONS,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    await query.answer()

    content_type = context.user_data.get(
        "bundle_desc_type"
    )

    if content_type not in (
        "files",
        "summaries",
    ):
        return ConversationHandler.END

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
                text=(
                    f"{'🟢' if stage.get('is_active') else '🔴'} "
                    f"المرحلة {stage['stage_number']}"
                ),
                callback_data=(
                    f"bundle_desc_stage:{stage['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="❌ إلغاء",
            callback_data="bundle_desc_cancel",
        )
    ])

    await query.edit_message_text(
        "📝 اختر المرحلة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return DESC_STAGE


def bundle_description_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                choose_description_type,
                pattern=r"^bundle_desc_type:",
            ),
        ],
        states={
            DESC_STAGE: [
                CallbackQueryHandler(
                    choose_description_stage,
                    pattern=r"^bundle_desc_stage:",
                ),
                CallbackQueryHandler(
                    bundle_description_cancel,
                    pattern=r"^bundle_desc_cancel$",
                ),
            ],
            DESC_SUBJECT: [
                CallbackQueryHandler(
                    choose_description_subject,
                    pattern=r"^bundle_desc_subject:",
                ),
                CallbackQueryHandler(
                    bundle_description_back_stage,
                    pattern=r"^bundle_desc_back_stage$",
                ),
                CallbackQueryHandler(
                    bundle_description_cancel,
                    pattern=r"^bundle_desc_cancel$",
                ),
            ],
            DESC_TEXT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_description,
                ),
            ],
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_description,
            ),
        ],
        allow_reentry=True,
    )
