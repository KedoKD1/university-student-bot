from datetime import datetime, timezone

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)

from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.database.client import supabase

from bot.utils.permissions import (
    PERMISSION_MANAGE_GRADES,
    has_permission,
)


# ============================================================
# Conversation States
# ============================================================

ADD_GRADE_NAME = 1
ADD_GRADE_DESCRIPTION = 2
ADD_GRADE_UPLOAD = 3

EDIT_GRADE_NAME = 4
EDIT_GRADE_DESCRIPTION = 5

REPLACE_GRADE_UPLOAD = 6


# ============================================================
# Helpers
# ============================================================

def normalize_text(text):
    return " ".join(text.strip().split())


def normalize_description(text):
    text = text.strip()

    if text in {
        "-",
        "لا يوجد",
        "بدون وصف",
        "بدون",
    }:
        return None

    return text


def extract_telegram_file(message):
    if message.document:
        return (
            "document",
            message.document.file_id,
            message.document.file_size,
        )

    if message.photo:
        photo = message.photo[-1]
        return (
            "photo",
            photo.file_id,
            photo.file_size,
        )

    if message.video:
        return (
            "video",
            message.video.file_id,
            message.video.file_size,
        )

    if message.audio:
        return (
            "audio",
            message.audio.file_id,
            message.audio.file_size,
        )

    return None, None, None


def clear_grade_conversation(context):
    keys = [
        "admin_grade_stage_id",
        "admin_grade_file_id",
        "admin_grade_name",
        "admin_grade_description",
    ]

    for key in keys:
        context.user_data.pop(key, None)


# ============================================================
# Keyboards
# ============================================================

def grades_stage_keyboard(stages):
    keyboard = []

    for stage in stages:
        if not stage.get("is_active", True):
            continue

        keyboard.append([
            InlineKeyboardButton(
                text=f"📚 المرحلة {stage['stage_number']}",
                callback_data=(
                    f"admin_grade_stage:{stage['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للوحة الإدارة",
            callback_data="admin_back",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def grades_list_keyboard(files, stage_id):
    keyboard = []

    for grade_file in files:
        status = (
            "🟢"
            if grade_file.get("is_active")
            else "🔴"
        )

        keyboard.append([
            InlineKeyboardButton(
                text=(
                    f"{status} "
                    f"{grade_file['name']}"
                ),
                callback_data=(
                    f"manage_grade:"
                    f"{grade_file['id']}:{stage_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="➕ إضافة ملف درجات",
            callback_data=f"add_grade:{stage_id}",
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للمراحل",
            callback_data="admin_grades",
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            text="🛠️ لوحة الإدارة",
            callback_data="admin_back",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def grade_manage_keyboard(
    file_id,
    stage_id,
    is_active,
):
    if is_active:
        toggle_text = "🔴 تعطيل الملف"
        toggle_callback = (
            f"disable_grade:{file_id}:{stage_id}"
        )
    else:
        toggle_text = "🟢 تفعيل الملف"
        toggle_callback = (
            f"enable_grade:{file_id}:{stage_id}"
        )

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="✏️ تعديل البيانات",
                callback_data=(
                    f"edit_grade:{file_id}:{stage_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 استبدال الملف",
                callback_data=(
                    f"replace_grade:{file_id}:{stage_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text=toggle_text,
                callback_data=toggle_callback,
            )
        ],
        [
            InlineKeyboardButton(
                text="🗑️ حذف الملف",
                callback_data=(
                    f"delete_grade:{file_id}:{stage_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ رجوع لملفات الدرجات",
                callback_data=(
                    f"admin_grade_list:{stage_id}"
                ),
            )
        ],
    ])


def delete_grade_keyboard(file_id, stage_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="🗑️ نعم، احذف",
                callback_data=(
                    f"confirm_delete_grade:"
                    f"{file_id}:{stage_id}"
                ),
            ),
            InlineKeyboardButton(
                text="❌ إلغاء",
                callback_data=(
                    f"manage_grade:"
                    f"{file_id}:{stage_id}"
                ),
            ),
        ]
    ])


# ============================================================
# Permission helper
# ============================================================

async def can_manage_grades(user_id):
    return await has_permission(
        user_id,
        PERMISSION_MANAGE_GRADES,
    )


# ============================================================
# Admin Grades
# ============================================================

async def admin_grades(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await can_manage_grades(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية إدارة الدرجات.",
            show_alert=True,
        )
        return

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

    if not stages:
        await query.edit_message_text(
            "📝 إدارة الدرجات\n\n"
            "❌ لا توجد مراحل في قاعدة البيانات.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🛠️ لوحة الإدارة",
                        callback_data="admin_back",
                    )
                ]
            ]),
        )
        return

    await query.edit_message_text(
        "📝 إدارة الدرجات\n\n"
        "اختر المرحلة:",
        reply_markup=grades_stage_keyboard(
            stages
        ),
    )


# ============================================================
# Stage
# ============================================================

async def admin_grade_stage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await can_manage_grades(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    stage_id = int(parts[1])

    await query.answer()

    await show_grade_list(
        update,
        context,
        stage_id,
    )


# ============================================================
# Grade List
# ============================================================

async def show_grade_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    stage_id: int,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    response = (
        supabase
        .table("grade_files")
        .select(
            "id, stage_id, name, description, "
            "telegram_file_id, file_type, file_size, "
            "is_active, created_at, updated_at, deleted_at"
        )
        .eq("stage_id", stage_id)
        .is_("deleted_at", "null")
        .order("id")
        .execute()
    )

    files = response.data or []

    if files:
        text = (
            "📝 إدارة الدرجات\n\n"
            "اختر ملف الدرجات الذي تريد إدارته:"
        )
    else:
        text = (
            "📝 إدارة الدرجات\n\n"
            "❌ لا توجد ملفات درجات لهذه المرحلة حالياً."
        )

    await query.edit_message_text(
        text,
        reply_markup=grades_list_keyboard(
            files,
            stage_id,
        ),
    )


# ============================================================
# Manage Grade
# ============================================================

async def manage_grade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await can_manage_grades(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    file_id = int(parts[1])
    stage_id = int(parts[2])

    response = (
        supabase
        .table("grade_files")
        .select("*")
        .eq("id", file_id)
        .eq("stage_id", stage_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )

    files = response.data or []

    if not files:
        await query.answer(
            "❌ الملف غير موجود.",
            show_alert=True,
        )
        return

    grade_file = files[0]

    await query.answer()

    status = (
        "🟢 فعال"
        if grade_file.get("is_active")
        else "🔴 معطل"
    )

    description = (
        grade_file.get("description")
        or "لا يوجد وصف"
    )

    await query.edit_message_text(
        "📝 إدارة ملف الدرجات\n\n"
        f"📄 الاسم: {grade_file['name']}\n"
        f"📌 الوصف: {description}\n"
        f"📊 الحالة: {status}",
        reply_markup=grade_manage_keyboard(
            file_id,
            stage_id,
            grade_file.get("is_active", False),
        ),
    )


# ============================================================
# Add Grade
# ============================================================

async def add_grade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    if not await can_manage_grades(
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
        return ConversationHandler.END

    stage_id = int(parts[1])

    context.user_data["admin_grade_stage_id"] = stage_id

    await query.answer()

    await query.message.reply_text(
        "➕ إضافة ملف درجات\n\n"
        "أرسل اسم الملف:"
    )

    return ADD_GRADE_NAME


async def add_grade_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_GRADE_NAME

    name = normalize_text(
        update.message.text or ""
    )

    if not name:
        await update.message.reply_text(
            "❌ الاسم لا يمكن أن يكون فارغاً.\n"
            "أرسل اسم الملف مرة أخرى:"
        )
        return ADD_GRADE_NAME

    context.user_data["admin_grade_name"] = name

    await update.message.reply_text(
        "📝 أرسل وصف الملف.\n\n"
        "إذا لا يوجد وصف أرسل: -"
    )

    return ADD_GRADE_DESCRIPTION


async def add_grade_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_GRADE_DESCRIPTION

    description = normalize_description(
        update.message.text or ""
    )

    context.user_data[
        "admin_grade_description"
    ] = description

    await update.message.reply_text(
        "📤 الآن أرسل ملف الدرجات.\n\n"
        "المسموح: مستند، صورة، فيديو أو ملف صوتي."
    )

    return ADD_GRADE_UPLOAD


async def add_grade_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_GRADE_UPLOAD

    (
        file_type,
        telegram_file_id,
        file_size,
    ) = extract_telegram_file(
        update.message
    )

    if not telegram_file_id:
        await update.message.reply_text(
            "❌ لم أتعرف على الملف.\n"
            "أرسل مستنداً أو صورة أو فيديو أو ملف صوتي."
        )
        return ADD_GRADE_UPLOAD

    stage_id = context.user_data.get(
        "admin_grade_stage_id"
    )

    name = context.user_data.get(
        "admin_grade_name"
    )

    description = context.user_data.get(
        "admin_grade_description"
    )

    if not stage_id or not name:
        clear_grade_conversation(context)

        await update.message.reply_text(
            "❌ انتهت جلسة الإضافة.\n"
            "ابدأ الإضافة من جديد."
        )

        return ConversationHandler.END

    try:
        (
            supabase
            .table("grade_files")
            .insert({
                "stage_id": stage_id,
                "name": name,
                "description": description,
                "telegram_file_id": telegram_file_id,
                "file_type": file_type,
                "file_size": file_size,
                "is_active": True,
            })
            .execute()
        )

    except Exception as exc:
        print(
            "ADD GRADE ERROR:",
            type(exc).__name__,
            exc,
        )

        await update.message.reply_text(
            "❌ حدث خطأ أثناء حفظ ملف الدرجات."
        )

        clear_grade_conversation(context)

        return ConversationHandler.END

    clear_grade_conversation(context)

    await update.message.reply_text(
        "✅ تم إضافة ملف الدرجات بنجاح."
    )

    return ConversationHandler.END


# ============================================================
# Edit Grade
# ============================================================

async def edit_grade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    if not await can_manage_grades(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    file_id = int(parts[1])
    stage_id = int(parts[2])

    response = (
        supabase
        .table("grade_files")
        .select(
            "id, name, description"
        )
        .eq("id", file_id)
        .eq("stage_id", stage_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )

    files = response.data or []

    if not files:
        await query.answer(
            "❌ الملف غير موجود.",
            show_alert=True,
        )
        return ConversationHandler.END

    grade_file = files[0]

    context.user_data[
        "admin_grade_file_id"
    ] = file_id

    context.user_data[
        "admin_grade_stage_id"
    ] = stage_id

    await query.answer()

    await query.message.reply_text(
        "✏️ تعديل ملف الدرجات\n\n"
        f"الاسم الحالي:\n"
        f"{grade_file['name']}\n\n"
        "أرسل الاسم الجديد:"
    )

    return EDIT_GRADE_NAME


async def edit_grade_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return EDIT_GRADE_NAME

    name = normalize_text(
        update.message.text or ""
    )

    if not name:
        await update.message.reply_text(
            "❌ الاسم لا يمكن أن يكون فارغاً."
        )
        return EDIT_GRADE_NAME

    context.user_data[
        "admin_grade_name"
    ] = name

    await update.message.reply_text(
        "📝 أرسل الوصف الجديد.\n\n"
        "إذا لا يوجد وصف أرسل: -"
    )

    return EDIT_GRADE_DESCRIPTION


async def edit_grade_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return EDIT_GRADE_DESCRIPTION

    description = normalize_description(
        update.message.text or ""
    )

    file_id = context.user_data.get(
        "admin_grade_file_id"
    )

    stage_id = context.user_data.get(
        "admin_grade_stage_id"
    )

    name = context.user_data.get(
        "admin_grade_name"
    )

    if not file_id or not stage_id or not name:
        clear_grade_conversation(context)

        await update.message.reply_text(
            "❌ انتهت جلسة التعديل."
        )

        return ConversationHandler.END

    try:
        (
            supabase
            .table("grade_files")
            .update({
                "name": name,
                "description": description,
                "updated_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            })
            .eq("id", file_id)
            .eq("stage_id", stage_id)
            .execute()
        )

    except Exception as exc:
        print(
            "EDIT GRADE ERROR:",
            type(exc).__name__,
            exc,
        )

        await update.message.reply_text(
            "❌ حدث خطأ أثناء تعديل الملف."
        )

        clear_grade_conversation(context)

        return ConversationHandler.END

    clear_grade_conversation(context)

    await update.message.reply_text(
        "✅ تم تعديل بيانات الملف بنجاح."
    )

    return ConversationHandler.END


# ============================================================
# Replace File
# ============================================================

async def replace_grade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    if not await can_manage_grades(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    file_id = int(parts[1])
    stage_id = int(parts[2])

    context.user_data[
        "admin_grade_file_id"
    ] = file_id

    context.user_data[
        "admin_grade_stage_id"
    ] = stage_id

    await query.answer()

    await query.message.reply_text(
        "🔄 استبدال ملف الدرجات\n\n"
        "أرسل الملف الجديد:"
    )

    return REPLACE_GRADE_UPLOAD


async def replace_grade_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return REPLACE_GRADE_UPLOAD

    (
        file_type,
        telegram_file_id,
        file_size,
    ) = extract_telegram_file(
        update.message
    )

    if not telegram_file_id:
        await update.message.reply_text(
            "❌ لم أتعرف على الملف.\n"
            "أرسل الملف الجديد مرة أخرى."
        )
        return REPLACE_GRADE_UPLOAD

    file_id = context.user_data.get(
        "admin_grade_file_id"
    )

    stage_id = context.user_data.get(
        "admin_grade_stage_id"
    )

    if not file_id or not stage_id:
        clear_grade_conversation(context)

        await update.message.reply_text(
            "❌ انتهت جلسة الاستبدال."
        )

        return ConversationHandler.END

    try:
        (
            supabase
            .table("grade_files")
            .update({
                "telegram_file_id": telegram_file_id,
                "file_type": file_type,
                "file_size": file_size,
                "updated_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            })
            .eq("id", file_id)
            .eq("stage_id", stage_id)
            .execute()
        )

    except Exception as exc:
        print(
            "REPLACE GRADE ERROR:",
            type(exc).__name__,
            exc,
        )

        await update.message.reply_text(
            "❌ حدث خطأ أثناء استبدال الملف."
        )

        clear_grade_conversation(context)

        return ConversationHandler.END

    clear_grade_conversation(context)

    await update.message.reply_text(
        "✅ تم استبدال ملف الدرجات بنجاح."
    )

    return ConversationHandler.END


# ============================================================
# Enable / Disable
# ============================================================

async def disable_grade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await toggle_grade(
        update,
        context,
        False,
    )


async def enable_grade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await toggle_grade(
        update,
        context,
        True,
    )


async def toggle_grade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    active: bool,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await can_manage_grades(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    file_id = int(parts[1])
    stage_id = int(parts[2])

    try:
        (
            supabase
            .table("grade_files")
            .update({
                "is_active": active,
                "updated_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            })
            .eq("id", file_id)
            .eq("stage_id", stage_id)
            .is_("deleted_at", "null")
            .execute()
        )

    except Exception as exc:
        print(
            "TOGGLE GRADE ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ تعذر تغيير حالة الملف.",
            show_alert=True,
        )
        return

    await query.answer(
        "✅ تم تحديث حالة الملف."
    )

    await manage_grade(
        update,
        context,
    )


# ============================================================
# Delete
# ============================================================

async def delete_grade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await can_manage_grades(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    file_id = int(parts[1])
    stage_id = int(parts[2])

    await query.answer()

    await query.edit_message_text(
        "⚠️ تأكيد حذف ملف الدرجات\n\n"
        "هل أنت متأكد من حذف هذا الملف؟\n\n"
        "ℹ️ سيتم إخفاؤه عن الطلاب "
        "ولن يتم حذفه نهائياً من قاعدة البيانات.",
        reply_markup=delete_grade_keyboard(
            file_id,
            stage_id,
        ),
    )


async def confirm_delete_grade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await can_manage_grades(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    file_id = int(parts[1])
    stage_id = int(parts[2])

    now = datetime.now(
        timezone.utc
    ).isoformat()

    try:
        (
            supabase
            .table("grade_files")
            .update({
                "deleted_at": now,
                "is_active": False,
                "updated_at": now,
            })
            .eq("id", file_id)
            .eq("stage_id", stage_id)
            .is_("deleted_at", "null")
            .execute()
        )

    except Exception as exc:
        print(
            "DELETE GRADE ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ تعذر حذف الملف.",
            show_alert=True,
        )
        return

    await query.answer(
        "✅ تم حذف الملف."
    )

    await show_grade_list(
        update,
        context,
        stage_id,
    )


# ============================================================
# Conversation Handler
# ============================================================

def grade_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                add_grade,
                pattern=r"^add_grade:",
            ),
            CallbackQueryHandler(
                edit_grade,
                pattern=r"^edit_grade:",
            ),
            CallbackQueryHandler(
                replace_grade,
                pattern=r"^replace_grade:",
            ),
        ],
        states={
            ADD_GRADE_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    add_grade_name,
                )
            ],
            ADD_GRADE_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    add_grade_description,
                )
            ],
            ADD_GRADE_UPLOAD: [
                MessageHandler(
                    filters.Document.ALL
                    | filters.PHOTO
                    | filters.VIDEO
                    | filters.AUDIO,
                    add_grade_upload,
                )
            ],
            EDIT_GRADE_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    edit_grade_name,
                )
            ],
            EDIT_GRADE_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    edit_grade_description,
                )
            ],
            REPLACE_GRADE_UPLOAD: [
                MessageHandler(
                    filters.Document.ALL
                    | filters.PHOTO
                    | filters.VIDEO
                    | filters.AUDIO,
                    replace_grade_upload,
                )
            ],
        },
        fallbacks=[],
        per_user=True,
        per_chat=True,
    )
