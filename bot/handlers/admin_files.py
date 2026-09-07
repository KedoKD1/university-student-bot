from datetime import datetime, timezone

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.database.client import supabase
from bot.handlers.admin import is_admin


# =========================
# Conversation States
# =========================

ADD_FILE_NAME, ADD_FILE_DESCRIPTION, ADD_FILE_ORDER, ADD_FILE_UPLOAD = range(4)

EDIT_FILE_NAME, EDIT_FILE_DESCRIPTION, EDIT_FILE_ORDER = range(4, 7)


# =========================
# Constants
# =========================

FILE_TYPES = {
    "document": "📄 مستند",
    "photo": "🖼️ صورة",
    "video": "🎥 فيديو",
    "audio": "🎵 صوت",
}

VALID_SECTION_TYPES = {
    "theoretical",
    "practical",
}

# دعم أزرار قديمة تم إنشاؤها قبل توحيد القيمة
SECTION_TYPE_ALIASES = {
    "theory": "theoretical",
    "theoretical": "theoretical",
    "practical": "practical",
}


# =========================
# Helpers
# =========================

def clear_file_conversation(context):
    keys = [
        "admin_file_stage_id",
        "admin_file_subject_id",
        "admin_file_section_type",
        "admin_file_id",
        "admin_file_name",
        "admin_file_description",
        "admin_file_order",
    ]

    for key in keys:
        context.user_data.pop(key, None)


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


def normalize_section_type(section_type):
    return SECTION_TYPE_ALIASES.get(section_type)


def section_name(section_type):
    section_type = normalize_section_type(section_type)

    if section_type == "theoretical":
        return "📖 النظري"

    if section_type == "practical":
        return "🧪 العملي"

    return "❓ غير محدد"


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


# =========================
# Keyboards
# =========================

def section_keyboard(stage_id, subject_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="📖 النظري",
                callback_data=(
                    f"admin_file_section:theoretical:"
                    f"{subject_id}:{stage_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="🧪 العملي",
                callback_data=(
                    f"admin_file_section:practical:"
                    f"{subject_id}:{stage_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ رجوع للمواد",
                callback_data=(
                    f"admin_file_subjects:{stage_id}"
                ),
            )
        ],
    ])


def file_list_keyboard(
    files,
    stage_id,
    subject_id,
    section_type,
):
    section_type = normalize_section_type(section_type)

    keyboard = []

    for file in files:
        status = "🟢" if file["is_active"] else "🔴"

        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {file['name']}",
                callback_data=(
                    f"manage_file:{file['id']}:"
                    f"{subject_id}:{section_type}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="➕ إضافة ملف",
            callback_data=(
                f"add_file:{stage_id}:{subject_id}:"
                f"{section_type}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للأقسام",
            callback_data=(
                f"admin_file_sections:"
                f"{stage_id}:{subject_id}"
            ),
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def file_manage_keyboard(
    file_id,
    stage_id,
    subject_id,
    section_type,
    is_active,
):
    section_type = normalize_section_type(section_type)

    if is_active:
        toggle_text = "🔴 تعطيل الملف"
        toggle_callback = (
            f"disable_file:{file_id}:{stage_id}:"
            f"{subject_id}:{section_type}"
        )
    else:
        toggle_text = "🟢 تفعيل الملف"
        toggle_callback = (
            f"enable_file:{file_id}:{stage_id}:"
            f"{subject_id}:{section_type}"
        )

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="✏️ تعديل البيانات",
                callback_data=(
                    f"edit_file:{file_id}:{stage_id}:"
                    f"{subject_id}:{section_type}"
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
                    f"delete_file:{file_id}:{stage_id}:"
                    f"{subject_id}:{section_type}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ رجوع للملفات",
                callback_data=(
                    f"admin_file_list:{stage_id}:"
                    f"{subject_id}:{section_type}"
                ),
            )
        ],
    ])


def delete_confirm_keyboard(
    file_id,
    stage_id,
    subject_id,
    section_type,
):
    section_type = normalize_section_type(section_type)

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="🗑️ نعم، احذف",
                callback_data=(
                    f"confirm_delete_file:{file_id}:"
                    f"{stage_id}:{subject_id}:{section_type}"
                ),
            ),
            InlineKeyboardButton(
                text="❌ إلغاء",
                callback_data=(
                    f"manage_file:{file_id}:"
                    f"{subject_id}:{section_type}"
                ),
            ),
        ],
    ])


def after_save_keyboard(
    stage_id,
    subject_id,
    section_type,
):
    section_type = normalize_section_type(section_type)

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="⬅️ العودة إلى الملفات",
                callback_data=(
                    f"admin_file_list:{stage_id}:"
                    f"{subject_id}:{section_type}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="🛠️ لوحة الإدارة",
                callback_data="admin_back",
            )
        ],
    ])


# =========================
# Database Helpers
# =========================

async def get_subjects(stage_id):
    response = (
        supabase
        .table("subjects")
        .select(
            "id, name, description, sort_order, is_active"
        )
        .eq("stage_id", stage_id)
        .order("sort_order")
        .execute()
    )

    return response.data or []


async def get_files(
    subject_id,
    section_type,
    include_inactive=True,
):
    section_type = normalize_section_type(section_type)

    if section_type not in VALID_SECTION_TYPES:
        return []

    query = (
        supabase
        .table("files")
        .select("*")
        .eq("subject_id", subject_id)
        .eq("section_type", section_type)
        .is_("deleted_at", "null")
        .order("sort_order")
    )

    if not include_inactive:
        query = query.eq("is_active", True)

    response = query.execute()

    return response.data or []


async def get_file(
    file_id,
    subject_id=None,
):
    query = (
        supabase
        .table("files")
        .select("*")
        .eq("id", file_id)
        .is_("deleted_at", "null")
    )

    if subject_id is not None:
        query = query.eq(
            "subject_id",
            subject_id,
        )

    response = query.limit(1).execute()

    files = response.data or []

    if not files:
        return None

    return files[0]


# =========================
# Admin Files Main
# =========================

async def admin_files(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    await query.answer()

    response = (
        supabase
        .table("stages")
        .select("id, stage_number, is_active")
        .order("stage_number")
        .execute()
    )

    stages = response.data or []

    if not stages:
        await query.edit_message_text(
            "❌ لا توجد مراحل في قاعدة البيانات."
        )
        return

    keyboard = []

    for stage in stages:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📚 المرحلة {stage['stage_number']}",
                callback_data=(
                    f"admin_file_stage:{stage['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للوحة الإدارة",
            callback_data="admin_back",
        )
    ])

    await query.edit_message_text(
        "📄 إدارة الملفات\n\n"
        "اختر المرحلة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =========================
# Stage → Subjects
# =========================

async def admin_file_stage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
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

    stage_id = parts[1]

    await query.answer()

    subjects = await get_subjects(stage_id)

    keyboard = []

    for subject in subjects:
        status = "🟢" if subject["is_active"] else "🔴"

        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {subject['name']}",
                callback_data=(
                    f"admin_file_subject:"
                    f"{subject['id']}:{stage_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للمراحل",
            callback_data="admin_files",
        )
    ])

    if not subjects:
        await query.edit_message_text(
            "📄 إدارة الملفات\n\n"
            "لا توجد مواد مضافة لهذه المرحلة.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    await query.edit_message_text(
        "📄 إدارة الملفات\n\n"
        "اختر المادة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =========================
# Subject → Sections
# =========================

async def admin_file_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
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

    subject_id = parts[1]
    stage_id = parts[2]

    await query.answer()

    response = (
        supabase
        .table("subjects")
        .select("id, name, is_active")
        .eq("id", subject_id)
        .eq("stage_id", stage_id)
        .limit(1)
        .execute()
    )

    subjects = response.data or []

    if not subjects:
        await query.edit_message_text(
            "❌ المادة غير موجودة."
        )
        return

    subject = subjects[0]

    await query.edit_message_text(
        f"📄 إدارة ملفات\n"
        f"📘 {subject['name']}\n\n"
        "اختر القسم:",
        reply_markup=section_keyboard(
            stage_id,
            subject_id,
        ),
    )


# =========================
# Sections → Subjects
# =========================

async def admin_file_subjects(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
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

    stage_id = parts[1]

    await query.answer()

    subjects = await get_subjects(stage_id)

    keyboard = []

    for subject in subjects:
        status = "🟢" if subject["is_active"] else "🔴"

        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {subject['name']}",
                callback_data=(
                    f"admin_file_subject:"
                    f"{subject['id']}:{stage_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للمراحل",
            callback_data="admin_files",
        )
    ])

    if not subjects:
        await query.edit_message_text(
            "📄 إدارة الملفات\n\n"
            "لا توجد مواد مضافة لهذه المرحلة.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    await query.edit_message_text(
        "📄 إدارة الملفات\n\n"
        "اختر المادة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =========================
# Subject → Sections
# =========================

async def admin_file_sections(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
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

    stage_id = parts[1]
    subject_id = parts[2]

    await query.answer()

    response = (
        supabase
        .table("subjects")
        .select("id, name")
        .eq("id", subject_id)
        .eq("stage_id", stage_id)
        .limit(1)
        .execute()
    )

    subjects = response.data or []

    if not subjects:
        await query.edit_message_text(
            "❌ المادة غير موجودة."
        )
        return

    subject = subjects[0]

    await query.edit_message_text(
        f"📄 إدارة ملفات\n"
        f"📘 {subject['name']}\n\n"
        "اختر القسم:",
        reply_markup=section_keyboard(
            stage_id,
            subject_id,
        ),
    )


# =========================
# Section → File List
# =========================

async def admin_file_section(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 4:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    section_type = normalize_section_type(parts[1])
    subject_id = parts[2]
    stage_id = parts[3]

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True,
        )
        return

    await query.answer()

    files = await get_files(
        subject_id,
        section_type,
        include_inactive=True,
    )

    response = (
        supabase
        .table("subjects")
        .select("name")
        .eq("id", subject_id)
        .eq("stage_id", stage_id)
        .limit(1)
        .execute()
    )

    subjects = response.data or []

    if not subjects:
        await query.edit_message_text(
            "❌ المادة غير موجودة."
        )
        return

    subject_name = subjects[0]["name"]

    if not files:
        await query.edit_message_text(
            f"📄 إدارة الملفات\n"
            f"📘 {subject_name}\n"
            f"{section_name(section_type)}\n\n"
            "لا توجد ملفات مضافة لهذا القسم.",
            reply_markup=file_list_keyboard(
                [],
                stage_id,
                subject_id,
                section_type,
            ),
        )
        return

    await query.edit_message_text(
        f"📄 إدارة الملفات\n"
        f"📘 {subject_name}\n"
        f"{section_name(section_type)}\n\n"
        "اختر الملف:",
        reply_markup=file_list_keyboard(
            files,
            stage_id,
            subject_id,
            section_type,
        ),
    )


# =========================
# File List
# =========================

async def admin_file_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 4:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    stage_id = parts[1]
    subject_id = parts[2]
    section_type = normalize_section_type(parts[3])

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True,
        )
        return

    await query.answer()

    files = await get_files(
        subject_id,
        section_type,
        include_inactive=True,
    )

    response = (
        supabase
        .table("subjects")
        .select("name")
        .eq("id", subject_id)
        .eq("stage_id", stage_id)
        .limit(1)
        .execute()
    )

    subjects = response.data or []

    if not subjects:
        await query.edit_message_text(
            "❌ المادة غير موجودة."
        )
        return

    subject_name = subjects[0]["name"]

    await query.edit_message_text(
        f"📄 إدارة الملفات\n"
        f"📘 {subject_name}\n"
        f"{section_name(section_type)}\n\n"
        "اختر الملف:",
        reply_markup=file_list_keyboard(
            files,
            stage_id,
            subject_id,
            section_type,
        ),
    )


# =========================
# Manage File
# =========================

async def manage_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 4:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    file_id = parts[1]
    subject_id = parts[2]
    section_type = normalize_section_type(parts[3])

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True,
        )
        return

    file = await get_file(
        file_id,
        subject_id,
    )

    if not file:
        await query.answer(
            "❌ الملف غير موجود.",
            show_alert=True,
        )
        return

    await query.answer()

    stage_response = (
        supabase
        .table("subjects")
        .select("stage_id, name")
        .eq("id", subject_id)
        .limit(1)
        .execute()
    )

    subjects = stage_response.data or []

    if not subjects:
        await query.edit_message_text(
            "❌ المادة غير موجودة."
        )
        return

    stage_id = subjects[0]["stage_id"]
    subject_name = subjects[0]["name"]

    file_type = FILE_TYPES.get(
        file.get("file_type"),
        "📎 ملف",
    )

    status = (
        "🟢 فعال"
        if file.get("is_active")
        else "🔴 معطل"
    )

    description = (
        file.get("description")
        or "لا يوجد وصف."
    )

    file_size = file.get("file_size")

    if file_size:
        size_text = f"{file_size:,} بايت"
    else:
        size_text = "غير معروف"

    await query.edit_message_text(
        f"📄 إدارة الملف\n\n"
        f"📘 المادة: {subject_name}\n"
        f"{section_name(section_type)}\n\n"
        f"📌 الاسم: {file['name']}\n"
        f"📝 الوصف: {description}\n"
        f"📎 النوع: {file_type}\n"
        f"📦 الحجم: {size_text}\n"
        f"🔢 الترتيب: {file.get('sort_order', 0)}\n"
        f"📊 الحالة: {status}\n\n"
        "اختر الإجراء:",
        reply_markup=file_manage_keyboard(
            file_id,
            stage_id,
            subject_id,
            section_type,
            file.get("is_active", False),
        ),
    )


# =========================
# Add File
# =========================

async def start_add_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    parts = query.data.split(":")

    if len(parts) != 4:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    stage_id = parts[1]
    subject_id = parts[2]
    section_type = normalize_section_type(parts[3])

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    clear_file_conversation(context)

    context.user_data["admin_file_stage_id"] = stage_id
    context.user_data["admin_file_subject_id"] = subject_id
    context.user_data["admin_file_section_type"] = section_type

    await query.answer()

    await query.message.reply_text(
        "➕ إضافة ملف جديد\n\n"
        f"{section_name(section_type)}\n\n"
        "أرسل اسم الملف:"
    )

    return ADD_FILE_NAME


async def receive_add_file_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if message is None or message.text is None:
        return ADD_FILE_NAME

    name = normalize_text(message.text)

    if not name:
        await message.reply_text(
            "❌ اسم الملف لا يمكن أن يكون فارغاً.\n\n"
            "أرسل اسم الملف مرة أخرى:"
        )
        return ADD_FILE_NAME

    context.user_data["admin_file_name"] = name

    await message.reply_text(
        "📝 أرسل وصف الملف.\n\n"
        "إذا لا يوجد وصف، أرسل:\n"
        "`-`",
        parse_mode="Markdown",
    )

    return ADD_FILE_DESCRIPTION


async def receive_add_file_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if message is None or message.text is None:
        return ADD_FILE_DESCRIPTION

    description = normalize_description(
        message.text
    )

    context.user_data[
        "admin_file_description"
    ] = description

    await message.reply_text(
        "🔢 أرسل ترتيب الملف.\n\n"
        "مثال:\n"
        "`1`",
        parse_mode="Markdown",
    )

    return ADD_FILE_ORDER


async def receive_add_file_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if message is None or message.text is None:
        return ADD_FILE_ORDER

    text = normalize_text(message.text)

    try:
        order = int(text)
    except ValueError:
        await message.reply_text(
            "❌ الترتيب يجب أن يكون رقماً صحيحاً.\n\n"
            "أرسل الترتيب مرة أخرى:"
        )
        return ADD_FILE_ORDER

    if order < 0:
        await message.reply_text(
            "❌ الترتيب لا يمكن أن يكون سالباً.\n\n"
            "أرسل الترتيب مرة أخرى:"
        )
        return ADD_FILE_ORDER

    context.user_data["admin_file_order"] = order

    await message.reply_text(
        "📎 الآن أرسل الملف نفسه.\n\n"
        "المسموح:\n"
        "📄 مستند\n"
        "🖼️ صورة\n"
        "🎥 فيديو\n"
        "🎵 صوت"
    )

    return ADD_FILE_UPLOAD


async def receive_add_file_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if message is None:
        return ADD_FILE_UPLOAD

    file_type, telegram_file_id, file_size = (
        extract_telegram_file(message)
    )

    if not telegram_file_id:
        await message.reply_text(
            "❌ لم أتعرف على الملف.\n\n"
            "أرسل مستند أو صورة أو فيديو أو ملف صوتي."
        )
        return ADD_FILE_UPLOAD

    stage_id = context.user_data.get(
        "admin_file_stage_id"
    )
    subject_id = context.user_data.get(
        "admin_file_subject_id"
    )
    section_type = normalize_section_type(
        context.user_data.get(
            "admin_file_section_type"
        )
    )
    name = context.user_data.get(
        "admin_file_name"
    )
    description = context.user_data.get(
        "admin_file_description"
    )
    sort_order = context.user_data.get(
        "admin_file_order"
    )

    if not stage_id or not subject_id:
        await message.reply_text(
            "❌ انتهت جلسة إضافة الملف.\n\n"
            "ابدأ الإضافة من جديد."
        )
        clear_file_conversation(context)
        return ConversationHandler.END

    if section_type not in VALID_SECTION_TYPES:
        await message.reply_text(
            "❌ نوع القسم غير صالح."
        )
        clear_file_conversation(context)
        return ConversationHandler.END

    if not name:
        await message.reply_text(
            "❌ اسم الملف مفقود."
        )
        clear_file_conversation(context)
        return ConversationHandler.END

    if sort_order is None:
        await message.reply_text(
            "❌ ترتيب الملف مفقود."
        )
        clear_file_conversation(context)
        return ConversationHandler.END

    try:
        response = (
            supabase
            .table("files")
            .insert({
                "subject_id": subject_id,
                "section_type": section_type,
                "name": name,
                "description": description,
                "telegram_file_id": telegram_file_id,
                "file_type": file_type,
                "file_size": file_size,
                "sort_order": sort_order,
                "is_active": True,
            })
            .execute()
        )

        if not response.data:
            raise RuntimeError(
                "Supabase did not return a created file record."
            )

    except Exception as exc:
        error_text = str(exc)

        await message.reply_text(
            "❌ حدث خطأ أثناء حفظ الملف.\n\n"
            "🔎 تفاصيل الخطأ:\n"
            f"{error_text}\n\n"
            "لم يتم إنشاء سجل الملف."
        )

        clear_file_conversation(context)
        return ConversationHandler.END

    await message.reply_text(
        "✅ تم حفظ الملف بنجاح.\n\n"
        f"📌 الاسم: {name}\n"
        f"{section_name(section_type)}\n"
        f"📎 النوع: {FILE_TYPES.get(file_type, '📎 ملف')}\n"
        f"🔢 الترتيب: {sort_order}",
        reply_markup=after_save_keyboard(
            stage_id,
            subject_id,
            section_type,
        ),
    )

    clear_file_conversation(context)

    return ConversationHandler.END


# =========================
# Edit File
# =========================

async def start_edit_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    parts = query.data.split(":")

    if len(parts) != 5:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    file_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]
    section_type = normalize_section_type(parts[4])

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    file = await get_file(
        file_id,
        subject_id,
    )

    if not file:
        await query.answer(
            "❌ الملف غير موجود.",
            show_alert=True,
        )
        return ConversationHandler.END

    clear_file_conversation(context)

    context.user_data["admin_file_id"] = file_id
    context.user_data["admin_file_stage_id"] = stage_id
    context.user_data["admin_file_subject_id"] = subject_id
    context.user_data["admin_file_section_type"] = section_type

    context.user_data["admin_file_name"] = file["name"]
    context.user_data["admin_file_description"] = file.get(
        "description"
    )
    context.user_data["admin_file_order"] = file.get(
        "sort_order",
        0,
    )

    await query.answer()

    await query.message.reply_text(
        "✏️ تعديل بيانات الملف\n\n"
        f"الاسم الحالي:\n{file['name']}\n\n"
        "أرسل الاسم الجديد:"
    )

    return EDIT_FILE_NAME


async def receive_edit_file_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if message is None or message.text is None:
        return EDIT_FILE_NAME

    name = normalize_text(message.text)

    if not name:
        await message.reply_text(
            "❌ الاسم لا يمكن أن يكون فارغاً.\n\n"
            "أرسل الاسم الجديد:"
        )
        return EDIT_FILE_NAME

    context.user_data["admin_file_name"] = name

    current_description = context.user_data.get(
        "admin_file_description"
    )

    description_text = (
        current_description
        if current_description
        else "لا يوجد وصف"
    )

    await message.reply_text(
        "📝 الوصف الحالي:\n"
        f"{description_text}\n\n"
        "أرسل الوصف الجديد.\n"
        "إذا لا يوجد وصف، أرسل:\n"
        "`-`",
        parse_mode="Markdown",
    )

    return EDIT_FILE_DESCRIPTION


async def receive_edit_file_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if message is None or message.text is None:
        return EDIT_FILE_DESCRIPTION

    description = normalize_description(
        message.text
    )

    context.user_data[
        "admin_file_description"
    ] = description

    current_order = context.user_data.get(
        "admin_file_order",
        0,
    )

    await message.reply_text(
        "🔢 الترتيب الحالي:\n"
        f"{current_order}\n\n"
        "أرسل الترتيب الجديد:",
    )

    return EDIT_FILE_ORDER


async def receive_edit_file_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if message is None or message.text is None:
        return EDIT_FILE_ORDER

    text = normalize_text(message.text)

    try:
        order = int(text)
    except ValueError:
        await message.reply_text(
            "❌ الترتيب يجب أن يكون رقماً صحيحاً.\n\n"
            "أرسل الترتيب الجديد:"
        )
        return EDIT_FILE_ORDER

    if order < 0:
        await message.reply_text(
            "❌ الترتيب لا يمكن أن يكون سالباً.\n\n"
            "أرسل الترتيب الجديد:"
        )
        return EDIT_FILE_ORDER

    file_id = context.user_data.get(
        "admin_file_id"
    )
    stage_id = context.user_data.get(
        "admin_file_stage_id"
    )
    subject_id = context.user_data.get(
        "admin_file_subject_id"
    )
    section_type = normalize_section_type(
        context.user_data.get(
            "admin_file_section_type"
        )
    )
    name = context.user_data.get(
        "admin_file_name"
    )
    description = context.user_data.get(
        "admin_file_description"
    )

    if not file_id or not subject_id:
        await message.reply_text(
            "❌ انتهت جلسة التعديل.\n\n"
            "ابدأ التعديل من جديد."
        )
        clear_file_conversation(context)
        return ConversationHandler.END

    if section_type not in VALID_SECTION_TYPES:
        await message.reply_text(
            "❌ نوع القسم غير صالح."
        )
        clear_file_conversation(context)
        return ConversationHandler.END

    try:
        response = (
            supabase
            .table("files")
            .update({
                "name": name,
                "description": description,
                "sort_order": order,
            })
            .eq("id", file_id)
            .eq("subject_id", subject_id)
            .is_("deleted_at", "null")
            .execute()
        )

        if not response.data:
            raise RuntimeError(
                "لم يتم تحديث سجل الملف."
            )

    except Exception as exc:
        await message.reply_text(
            "❌ حدث خطأ أثناء تعديل الملف.\n\n"
            "🔎 تفاصيل الخطأ:\n"
            f"{str(exc)}"
        )

        clear_file_conversation(context)
        return ConversationHandler.END

    await message.reply_text(
        "✅ تم تعديل الملف بنجاح.\n\n"
        f"📌 الاسم: {name}\n"
        f"{section_name(section_type)}\n"
        f"🔢 الترتيب: {order}",
        reply_markup=after_save_keyboard(
            stage_id,
            subject_id,
            section_type,
        ),
    )

    clear_file_conversation(context)

    return ConversationHandler.END


# =========================
# Enable / Disable
# =========================

async def set_file_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    is_active: bool,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 5:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    file_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]
    section_type = normalize_section_type(parts[4])

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True,
        )
        return

    file = await get_file(
        file_id,
        subject_id,
    )

    if not file:
        await query.answer(
            "❌ الملف غير موجود.",
            show_alert=True,
        )
        return

    try:
        response = (
            supabase
            .table("files")
            .update({
                "is_active": is_active,
            })
            .eq("id", file_id)
            .eq("subject_id", subject_id)
            .is_("deleted_at", "null")
            .execute()
        )

        if not response.data:
            raise RuntimeError(
                "لم يتم تحديث حالة الملف."
            )

    except Exception as exc:
        await query.answer(
            f"❌ فشل تحديث حالة الملف: {str(exc)}",
            show_alert=True,
        )
        return

    await query.answer()

    status_text = (
        "🟢 تم تفعيل الملف."
        if is_active
        else "🔴 تم تعطيل الملف."
    )

    await query.edit_message_text(
        f"{status_text}\n\n"
        f"📌 {file['name']}\n"
        f"{section_name(section_type)}",
        reply_markup=after_save_keyboard(
            stage_id,
            subject_id,
            section_type,
        ),
    )


async def disable_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await set_file_status(
        update,
        context,
        False,
    )


async def enable_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await set_file_status(
        update,
        context,
        True,
    )


# =========================
# Delete File
# =========================

async def delete_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 5:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    file_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]
    section_type = normalize_section_type(parts[4])

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True,
        )
        return

    file = await get_file(
        file_id,
        subject_id,
    )

    if not file:
        await query.answer(
            "❌ الملف غير موجود.",
            show_alert=True,
        )
        return

    await query.answer()

    await query.edit_message_text(
        "⚠️ تأكيد حذف الملف\n\n"
        f"📌 {file['name']}\n"
        f"{section_name(section_type)}\n\n"
        "الحذف هنا سيكون حذفاً من النظام، "
        "ويمكن لاحقاً تنظيف السجلات المحذوفة نهائياً.\n\n"
        "هل أنت متأكد؟",
        reply_markup=delete_confirm_keyboard(
            file_id,
            stage_id,
            subject_id,
            section_type,
        ),
    )


async def confirm_delete_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 5:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    file_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]
    section_type = normalize_section_type(parts[4])

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True,
        )
        return

    file = await get_file(
        file_id,
        subject_id,
    )

    if not file:
        await query.answer(
            "❌ الملف غير موجود أو تم حذفه مسبقاً.",
            show_alert=True,
        )
        return

    deleted_at = datetime.now(
        timezone.utc
    ).isoformat()

    try:
        response = (
            supabase
            .table("files")
            .update({
                "is_active": False,
                "deleted_at": deleted_at,
            })
            .eq("id", file_id)
            .eq("subject_id", subject_id)
            .is_("deleted_at", "null")
            .execute()
        )

        if not response.data:
            raise RuntimeError(
                "لم يتم حذف سجل الملف."
            )

    except Exception as exc:
        await query.answer(
            "❌ فشل حذف الملف.",
            show_alert=True,
        )

        await query.edit_message_text(
            "❌ حدث خطأ أثناء حذف الملف.\n\n"
            "🔎 تفاصيل الخطأ:\n"
            f"{str(exc)}"
        )
        return

    await query.answer()

    await query.edit_message_text(
        "✅ تم حذف الملف بنجاح.\n\n"
        f"📌 {file['name']}\n"
        f"{section_name(section_type)}",
        reply_markup=after_save_keyboard(
            stage_id,
            subject_id,
            section_type,
        ),
    )


# =========================
# Cancel
# =========================

async def cancel_file_operation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    clear_file_conversation(context)

    if update.message:
        await update.message.reply_text(
            "❌ تم إلغاء العملية."
        )

    return ConversationHandler.END


# =========================
# Conversation Handler
# =========================

def file_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                start_add_file,
                pattern=r"^add_file:",
            ),
            CallbackQueryHandler(
                start_edit_file,
                pattern=r"^edit_file:",
            ),
        ],
        states={
            ADD_FILE_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_add_file_name,
                ),
            ],
            ADD_FILE_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_add_file_description,
                ),
            ],
            ADD_FILE_ORDER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_add_file_order,
                ),
            ],
            ADD_FILE_UPLOAD: [
                MessageHandler(
                    filters.Document.ALL
                    | filters.PHOTO
                    | filters.VIDEO
                    | filters.AUDIO,
                    receive_add_file_upload,
                ),
            ],
            EDIT_FILE_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_edit_file_name,
                ),
            ],
            EDIT_FILE_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_edit_file_description,
                ),
            ],
            EDIT_FILE_ORDER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_edit_file_order,
                ),
            ],
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_file_operation,
            ),
        ],
        allow_reentry=True,
    )


# =========================
# Back to Admin Files
# =========================

async def back_to_admin_files(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    await query.answer()

    response = (
        supabase
        .table("stages")
        .select("id, stage_number, is_active")
        .order("stage_number")
        .execute()
    )

    stages = response.data or []

    keyboard = []

    for stage in stages:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📚 المرحلة {stage['stage_number']}",
                callback_data=(
                    f"admin_file_stage:{stage['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للوحة الإدارة",
            callback_data="admin_back",
        )
    ])

    await query.edit_message_text(
        "📄 إدارة الملفات\n\n"
        "اختر المرحلة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
