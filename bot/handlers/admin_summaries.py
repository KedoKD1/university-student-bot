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

ADD_SUMMARY_NAME, ADD_SUMMARY_DESCRIPTION, ADD_SUMMARY_ORDER, ADD_SUMMARY_UPLOAD = range(4)

EDIT_SUMMARY_NAME, EDIT_SUMMARY_DESCRIPTION, EDIT_SUMMARY_ORDER = range(4, 7)


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


def clear_summary_conversation(context):
    keys = [
        "admin_summary_stage_id",
        "admin_summary_subject_id",
        "admin_summary_section_type",
        "admin_summary_id",
        "admin_summary_name",
        "admin_summary_description",
        "admin_summary_order",
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
                    f"admin_summary_section:"
                    f"theoretical:{subject_id}:{stage_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="🧪 العملي",
                callback_data=(
                    f"admin_summary_section:"
                    f"practical:{subject_id}:{stage_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ رجوع للمواد",
                callback_data=(
                    f"admin_summary_subjects:{stage_id}"
                ),
            )
        ],
    ])


def summary_list_keyboard(
    summaries,
    stage_id,
    subject_id,
    section_type,
):
    section_type = normalize_section_type(section_type)

    keyboard = []

    for summary in summaries:
        status = "🟢" if summary["is_active"] else "🔴"

        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {summary['name']}",
                callback_data=(
                    f"manage_summary:{summary['id']}:"
                    f"{subject_id}:{section_type}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="➕ إضافة ملخص",
            callback_data=(
                f"add_summary:{stage_id}:"
                f"{subject_id}:{section_type}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للأقسام",
            callback_data=(
                f"admin_summary_sections:"
                f"{stage_id}:{subject_id}"
            ),
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def summary_manage_keyboard(
    summary_id,
    stage_id,
    subject_id,
    section_type,
    is_active,
):
    section_type = normalize_section_type(section_type)

    if is_active:
        toggle_text = "🔴 تعطيل الملخص"
        toggle_callback = (
            f"disable_summary:{summary_id}:"
            f"{stage_id}:{subject_id}:{section_type}"
        )
    else:
        toggle_text = "🟢 تفعيل الملخص"
        toggle_callback = (
            f"enable_summary:{summary_id}:"
            f"{stage_id}:{subject_id}:{section_type}"
        )

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="✏️ تعديل البيانات",
                callback_data=(
                    f"edit_summary:{summary_id}:"
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
                text="🗑️ حذف الملخص",
                callback_data=(
                    f"delete_summary:{summary_id}:"
                    f"{stage_id}:{subject_id}:{section_type}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ رجوع للملخصات",
                callback_data=(
                    f"admin_summary_list:{stage_id}:"
                    f"{subject_id}:{section_type}"
                ),
            )
        ],
    ])


def delete_confirm_keyboard(
    summary_id,
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
                    f"confirm_delete_summary:{summary_id}:"
                    f"{stage_id}:{subject_id}:{section_type}"
                ),
            ),
            InlineKeyboardButton(
                text="❌ إلغاء",
                callback_data=(
                    f"manage_summary:{summary_id}:"
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
                text="⬅️ العودة إلى الملخصات",
                callback_data=(
                    f"admin_summary_list:{stage_id}:"
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


async def get_summaries(
    subject_id,
    section_type,
    include_inactive=True,
):
    section_type = normalize_section_type(section_type)

    if section_type not in VALID_SECTION_TYPES:
        return []

    query = (
        supabase
        .table("summaries")
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


async def get_summary(
    summary_id,
    subject_id=None,
):
    query = (
        supabase
        .table("summaries")
        .select("*")
        .eq("id", summary_id)
        .is_("deleted_at", "null")
    )

    if subject_id is not None:
        query = query.eq(
            "subject_id",
            subject_id,
        )

    response = query.limit(1).execute()

    summaries = response.data or []

    if not summaries:
        return None

    return summaries[0]


# =========================
# Admin Summaries Main
# =========================

async def admin_summaries(
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
                    f"admin_summary_stage:{stage['id']}"
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
        "📝 إدارة الملخصات\n\n"
        "اختر المرحلة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =========================
# Stage → Subjects
# =========================

async def admin_summary_stage(
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
                    f"admin_summary_subject:"
                    f"{subject['id']}:{stage_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للمراحل",
            callback_data="admin_summaries",
        )
    ])

    if not subjects:
        await query.edit_message_text(
            "📝 إدارة الملخصات\n\n"
            "لا توجد مواد مضافة لهذه المرحلة.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    await query.edit_message_text(
        "📝 إدارة الملخصات\n\n"
        "اختر المادة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =========================
# Subject → Sections
# =========================

async def admin_summary_subject(
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
        "📝 إدارة الملخصات\n"
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

async def admin_summary_subjects(
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
                    f"admin_summary_subject:"
                    f"{subject['id']}:{stage_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للمراحل",
            callback_data="admin_summaries",
        )
    ])

    await query.edit_message_text(
        "📝 إدارة الملخصات\n\n"
        "اختر المادة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =========================
# Section → Summary List
# =========================

async def admin_summary_section(
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

    summaries = await get_summaries(
        subject_id,
        section_type,
        include_inactive=True,
    )

    await query.edit_message_text(
        "📝 إدارة الملخصات\n\n"
        f"{section_name(section_type)}\n\n"
        "اختر الملخص:",
        reply_markup=summary_list_keyboard(
            summaries,
            stage_id,
            subject_id,
            section_type,
        ),
    )


async def admin_summary_sections(
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
        "📝 إدارة الملخصات\n"
        f"📘 {subject['name']}\n\n"
        "اختر القسم:",
        reply_markup=section_keyboard(
            stage_id,
            subject_id,
        ),
    )


# =========================
# Summary List
# =========================

async def admin_summary_list(
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

    summaries = await get_summaries(
        subject_id,
        section_type,
        include_inactive=True,
    )

    await query.edit_message_text(
        "📝 إدارة الملخصات\n\n"
        f"{section_name(section_type)}\n\n"
        "اختر الملخص:",
        reply_markup=summary_list_keyboard(
            summaries,
            stage_id,
            subject_id,
            section_type,
        ),
    )


# =========================
# Manage Summary
# =========================

async def manage_summary(
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

    summary_id = parts[1]
    subject_id = parts[2]
    section_type = normalize_section_type(parts[3])

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True,
        )
        return

    summary = await get_summary(
        summary_id,
        subject_id,
    )

    if not summary:
        await query.answer(
            "❌ الملخص غير موجود.",
            show_alert=True,
        )
        return

    await query.answer()

    status = (
        "🟢 فعال"
        if summary["is_active"]
        else "🔴 معطل"
    )

    description = (
        summary.get("description")
        or "لا يوجد وصف."
    )

    await query.edit_message_text(
        "📝 إدارة الملخص\n\n"
        f"📄 الاسم: {summary['name']}\n"
        f"📚 القسم: {section_name(section_type)}\n"
        f"📌 الحالة: {status}\n"
        f"🔢 الترتيب: {summary.get('sort_order', 0)}\n\n"
        f"📝 الوصف:\n{description}",
        reply_markup=summary_manage_keyboard(
            summary_id,
            summary["subject_id"],
            subject_id,
            section_type,
            summary["is_active"],
        ),
    )


# =========================
# Disable / Enable
# =========================

async def disable_summary(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await toggle_summary(
        update,
        context,
        False,
    )


async def enable_summary(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await toggle_summary(
        update,
        context,
        True,
    )


async def toggle_summary(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    is_active,
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

    summary_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]
    section_type = normalize_section_type(parts[4])

    if section_type not in VALID_SECTION_TYPES:
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True,
        )
        return

    summary = await get_summary(
        summary_id,
        subject_id,
    )

    if not summary:
        await query.answer(
            "❌ الملخص غير موجود.",
            show_alert=True,
        )
        return

    await query.answer()

    supabase.table("summaries").update({
        "is_active": is_active,
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }).eq(
        "id",
        summary_id,
    ).execute()

    status_text = (
        "🟢 تم تفعيل الملخص."
        if is_active
        else "🔴 تم تعطيل الملخص."
    )

    await query.edit_message_text(
        f"{status_text}\n\n"
        f"📄 {summary['name']}",
        reply_markup=summary_manage_keyboard(
            summary_id,
            stage_id,
            subject_id,
            section_type,
            is_active,
        ),
    )


# =========================
# Delete
# =========================

async def delete_summary(
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

    summary_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]
    section_type = normalize_section_type(parts[4])

    summary = await get_summary(
        summary_id,
        subject_id,
    )

    if not summary:
        await query.answer(
            "❌ الملخص غير موجود.",
            show_alert=True,
        )
        return

    await query.answer()

    await query.edit_message_text(
        "⚠️ تأكيد حذف الملخص\n\n"
        f"📄 {summary['name']}\n\n"
        "هل أنت متأكد من حذف هذا الملخص؟\n\n"
        "سيتم إخفاؤه عن الطلاب.",
        reply_markup=delete_confirm_keyboard(
            summary_id,
            stage_id,
            subject_id,
            section_type,
        ),
    )


async def confirm_delete_summary(
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

    summary_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]
    section_type = normalize_section_type(parts[4])

    summary = await get_summary(
        summary_id,
        subject_id,
    )

    if not summary:
        await query.answer(
            "❌ الملخص غير موجود أو تم حذفه مسبقاً.",
            show_alert=True,
        )
        return

    await query.answer(
        "⏳ جارٍ حذف الملخص..."
    )

    supabase.table("summaries").update({
        "deleted_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "is_active": False,
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }).eq(
        "id",
        summary_id,
    ).execute()

    await query.edit_message_text(
        "✅ تم حذف الملخص بنجاح.\n\n"
        f"📄 {summary['name']}",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text="⬅️ العودة إلى الملخصات",
                    callback_data=(
                        f"admin_summary_list:{stage_id}:"
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
        ]),
    )


# =========================
# Add Summary
# =========================

async def start_add_summary(
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

    clear_summary_conversation(context)

    context.user_data["admin_summary_stage_id"] = stage_id
    context.user_data["admin_summary_subject_id"] = subject_id
    context.user_data["admin_summary_section_type"] = section_type

    await query.answer()

    await query.edit_message_text(
        "➕ إضافة ملخص\n\n"
        "أرسل اسم الملخص:"
    )

    return ADD_SUMMARY_NAME


async def receive_add_summary_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_SUMMARY_NAME

    name = normalize_text(update.message.text)

    if not name:
        await update.message.reply_text(
            "❌ الاسم لا يمكن أن يكون فارغاً.\n\n"
            "أرسل اسم الملخص مرة أخرى:"
        )
        return ADD_SUMMARY_NAME

    context.user_data["admin_summary_name"] = name

    await update.message.reply_text(
        "📝 أرسل وصف الملخص:\n\n"
        "إذا لا تريد وصفاً، أرسل: -"
    )

    return ADD_SUMMARY_DESCRIPTION


async def receive_add_summary_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_SUMMARY_DESCRIPTION

    description = normalize_description(
        update.message.text
    )

    context.user_data[
        "admin_summary_description"
    ] = description

    await update.message.reply_text(
        "🔢 أرسل ترتيب الملخص كرقم.\n\n"
        "مثال: 1"
    )

    return ADD_SUMMARY_ORDER


async def receive_add_summary_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_SUMMARY_ORDER

    text = update.message.text.strip()

    try:
        order = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ يجب أن يكون الترتيب رقماً.\n\n"
            "مثال: 1"
        )
        return ADD_SUMMARY_ORDER

    if order < 0:
        await update.message.reply_text(
            "❌ الترتيب يجب أن يكون 0 أو أكبر."
        )
        return ADD_SUMMARY_ORDER

    context.user_data[
        "admin_summary_order"
    ] = order

    await update.message.reply_text(
        "📎 الآن أرسل ملف الملخص.\n\n"
        "يمكنك إرسال:\n"
        "📄 مستند\n"
        "🖼️ صورة\n"
        "🎥 فيديو\n"
        "🎵 صوت"
    )

    return ADD_SUMMARY_UPLOAD


async def receive_add_summary_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_SUMMARY_UPLOAD

    file_type, telegram_file_id, file_size = (
        extract_telegram_file(update.message)
    )

    if not telegram_file_id:
        await update.message.reply_text(
            "❌ لم أتعرف على الملف.\n\n"
            "أرسل مستنداً أو صورة أو فيديو أو صوت."
        )
        return ADD_SUMMARY_UPLOAD

    stage_id = context.user_data.get(
        "admin_summary_stage_id"
    )
    subject_id = context.user_data.get(
        "admin_summary_subject_id"
    )
    section_type = context.user_data.get(
        "admin_summary_section_type"
    )
    name = context.user_data.get(
        "admin_summary_name"
    )
    description = context.user_data.get(
        "admin_summary_description"
    )
    sort_order = context.user_data.get(
        "admin_summary_order"
    )

    if not all([
        stage_id,
        subject_id,
        section_type,
        name,
        sort_order is not None,
    ]):
        clear_summary_conversation(context)

        await update.message.reply_text(
            "❌ انتهت بيانات عملية الإضافة.\n\n"
            "ابدأ العملية من جديد."
        )

        return ConversationHandler.END

    try:
        supabase.table("summaries").insert({
            "subject_id": subject_id,
            "section_type": section_type,
            "name": name,
            "description": description,
            "telegram_file_id": telegram_file_id,
            "file_type": file_type,
            "file_size": file_size,
            "sort_order": sort_order,
            "is_active": True,
        }).execute()
    except Exception:
        await update.message.reply_text(
            "❌ تعذر حفظ الملخص في قاعدة البيانات.\n\n"
            "تأكد من بيانات الجدول وحاول مرة أخرى."
        )

        return ConversationHandler.END

    await update.message.reply_text(
        "✅ تمت إضافة الملخص بنجاح.\n\n"
        f"📄 {name}\n"
        f"📚 {section_name(section_type)}",
        reply_markup=after_save_keyboard(
            stage_id,
            subject_id,
            section_type,
        ),
    )

    clear_summary_conversation(context)

    return ConversationHandler.END


# =========================
# Edit Summary
# =========================

async def start_edit_summary(
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

    summary_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]
    section_type = normalize_section_type(parts[4])

    summary = await get_summary(
        summary_id,
        subject_id,
    )

    if not summary:
        await query.answer(
            "❌ الملخص غير موجود.",
            show_alert=True,
        )
        return ConversationHandler.END

    clear_summary_conversation(context)

    context.user_data["admin_summary_stage_id"] = stage_id
    context.user_data["admin_summary_subject_id"] = subject_id
    context.user_data["admin_summary_section_type"] = section_type
    context.user_data["admin_summary_id"] = summary_id

    await query.answer()

    await query.edit_message_text(
        "✏️ تعديل الملخص\n\n"
        f"الاسم الحالي:\n{summary['name']}\n\n"
        "أرسل الاسم الجديد:"
    )

    return EDIT_SUMMARY_NAME


async def receive_edit_summary_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return EDIT_SUMMARY_NAME

    name = normalize_text(update.message.text)

    if not name:
        await update.message.reply_text(
            "❌ الاسم لا يمكن أن يكون فارغاً."
        )
        return EDIT_SUMMARY_NAME

    context.user_data[
        "admin_summary_name"
    ] = name

    await update.message.reply_text(
        "📝 أرسل الوصف الجديد:\n\n"
        "إذا لا تريد وصفاً، أرسل: -"
    )

    return EDIT_SUMMARY_DESCRIPTION


async def receive_edit_summary_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return EDIT_SUMMARY_DESCRIPTION

    description = normalize_description(
        update.message.text
    )

    context.user_data[
        "admin_summary_description"
    ] = description

    await update.message.reply_text(
        "🔢 أرسل الترتيب الجديد كرقم."
    )

    return EDIT_SUMMARY_ORDER


async def receive_edit_summary_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return EDIT_SUMMARY_ORDER

    try:
        order = int(
            update.message.text.strip()
        )
    except ValueError:
        await update.message.reply_text(
            "❌ يجب أن يكون الترتيب رقماً."
        )
        return EDIT_SUMMARY_ORDER

    if order < 0:
        await update.message.reply_text(
            "❌ الترتيب يجب أن يكون 0 أو أكبر."
        )
        return EDIT_SUMMARY_ORDER

    summary_id = context.user_data.get(
        "admin_summary_id"
    )
    stage_id = context.user_data.get(
        "admin_summary_stage_id"
    )
    subject_id = context.user_data.get(
        "admin_summary_subject_id"
    )
    section_type = context.user_data.get(
        "admin_summary_section_type"
    )
    name = context.user_data.get(
        "admin_summary_name"
    )
    description = context.user_data.get(
        "admin_summary_description"
    )

    if not all([
        summary_id,
        stage_id,
        subject_id,
        section_type,
        name,
    ]):
        clear_summary_conversation(context)

        await update.message.reply_text(
            "❌ انتهت بيانات عملية التعديل.\n\n"
            "ابدأ العملية من جديد."
        )

        return ConversationHandler.END

    try:
        supabase.table("summaries").update({
            "name": name,
            "description": description,
            "sort_order": order,
            "updated_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }).eq(
            "id",
            summary_id,
        ).execute()
    except Exception:
        await update.message.reply_text(
            "❌ تعذر تعديل بيانات الملخص."
        )

        return ConversationHandler.END

    await update.message.reply_text(
        "✅ تم تعديل بيانات الملخص بنجاح.\n\n"
        f"📄 {name}",
        reply_markup=after_save_keyboard(
            stage_id,
            subject_id,
            section_type,
        ),
    )

    clear_summary_conversation(context)

    return ConversationHandler.END


# =========================
# Cancel
# =========================

async def cancel_summary_operation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    clear_summary_conversation(context)

    if update.message:
        await update.message.reply_text(
            "❌ تم إلغاء العملية."
        )

    return ConversationHandler.END


# =========================
# Conversation Handler
# =========================

def summary_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                start_add_summary,
                pattern=r"^add_summary:",
            ),
            CallbackQueryHandler(
                start_edit_summary,
                pattern=r"^edit_summary:",
            ),
        ],
        states={
            ADD_SUMMARY_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_add_summary_name,
                ),
            ],
            ADD_SUMMARY_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_add_summary_description,
                ),
            ],
            ADD_SUMMARY_ORDER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_add_summary_order,
                ),
            ],
            ADD_SUMMARY_UPLOAD: [
                MessageHandler(
                    filters.Document.ALL
                    | filters.PHOTO
                    | filters.VIDEO
                    | filters.AUDIO,
                    receive_add_summary_upload,
                ),
            ],
            EDIT_SUMMARY_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_edit_summary_name,
                ),
            ],
            EDIT_SUMMARY_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_edit_summary_description,
                ),
            ],
            EDIT_SUMMARY_ORDER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_edit_summary_order,
                ),
            ],
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_summary_operation,
            ),
        ],
        allow_reentry=True,
    )
