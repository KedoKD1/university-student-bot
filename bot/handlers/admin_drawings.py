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
from bot.handlers.admin import is_admin


# =========================
# Conversation States
# =========================

ADD_DRAWING_NAME, ADD_DRAWING_DESCRIPTION, ADD_DRAWING_ORDER, ADD_DRAWING_UPLOAD = range(4)

EDIT_DRAWING_NAME, EDIT_DRAWING_DESCRIPTION, EDIT_DRAWING_ORDER = range(4, 7)


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
                    f"admin_drawing_subjects:{stage_id}"
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
        status = "🟢" if drawing["is_active"] else "🔴"

        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {drawing['name']}",
                callback_data=(
                    f"manage_drawing:{drawing['id']}:"
                    f"{subject_id}:{section_type}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="➕ إضافة رسمة",
            callback_data=(
                f"add_drawing:{stage_id}:"
                f"{subject_id}:{section_type}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للأقسام",
            callback_data=(
                f"admin_drawing_sections:"
                f"{stage_id}:{subject_id}"
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
            f"disable_drawing:{drawing_id}:"
            f"{stage_id}:{subject_id}:{section_type}"
        )
    else:
        toggle_text = "🟢 تفعيل الرسمة"
        toggle_callback = (
            f"enable_drawing:{drawing_id}:"
            f"{stage_id}:{subject_id}:{section_type}"
        )

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="✏️ تعديل البيانات",
                callback_data=(
                    f"edit_drawing:{drawing_id}:"
                    f"{stage_id}:{subject_id}:{section_type}"
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
                    f"delete_drawing:{drawing_id}:"
                    f"{stage_id}:{subject_id}:{section_type}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ رجوع للرسومات",
                callback_data=(
                    f"admin_drawing_list:{stage_id}:"
                    f"{subject_id}:{section_type}"
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
                    f"confirm_delete_drawing:{drawing_id}:"
                    f"{stage_id}:{subject_id}:{section_type}"
                ),
            ),
            InlineKeyboardButton(
                text="❌ إلغاء",
                callback_data=(
                    f"manage_drawing:{drawing_id}:"
                    f"{subject_id}:{section_type}"
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
        query = query.eq("is_active", True)

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

    response = query.limit(1).execute()

    drawings = response.data or []

    if not drawings:
        return None

    return drawings[0]


# =========================
# Admin Drawings Main
# =========================

async def admin_drawings(
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
                    f"admin_drawing_stage:{stage['id']}"
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
        reply_markup=InlineKeyboardMarkup(keyboard),
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
                    f"admin_drawing_subject:"
                    f"{subject['id']}:{stage_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للمراحل",
            callback_data="admin_drawings",
        )
    ])

    if not subjects:
        await query.edit_message_text(
            "🎨 إدارة الرسومات\n\n"
            "لا توجد مواد مضافة لهذه المرحلة.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    await query.edit_message_text(
        "🎨 إدارة الرسومات\n\n"
        "اختر المادة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
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
        "🎨 إدارة الرسومات\n"
        f"📘 {subject['name']}\n\n"
        "اختر القسم:",
        reply_markup=section_keyboard(
            stage_id,
            subject_id,
        ),
    )


# =========================
# Section → Subjects
# =========================

async def admin_drawing_subjects(
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
                    f"admin_drawing_subject:"
                    f"{subject['id']}:{stage_id}"
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
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =========================
# Subject → Sections
# =========================

async def admin_drawing_sections(
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
        "🎨 إدارة الرسومات\n"
        f"📘 {subject['name']}\n\n"
        "اختر القسم:",
        reply_markup=section_keyboard(
            stage_id,
            subject_id,
        ),
    )


# =========================
# Section → Drawing List
# =========================

async def admin_drawing_section(
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
        "🎨 إدارة الرسومات\n\n"
        f"{section_name(section_type)}\n\n"
    )

    if drawings:
        text += "اختر الرسمة لإدارتها:"
    else:
        text += "لا توجد رسومات مضافة حاليًا."

    await query.edit_message_text(
        text,
        reply_markup=drawing_list_keyboard(
            drawings,
            stage_id,
            subject_id,
            section_type,
        ),
    )


# =========================
# Drawing List
# =========================

async def admin_drawing_list(
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
        "🎨 إدارة الرسومات\n\n"
        f"{section_name(section_type)}\n\n"
        "اختر الرسمة:"
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

    drawing_id = parts[1]
    subject_id = parts[2]
    section_type = normalize_section_type(parts[3])

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ قسم غير صالح.",
            show_alert=True,
        )
        return

    await query.answer()

    drawing = await get_drawing(
        drawing_id,
        subject_id,
    )

    if not drawing:
        await query.edit_message_text(
            "❌ الرسمة غير موجودة."
        )
        return

    status = (
        "🟢 مفعّلة"
        if drawing["is_active"]
        else "🔴 معطّلة"
    )

    description = drawing.get("description")

    text = (
        "🎨 إدارة الرسمة\n\n"
        f"📌 الاسم: {drawing['name']}\n"
        f"📂 القسم: {section_name(section_type)}\n"
        f"📊 الحالة: {status}\n"
        f"🔢 الترتيب: {drawing.get('sort_order', 0)}\n"
    )

    if description:
        text += f"\n📝 الوصف: {description}"

    await query.edit_message_text(
        text,
        reply_markup=drawing_manage_keyboard(
            drawing_id,
            drawing.get("stage_id", ""),
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
            "❌ قسم غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    await query.answer()

    context.user_data["admin_drawing_stage_id"] = stage_id
    context.user_data["admin_drawing_subject_id"] = subject_id
    context.user_data["admin_drawing_section_type"] = section_type

    await query.edit_message_text(
        "➕ إضافة رسمة\n\n"
        "أرسل اسم الرسمة:"
    )

    return ADD_DRAWING_NAME


async def receive_drawing_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_DRAWING_NAME

    name = normalize_text(
        update.message.text or ""
    )

    if not name:
        await update.message.reply_text(
            "❌ اسم الرسمة لا يمكن أن يكون فارغًا.\n"
            "أرسل الاسم مرة أخرى:"
        )
        return ADD_DRAWING_NAME

    context.user_data["admin_drawing_name"] = name

    await update.message.reply_text(
        "📝 أرسل وصف الرسمة.\n\n"
        "إذا لا يوجد وصف، أرسل: -"
    )

    return ADD_DRAWING_DESCRIPTION


async def receive_drawing_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_DRAWING_DESCRIPTION

    description = normalize_description(
        update.message.text or ""
    )

    context.user_data["admin_drawing_description"] = description

    await update.message.reply_text(
        "🔢 أرسل رقم ترتيب الرسمة.\n\n"
        "مثال: 1"
    )

    return ADD_DRAWING_ORDER


async def receive_drawing_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_DRAWING_ORDER

    value = (update.message.text or "").strip()

    try:
        order = int(value)
    except ValueError:
        await update.message.reply_text(
            "❌ أرسل رقمًا صحيحًا فقط.\n"
            "مثال: 1"
        )
        return ADD_DRAWING_ORDER

    context.user_data["admin_drawing_order"] = order

    await update.message.reply_text(
        "📎 الآن أرسل الرسمة.\n\n"
        "يمكن إرسال صورة أو مستند أو فيديو أو صوت."
    )

    return ADD_DRAWING_UPLOAD


async def receive_drawing_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_DRAWING_UPLOAD

    (
        file_type,
        telegram_file_id,
        file_size,
    ) = extract_telegram_file(update.message)

    if not telegram_file_id:
        await update.message.reply_text(
            "❌ أرسل صورة أو مستند أو فيديو أو صوت."
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

    if not all([
        stage_id,
        subject_id,
        section_type,
        name,
    ]):
        clear_drawing_conversation(context)

        await update.message.reply_text(
            "❌ انتهت جلسة الإضافة. حاول مرة أخرى."
        )

        return ConversationHandler.END

    try:
        supabase.table("drawings").insert({
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
        }).execute()

    except Exception as exc:
        print(
            f"Error adding drawing: {exc}"
        )

        await update.message.reply_text(
            "❌ حدث خطأ أثناء حفظ الرسمة.\n"
            "لم يتم حفظها."
        )

        return ConversationHandler.END

    clear_drawing_conversation(context)

    await update.message.reply_text(
        "✅ تمت إضافة الرسمة بنجاح."
    )

    return ConversationHandler.END


# =========================
# Disable Drawing
# =========================

async def disable_drawing(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    return await toggle_drawing(
        update,
        context,
        False,
    )


# =========================
# Enable Drawing
# =========================

async def enable_drawing(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    return await toggle_drawing(
        update,
        context,
        True,
    )


async def toggle_drawing(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    active,
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

    drawing_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]
    section_type = normalize_section_type(parts[4])

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ قسم غير صالح.",
            show_alert=True,
        )
        return

    await query.answer()

    supabase.table("drawings").update({
        "is_active": active,
    }).eq(
        "id",
        drawing_id,
    ).execute()

    drawing = await get_drawing(
        drawing_id,
        subject_id,
    )

    if not drawing:
        await query.edit_message_text(
            "❌ الرسمة غير موجودة."
        )
        return

    status = (
        "🟢 تم تفعيل الرسمة."
        if active
        else "🔴 تم تعطيل الرسمة."
    )

    await query.edit_message_text(
        status,
        reply_markup=drawing_manage_keyboard(
            drawing_id,
            stage_id,
            subject_id,
            section_type,
            active,
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

    drawing_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]
    section_type = normalize_section_type(parts[4])

    await query.answer()

    drawing = await get_drawing(
        drawing_id,
        subject_id,
    )

    if not drawing:
        await query.edit_message_text(
            "❌ الرسمة غير موجودة."
        )
        return

    await query.edit_message_text(
        "⚠️ هل أنت متأكد من حذف هذه الرسمة؟\n\n"
        f"🎨 {drawing['name']}\n\n"
        "سيتم حذفها من ظهور الطلاب، ويمكن لاحقًا "
        "استرجاعها من قاعدة البيانات إذا احتجنا.",
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

    drawing_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]
    section_type = normalize_section_type(parts[4])

    await query.answer()

    supabase.table("drawings").update({
        "deleted_at": "now()",
        "is_active": False,
    }).eq(
        "id",
        drawing_id,
    ).execute()

    await query.edit_message_text(
        "✅ تم حذف الرسمة بنجاح.\n\n"
        "تم استخدام الحذف المنطقي للحفاظ على البيانات."
    )


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
        ],
        states={
            ADD_DRAWING_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_drawing_name,
                ),
            ],
            ADD_DRAWING_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_drawing_description,
                ),
            ],
            ADD_DRAWING_ORDER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_drawing_order,
                ),
            ],
            ADD_DRAWING_UPLOAD: [
                MessageHandler(
                    filters.ATTACHMENT,
                    receive_drawing_upload,
                ),
            ],
        },
        fallbacks=[],
        allow_reentry=True,
    )
