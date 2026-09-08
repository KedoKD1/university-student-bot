from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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

ADD_DRAWING_NAME = 0
ADD_DRAWING_DESCRIPTION = 1
ADD_DRAWING_ORDER = 2
ADD_DRAWING_UPLOAD = 3

EDIT_DRAWING_NAME = 4
EDIT_DRAWING_DESCRIPTION = 5
EDIT_DRAWING_ORDER = 6


# =========================
# Constants
# =========================

VALID_SECTION_TYPES = {
    "theoretical",
    "practical",
}


SECTION_TYPE_ALIASES = {
    "theory": "theoretical",
    "theoretical": "theoretical",
    "practical": "practical",
}


# =========================
# Helpers
# =========================

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


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clear_drawing_conversation(context):
    keys = [
        "admin_drawing_stage_id",
        "admin_drawing_subject_id",
        "admin_drawing_section_type",
        "admin_drawing_id",
        "admin_drawing_name",
        "admin_drawing_description",
        "admin_drawing_order",
    ]

    for key in keys:
        context.user_data.pop(key, None)


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
                    f"admin_drawing_section:"
                    f"theoretical:{subject_id}:{stage_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="🧪 العملي",
                callback_data=(
                    f"admin_drawing_section:"
                    f"practical:{subject_id}:{stage_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ رجوع للمواد",
                callback_data=(
                    f"admin_drawing_subjects:"
                    f"{stage_id}"
                ),
            )
        ],
    ])


def drawing_list_keyboard(
    drawings,
    stage_id,
    subject_id,
    section_type,
):
    section_type = normalize_section_type(section_type)

    keyboard = []

    for drawing in drawings:
        status = (
            "🟢"
            if drawing["is_active"]
            else "🔴"
        )

        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {drawing['name']}",
                callback_data=(
                    f"manage_drawing:"
                    f"{drawing['id']}:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"{section_type}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="➕ إضافة رسمة",
            callback_data=(
                f"add_drawing:"
                f"{stage_id}:"
                f"{subject_id}:"
                f"{section_type}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للأقسام",
            callback_data=(
                f"admin_drawing_sections:"
                f"{stage_id}:"
                f"{subject_id}"
            ),
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def drawing_manage_keyboard(
    drawing_id,
    stage_id,
    subject_id,
    section_type,
    is_active,
):
    section_type = normalize_section_type(section_type)

    if is_active:
        toggle_text = "🔴 تعطيل الرسمة"

        toggle_callback = (
            f"disable_drawing:"
            f"{drawing_id}:"
            f"{stage_id}:"
            f"{subject_id}:"
            f"{section_type}"
        )

    else:
        toggle_text = "🟢 تفعيل الرسمة"

        toggle_callback = (
            f"enable_drawing:"
            f"{drawing_id}:"
            f"{stage_id}:"
            f"{subject_id}:"
            f"{section_type}"
        )

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="✏️ تعديل البيانات",
                callback_data=(
                    f"edit_drawing:"
                    f"{drawing_id}:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"{section_type}"
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
                text="🗑️ حذف الرسمة",
                callback_data=(
                    f"delete_drawing:"
                    f"{drawing_id}:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"{section_type}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ رجوع للرسومات",
                callback_data=(
                    f"admin_drawing_list:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"{section_type}"
                ),
            )
        ],
    ])


def delete_confirm_keyboard(
    drawing_id,
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
                    f"confirm_delete_drawing:"
                    f"{drawing_id}:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"{section_type}"
                ),
            ),
            InlineKeyboardButton(
                text="❌ إلغاء",
                callback_data=(
                    f"manage_drawing:"
                    f"{drawing_id}:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"{section_type}"
                ),
            ),
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


async def get_drawings(
    subject_id,
    section_type,
    include_inactive=True,
):
    section_type = normalize_section_type(section_type)

    if section_type not in VALID_SECTION_TYPES:
        return []

    query = (
        supabase
        .table("drawings")
        .select("*")
        .eq("subject_id", subject_id)
        .eq("section_type", section_type)
        .is_("deleted_at", "null")
        .order("sort_order")
    )

    if not include_inactive:
        query = query.eq(
            "is_active",
            True,
        )

    response = query.execute()

    return response.data or []


async def get_drawing(
    drawing_id,
    subject_id=None,
):
    query = (
        supabase
        .table("drawings")
        .select("*")
        .eq("id", drawing_id)
        .is_("deleted_at", "null")
    )

    if subject_id is not None:
        query = query.eq(
            "subject_id",
            subject_id,
        )

    response = (
        query
        .limit(1)
        .execute()
    )

    drawings = response.data or []

    if not drawings:
        return None

    return drawings[0]


# =========================
# Admin Drawings
# =========================

async def admin_drawings(
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
            "❌ لا توجد مراحل في قاعدة البيانات."
        )
        return

    keyboard = []

    for stage in stages:
        status = (
            "🟢"
            if stage["is_active"]
            else "🔴"
        )

        keyboard.append([
            InlineKeyboardButton(
                text=(
                    f"{status} "
                    f"المرحلة {stage['stage_number']}"
                ),
                callback_data=(
                    f"admin_drawing_stage:"
                    f"{stage['id']}"
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
        "🎨 إدارة الرسومات\n\n"
        "اختر المرحلة:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# =========================
# Stage → Subjects
# =========================

async def admin_drawing_stage(
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

    parts = query.data.split(":")

    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    stage_id = parts[1]

    await query.answer()

    subjects = await get_subjects(
        stage_id
    )

    keyboard = []

    for subject in subjects:
        status = (
            "🟢"
            if subject["is_active"]
            else "🔴"
        )

        keyboard.append([
            InlineKeyboardButton(
                text=(
                    f"{status} "
                    f"{subject['name']}"
                ),
                callback_data=(
                    f"admin_drawing_subject:"
                    f"{subject['id']}:"
                    f"{stage_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للمراحل",
            callback_data="admin_drawings",
        )
    ])

    await query.edit_message_text(
        "🎨 إدارة الرسومات\n\n"
        "اختر المادة:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def admin_drawing_subjects(
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

    parts = query.data.split(":")

    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    stage_id = parts[1]

    await query.answer()

    subjects = await get_subjects(
        stage_id
    )

    keyboard = []

    for subject in subjects:
        status = (
            "🟢"
            if subject["is_active"]
            else "🔴"
        )

        keyboard.append([
            InlineKeyboardButton(
                text=(
                    f"{status} "
                    f"{subject['name']}"
                ),
                callback_data=(
                    f"admin_drawing_subject:"
                    f"{subject['id']}:"
                    f"{stage_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للمراحل",
            callback_data="admin_drawings",
        )
    ])

    await query.edit_message_text(
        "🎨 إدارة الرسومات\n\n"
        "اختر المادة:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# =========================
# Subject → Sections
# =========================

async def admin_drawing_subject(
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

    subject_name = subjects[0]["name"]

    await query.edit_message_text(
        "🎨 إدارة الرسومات\n\n"
        f"📘 المادة: {subject_name}\n\n"
        "اختر القسم:",
        reply_markup=section_keyboard(
            stage_id,
            subject_id,
        ),
    )


# =========================
# Sections → Drawings
# =========================

async def admin_drawing_sections(
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

    await query.edit_message_text(
        "🎨 إدارة الرسومات\n\n"
        "اختر القسم:",
        reply_markup=section_keyboard(
            stage_id,
            subject_id,
        ),
    )


async def admin_drawing_section(
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

    parts = query.data.split(":")

    if len(parts) != 4:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    section_type = normalize_section_type(
        parts[1]
    )

    subject_id = parts[2]
    stage_id = parts[3]

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ قسم غير صالح.",
            show_alert=True,
        )
        return

    await query.answer()

    drawings = await get_drawings(
        subject_id,
        section_type,
        include_inactive=True,
    )

    text = (
        "🎨 إدارة الرسومات\n"
        f"{section_name(section_type)}\n\n"
        f"عدد الرسومات: {len(drawings)}\n\n"
        "اختر رسمة أو أضف رسمة جديدة:"
    )

    await query.edit_message_text(
        text,
        reply_markup=drawing_list_keyboard(
            drawings,
            stage_id,
            subject_id,
            section_type,
        ),
    )


async def admin_drawing_list(
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

    parts = query.data.split(":")

    if len(parts) != 4:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    stage_id = parts[1]
    subject_id = parts[2]

    section_type = normalize_section_type(
        parts[3]
    )

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ قسم غير صالح.",
            show_alert=True,
        )
        return

    await query.answer()

    drawings = await get_drawings(
        subject_id,
        section_type,
        include_inactive=True,
    )

    await query.edit_message_text(
        "🎨 إدارة الرسومات\n"
        f"{section_name(section_type)}\n\n"
        f"عدد الرسومات: {len(drawings)}\n\n"
        "اختر رسمة أو أضف رسمة جديدة:",
        reply_markup=drawing_list_keyboard(
            drawings,
            stage_id,
            subject_id,
            section_type,
        ),
    )


# =========================
# Manage Drawing
# =========================

async def manage_drawing(
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

    parts = query.data.split(":")

    if len(parts) != 5:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    drawing_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]

    section_type = normalize_section_type(
        parts[4]
    )

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ قسم غير صالح.",
            show_alert=True,
        )
        return

    drawing = await get_drawing(
        drawing_id,
        subject_id,
    )

    if not drawing:
        await query.answer(
            "❌ الرسمة غير موجودة.",
            show_alert=True,
        )
        return

    await query.answer()

    status = (
        "🟢 مفعّلة"
        if drawing["is_active"]
        else "🔴 معطّلة"
    )

    description = (
        drawing.get("description")
        or "لا يوجد"
    )

    await query.edit_message_text(
        "🎨 إدارة الرسمة\n\n"
        f"📌 الاسم: {drawing['name']}\n"
        f"📝 الوصف: {description}\n"
        f"📂 القسم: {section_name(section_type)}\n"
        f"🔢 الترتيب: {drawing.get('sort_order', 0)}\n"
        f"📊 الحالة: {status}",
        reply_markup=drawing_manage_keyboard(
            drawing_id,
            stage_id,
            subject_id,
            section_type,
            drawing["is_active"],
        ),
    )


# =========================
# Add Drawing
# =========================

async def start_add_drawing(
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

    if len(parts) != 4:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    stage_id = parts[1]
    subject_id = parts[2]

    section_type = normalize_section_type(
        parts[3]
    )

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ قسم غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    clear_drawing_conversation(context)

    context.user_data.update({
        "admin_drawing_stage_id": stage_id,
        "admin_drawing_subject_id": subject_id,
        "admin_drawing_section_type": section_type,
    })

    await query.answer()

    await query.edit_message_text(
        "➕ إضافة رسمة جديدة\n\n"
        "أرسل اسم الرسمة:"
    )

    return ADD_DRAWING_NAME


async def receive_drawing_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return ADD_DRAWING_NAME

    name = normalize_text(
        update.message.text
    )

    if not name:
        await update.message.reply_text(
            "❌ الاسم لا يمكن أن يكون فارغًا.\n"
            "أرسل الاسم مرة أخرى:"
        )

        return ADD_DRAWING_NAME

    context.user_data[
        "admin_drawing_name"
    ] = name

    await update.message.reply_text(
        "📝 أرسل وصف الرسمة.\n\n"
        "إذا لا يوجد وصف أرسل: -"
    )

    return ADD_DRAWING_DESCRIPTION


async def receive_drawing_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return ADD_DRAWING_DESCRIPTION

    description = normalize_description(
        update.message.text
    )

    context.user_data[
        "admin_drawing_description"
    ] = description

    await update.message.reply_text(
        "🔢 أرسل رقم ترتيب الرسمة.\n\n"
        "مثال: 1"
    )

    return ADD_DRAWING_ORDER


async def receive_drawing_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return ADD_DRAWING_ORDER

    try:
        order = int(
            update.message.text.strip()
        )

        if order < 0:
            raise ValueError

    except ValueError:
        await update.message.reply_text(
            "❌ أرسل رقم ترتيب صحيح.\n"
            "مثال: 1"
        )

        return ADD_DRAWING_ORDER

    context.user_data[
        "admin_drawing_order"
    ] = order

    await update.message.reply_text(
        "📎 الآن أرسل ملف الرسمة.\n\n"
        "المسموح:\n"
        "🖼️ صورة\n"
        "📄 مستند\n"
        "🎥 فيديو\n"
        "🎵 صوت"
    )

    return ADD_DRAWING_UPLOAD


async def receive_drawing_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if message is None:
        return ADD_DRAWING_UPLOAD

    (
        file_type,
        telegram_file_id,
        file_size,
    ) = extract_telegram_file(message)

    if not telegram_file_id:
        await message.reply_text(
            "❌ أرسل ملف الرسمة كصورة أو "
            "مستند أو فيديو أو صوت."
        )

        return ADD_DRAWING_UPLOAD

    stage_id = context.user_data.get(
        "admin_drawing_stage_id"
    )

    subject_id = context.user_data.get(
        "admin_drawing_subject_id"
    )

    section_type = context.user_data.get(
        "admin_drawing_section_type"
    )

    name = context.user_data.get(
        "admin_drawing_name"
    )

    description = context.user_data.get(
        "admin_drawing_description"
    )

    sort_order = context.user_data.get(
        "admin_drawing_order",
        0,
    )

    if (
        not stage_id
        or not subject_id
        or section_type not in VALID_SECTION_TYPES
        or not name
    ):
        clear_drawing_conversation(
            context
        )

        await message.reply_text(
            "❌ انتهت جلسة الإضافة.\n"
            "ابدأ الإضافة من لوحة الإدارة من جديد."
        )

        return ConversationHandler.END

    try:
        (
            supabase
            .table("drawings")
            .insert({
                "subject_id": int(subject_id),
                "section_type": section_type,
                "name": name,
                "description": description,
                "telegram_file_id": telegram_file_id,
                "file_type": file_type,
                "file_size": file_size,
                "sort_order": sort_order,
                "is_active": True,
                "deleted_at": None,
            })
            .execute()
        )

    except Exception as exc:
        print(
            f"DRAWING INSERT ERROR: {exc}"
        )

        await message.reply_text(
            "❌ حدث خطأ أثناء حفظ الرسمة "
            "في قاعدة البيانات."
        )

        return ConversationHandler.END

    clear_drawing_conversation(
        context
    )

    await message.reply_text(
        "✅ تمت إضافة الرسمة بنجاح."
    )

    return ConversationHandler.END


# =========================
# Edit Drawing
# =========================

async def start_edit_drawing(
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

    if len(parts) != 5:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    drawing_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]

    section_type = normalize_section_type(
        parts[4]
    )

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ قسم غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    drawing = await get_drawing(
        drawing_id,
        subject_id,
    )

    if not drawing:
        await query.answer(
            "❌ الرسمة غير موجودة.",
            show_alert=True,
        )
        return ConversationHandler.END

    clear_drawing_conversation(
        context
    )

    context.user_data.update({
        "admin_drawing_id": drawing_id,
        "admin_drawing_stage_id": stage_id,
        "admin_drawing_subject_id": subject_id,
        "admin_drawing_section_type": section_type,
    })

    await query.answer()

    await query.edit_message_text(
        "✏️ تعديل الرسمة\n\n"
        f"الاسم الحالي:\n"
        f"{drawing['name']}\n\n"
        "أرسل الاسم الجديد:"
    )

    return EDIT_DRAWING_NAME


async def receive_edit_drawing_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return EDIT_DRAWING_NAME

    name = normalize_text(
        update.message.text
    )

    if not name:
        await update.message.reply_text(
            "❌ الاسم لا يمكن أن يكون فارغًا.\n"
            "أرسل الاسم مرة أخرى:"
        )

        return EDIT_DRAWING_NAME

    context.user_data[
        "admin_drawing_name"
    ] = name

    await update.message.reply_text(
        "📝 أرسل الوصف الجديد.\n\n"
        "إذا لا يوجد وصف أرسل: -"
    )

    return EDIT_DRAWING_DESCRIPTION


async def receive_edit_drawing_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return EDIT_DRAWING_DESCRIPTION

    description = normalize_description(
        update.message.text
    )

    context.user_data[
        "admin_drawing_description"
    ] = description

    await update.message.reply_text(
        "🔢 أرسل رقم الترتيب الجديد.\n\n"
        "مثال: 1"
    )

    return EDIT_DRAWING_ORDER


async def receive_edit_drawing_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return EDIT_DRAWING_ORDER

    try:
        order = int(
            update.message.text.strip()
        )

        if order < 0:
            raise ValueError

    except ValueError:
        await update.message.reply_text(
            "❌ أرسل رقم ترتيب صحيح.\n"
            "مثال: 1"
        )

        return EDIT_DRAWING_ORDER

    drawing_id = context.user_data.get(
        "admin_drawing_id"
    )

    subject_id = context.user_data.get(
        "admin_drawing_subject_id"
    )

    stage_id = context.user_data.get(
        "admin_drawing_stage_id"
    )

    section_type = context.user_data.get(
        "admin_drawing_section_type"
    )

    name = context.user_data.get(
        "admin_drawing_name"
    )

    description = context.user_data.get(
        "admin_drawing_description"
    )

    if (
        not drawing_id
        or not subject_id
        or not stage_id
        or section_type not in VALID_SECTION_TYPES
        or not name
    ):
        clear_drawing_conversation(
            context
        )

        await update.message.reply_text(
            "❌ انتهت جلسة التعديل.\n"
            "ابدأ التعديل من لوحة الإدارة من جديد."
        )

        return ConversationHandler.END

    try:
        (
            supabase
            .table("drawings")
            .update({
                "name": name,
                "description": description,
                "sort_order": order,
                "updated_at": now_iso(),
            })
            .eq("id", drawing_id)
            .eq("subject_id", subject_id)
            .execute()
        )

    except Exception as exc:
        print(
            f"DRAWING UPDATE ERROR: {exc}"
        )

        await update.message.reply_text(
            "❌ حدث خطأ أثناء تعديل الرسمة."
        )

        return ConversationHandler.END

    clear_drawing_conversation(
        context
    )

    await update.message.reply_text(
        "✅ تم تعديل بيانات الرسمة بنجاح."
    )

    return ConversationHandler.END


# =========================
# Enable / Disable
# =========================

async def disable_drawing(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    return await toggle_drawing(
        update,
        disable=True,
    )


async def enable_drawing(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    return await toggle_drawing(
        update,
        disable=False,
    )


async def toggle_drawing(
    update: Update,
    disable=False,
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

    parts = query.data.split(":")

    if len(parts) != 5:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    drawing_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]

    section_type = normalize_section_type(
        parts[4]
    )

    drawing = await get_drawing(
        drawing_id,
        subject_id,
    )

    if not drawing:
        await query.answer(
            "❌ الرسمة غير موجودة.",
            show_alert=True,
        )
        return

    new_status = not disable

    try:
        (
            supabase
            .table("drawings")
            .update({
                "is_active": new_status,
                "updated_at": now_iso(),
            })
            .eq("id", drawing_id)
            .eq("subject_id", subject_id)
            .execute()
        )

    except Exception as exc:
        print(
            f"DRAWING TOGGLE ERROR: {exc}"
        )

        await query.answer(
            "❌ تعذر تحديث حالة الرسمة.",
            show_alert=True,
        )

        return

    await query.answer(
        "✅ تم تحديث الحالة."
    )

    drawing = await get_drawing(
        drawing_id,
        subject_id,
    )

    if not drawing:
        return

    status = (
        "🟢 مفعّلة"
        if drawing["is_active"]
        else "🔴 معطّلة"
    )

    description = (
        drawing.get("description")
        or "لا يوجد"
    )

    await query.edit_message_text(
        "🎨 إدارة الرسمة\n\n"
        f"📌 الاسم: {drawing['name']}\n"
        f"📝 الوصف: {description}\n"
        f"📂 القسم: {section_name(section_type)}\n"
        f"🔢 الترتيب: {drawing.get('sort_order', 0)}\n"
        f"📊 الحالة: {status}",
        reply_markup=drawing_manage_keyboard(
            drawing_id,
            stage_id,
            subject_id,
            section_type,
            drawing["is_active"],
        ),
    )


# =========================
# Delete Drawing
# =========================

async def delete_drawing(
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

    parts = query.data.split(":")

    if len(parts) != 5:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    drawing_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]

    section_type = normalize_section_type(
        parts[4]
    )

    drawing = await get_drawing(
        drawing_id,
        subject_id,
    )

    if not drawing:
        await query.answer(
            "❌ الرسمة غير موجودة.",
            show_alert=True,
        )
        return

    await query.answer()

    await query.edit_message_text(
        "⚠️ تأكيد حذف الرسمة\n\n"
        f"هل أنت متأكد من حذف:\n"
        f"📌 {drawing['name']}\n\n"
        "سيتم حذفها منطقيًا من النظام.",
        reply_markup=delete_confirm_keyboard(
            drawing_id,
            stage_id,
            subject_id,
            section_type,
        ),
    )


async def confirm_delete_drawing(
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

    parts = query.data.split(":")

    if len(parts) != 5:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    drawing_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]

    section_type = normalize_section_type(
        parts[4]
    )

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ قسم غير صالح.",
            show_alert=True,
        )
        return

    try:
        timestamp = now_iso()

        (
            supabase
            .table("drawings")
            .update({
                "deleted_at": timestamp,
                "is_active": False,
                "updated_at": timestamp,
            })
            .eq("id", drawing_id)
            .eq("subject_id", subject_id)
            .execute()
        )

    except Exception as exc:
        print(
            f"DRAWING DELETE ERROR: {exc}"
        )

        await query.answer(
            "❌ تعذر حذف الرسمة.",
            show_alert=True,
        )

        return

    await query.answer(
        "✅ تم حذف الرسمة."
    )

    drawings = await get_drawings(
        subject_id,
        section_type,
        include_inactive=True,
    )

    await query.edit_message_text(
        "🎨 إدارة الرسومات\n"
        f"{section_name(section_type)}\n\n"
        f"عدد الرسومات: {len(drawings)}\n\n"
        "اختر رسمة أو أضف رسمة جديدة:",
        reply_markup=drawing_list_keyboard(
            drawings,
            stage_id,
            subject_id,
            section_type,
        ),
    )


# =========================
# Cancel
# =========================

async def cancel_drawing(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    clear_drawing_conversation(
        context
    )

    if update.message:
        await update.message.reply_text(
            "❌ تم إلغاء العملية."
        )

    return ConversationHandler.END


# =========================
# Conversation Handler
# =========================

def drawing_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                start_add_drawing,
                pattern=r"^add_drawing:",
            ),
            CallbackQueryHandler(
                start_edit_drawing,
                pattern=r"^edit_drawing:",
            ),
        ],

        states={

            ADD_DRAWING_NAME: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_drawing_name,
                )
            ],

            ADD_DRAWING_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_drawing_description,
                )
            ],

            ADD_DRAWING_ORDER: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_drawing_order,
                )
            ],

            ADD_DRAWING_UPLOAD: [
                MessageHandler(
                    filters.ATTACHMENT,
                    receive_drawing_upload,
                )
            ],

            EDIT_DRAWING_NAME: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_edit_drawing_name,
                )
            ],

            EDIT_DRAWING_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_edit_drawing_description,
                )
            ],

            EDIT_DRAWING_ORDER: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_edit_drawing_order,
                )
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_drawing,
            )
        ],

        allow_reentry=True,
    )
