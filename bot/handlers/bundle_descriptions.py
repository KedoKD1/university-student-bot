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
    require_callback_owner,
    PERMISSION_MANAGE_DESCRIPTIONS,
)


DESC_STAGE = 21
DESC_SUBJECT = 22
DESC_TEXT = 23


def description_type_keyboard(owner_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="📄 وصف جميع الملفات",
                callback_data=f'bundle_desc_type:files:{owner_id}',
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 وصف جميع الملخصات",
                callback_data=f'bundle_desc_type:summaries:{owner_id}',
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ أدوات الإدارة",
                callback_data="admin_tools",
            )
        ],
    ])


def clear_description_conversation(context):
    for key in ("bundle_desc_type", "bundle_desc_stage_id", "bundle_desc_subject_id", "bundle_desc_owner_id"):
        context.admin_data.pop(key, None)


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
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    clear_description_conversation(context)
    context.admin_data["bundle_desc_owner_id"] = user_id

    await query.answer()

    await query.edit_message_text(
        "📝 أوصاف الإرسال\n\n"
        "اختر الوصف الذي تريد إدارته:",
        reply_markup=description_type_keyboard(user_id),
    )


async def choose_description_type(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not await require_callback_owner(query):
        return None

    if query is None or query.from_user is None:
        clear_description_conversation(context)
        return ConversationHandler.END

    user_id = query.from_user.id

    if not await has_permission(
        user_id,
        PERMISSION_MANAGE_DESCRIPTIONS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        clear_description_conversation(context)
        return ConversationHandler.END

    owner_id = context.admin_data.get(
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
        return None

    parts = query.data.rsplit(":", 1)[0].split(":")

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
        clear_description_conversation(context)
        return ConversationHandler.END

    clear_description_conversation(context)
    context.admin_data["bundle_desc_owner_id"] = user_id

    content_type = parts[1]

    context.admin_data["bundle_desc_type"] = content_type

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
                    f"bundle_desc_stage:{stage['id']}:{user_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="❌ إلغاء",
            callback_data=f'bundle_desc_cancel:{user_id}',
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

    if not await require_callback_owner(query):
        return None

    if query is None or query.from_user is None:
        clear_description_conversation(context)
        return ConversationHandler.END

    user_id = query.from_user.id

    owner_id = context.admin_data.get(
        "bundle_desc_owner_id"
    )

    if owner_id is None:
        clear_description_conversation(context)
        await query.answer("❌ انتهت بيانات العملية.", show_alert=True)
        return ConversationHandler.END

    if user_id != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return DESC_STAGE

    if not await has_permission(
        user_id,
        PERMISSION_MANAGE_DESCRIPTIONS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        clear_description_conversation(context)
        return ConversationHandler.END

    parts = query.data.rsplit(":", 1)[0].split(":")

    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return DESC_STAGE

    stage_id = parts[1]

    content_type = context.admin_data.get(
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
        clear_description_conversation(context)
        return ConversationHandler.END

    context.admin_data[
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
                    f"bundle_desc_subject:{subject['id']}:{user_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع",
            callback_data=f'bundle_desc_back_stage:{user_id}',
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            text="❌ إلغاء",
            callback_data=f'bundle_desc_cancel:{user_id}',
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

    if not await require_callback_owner(query):
        return None

    if query is None or query.from_user is None:
        clear_description_conversation(context)
        return ConversationHandler.END

    user_id = query.from_user.id

    owner_id = context.admin_data.get(
        "bundle_desc_owner_id"
    )

    if owner_id is None:
        clear_description_conversation(context)
        await query.answer("❌ انتهت بيانات العملية.", show_alert=True)
        return ConversationHandler.END

    if user_id != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return DESC_SUBJECT

    if not await has_permission(
        user_id,
        PERMISSION_MANAGE_DESCRIPTIONS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        clear_description_conversation(context)
        return ConversationHandler.END

    parts = query.data.rsplit(":", 1)[0].split(":")

    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return DESC_SUBJECT

    subject_id = parts[1]

    content_type = context.admin_data.get(
        "bundle_desc_type"
    )

    stage_id = context.admin_data.get(
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
        clear_description_conversation(context)
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

    context.admin_data[
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
        "❌ للإلغاء أرسل /cancel",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ إلغاء", callback_data=f"bundle_desc_cancel:{user_id}")
        ]]),
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
        return None

    owner_id = context.admin_data.get(
        "bundle_desc_owner_id"
    )

    if owner_id is None:
        clear_description_conversation(context)
        return ConversationHandler.END

    if user.id != owner_id:
        return DESC_TEXT

    if not await has_permission(
        user.id,
        PERMISSION_MANAGE_DESCRIPTIONS,
        refresh=True,
    ):
        await update.message.reply_text(
            "⛔ ليس لديك صلاحية."
        )
        clear_description_conversation(context)
        return ConversationHandler.END

    description = (
        update.message.text or ""
    ).strip()

    if description == "بدون وصف":
        description = ""

    content_type = context.admin_data.get(
        "bundle_desc_type"
    )

    stage_id = context.admin_data.get(
        "bundle_desc_stage_id"
    )

    subject_id = context.admin_data.get(
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
        clear_description_conversation(context)
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

        clear_description_conversation(context)
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
        context.admin_data.pop(
            key,
            None,
        )

    return ConversationHandler.END


async def cancel_description(update, context):
    user = update.effective_user
    if user is None or context.admin_data.get("bundle_desc_owner_id") != user.id:
        return None
    allowed = await has_permission(user.id, PERMISSION_MANAGE_DESCRIPTIONS, refresh=True)
    clear_description_conversation(context)
    if update.message:
        await update.message.reply_text(
            "❌ تم إلغاء العملية." if allowed else "⛔ ليس لديك صلاحية."
        )
    return ConversationHandler.END


async def bundle_description_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not await require_callback_owner(query):
        return None

    if query is None or query.from_user is None:
        clear_description_conversation(context)
        return ConversationHandler.END

    user_id = query.from_user.id

    owner_id = context.admin_data.get(
        "bundle_desc_owner_id"
    )

    if owner_id is None:
        clear_description_conversation(context)
        await query.answer("❌ انتهت بيانات العملية.", show_alert=True)
        return ConversationHandler.END

    if user_id != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return DESC_STAGE

    if not await has_permission(
        user_id,
        PERMISSION_MANAGE_DESCRIPTIONS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        clear_description_conversation(context)
        return ConversationHandler.END

    await query.answer()

    for key in (
        "bundle_desc_type",
        "bundle_desc_stage_id",
        "bundle_desc_subject_id",
        "bundle_desc_owner_id",
    ):
        context.admin_data.pop(
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

    if not await require_callback_owner(query):
        return None

    if query is None or query.from_user is None:
        clear_description_conversation(context)
        return ConversationHandler.END

    user_id = query.from_user.id

    owner_id = context.admin_data.get(
        "bundle_desc_owner_id"
    )

    if owner_id is None:
        clear_description_conversation(context)
        await query.answer("❌ انتهت بيانات العملية.", show_alert=True)
        return ConversationHandler.END

    if user_id != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return DESC_SUBJECT

    if not await has_permission(
        user_id,
        PERMISSION_MANAGE_DESCRIPTIONS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        clear_description_conversation(context)
        return ConversationHandler.END

    await query.answer()

    content_type = context.admin_data.get(
        "bundle_desc_type"
    )

    if content_type not in (
        "files",
        "summaries",
    ):
        clear_description_conversation(context)
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
                    f"bundle_desc_stage:{stage['id']}:{user_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="❌ إلغاء",
            callback_data=f'bundle_desc_cancel:{user_id}',
        )
    ])

    await query.edit_message_text(
        "📝 اختر المرحلة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return DESC_STAGE


async def back_from_description_operation(update, context):
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return None
    if context.admin_data.get("bundle_desc_owner_id") != user.id:
        await query.answer("⛔ هذه العملية ليست لك.", show_alert=True)
        return None
    prefix = (query.data or "").split(":", 1)[0]
    if not await has_permission(user.id, PERMISSION_MANAGE_DESCRIPTIONS, refresh=True):
        clear_description_conversation(context)
        await query.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return ConversationHandler.END

    from bot.handlers.admin import admin_back
    from bot.handlers.admin_tools import admin_tools
    navigation = {
        "bundle_descriptions": bundle_descriptions,
        "admin_tools": admin_tools,
        "admin_back": admin_back,
    }
    clear_description_conversation(context)
    await navigation[prefix](update, context)
    return ConversationHandler.END


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
            ],
            DESC_SUBJECT: [
                CallbackQueryHandler(
                    choose_description_subject,
                    pattern=r"^bundle_desc_subject:",
                ),
                CallbackQueryHandler(
                    bundle_description_back_stage,
                    pattern=r"^bundle_desc_back_stage:",
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
            CallbackQueryHandler(bundle_description_cancel, pattern=r"^bundle_desc_cancel:\d+$"),
            CallbackQueryHandler(back_from_description_operation, pattern='^(?:bundle_descriptions$|admin_tools$|admin_back$)'),
            CommandHandler(
                "cancel",
                cancel_description,
            ),
        ],
        allow_reentry=True,
    )
