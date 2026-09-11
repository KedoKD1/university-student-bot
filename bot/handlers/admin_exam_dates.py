from datetime import datetime

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
    PERMISSION_MANAGE_EXAMS,
    has_permission,
)


# ============================================================
# Conversation states
# ============================================================

ADD_EXAM_TYPE = 1
ADD_EXAM_TITLE = 2
ADD_EXAM_SUBJECT = 3
ADD_EXAM_DATE = 4
ADD_EXAM_TIME = 5
ADD_EXAM_NOTES = 6

EDIT_EXAM_TYPE = 7
EDIT_EXAM_TITLE = 8
EDIT_EXAM_SUBJECT = 9
EDIT_EXAM_DATE = 10
EDIT_EXAM_TIME = 11
EDIT_EXAM_NOTES = 12


# ============================================================
# Exam types
# ============================================================

EXAM_TYPES = {
    "quiz": "🧪 كويز",
    "midterm": "📝 ميد",
    "final": "🎓 فاينل",
    "other": "📌 أخرى",
}


# ============================================================
# Permission
# ============================================================

async def can_manage_exams(user_id):
    return await has_permission(
        user_id,
        PERMISSION_MANAGE_EXAMS,
    )


# ============================================================
# Keyboards
# ============================================================

def admin_exam_stages_keyboard(stages):
    keyboard = []

    for stage in stages:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📚 المرحلة {stage['stage_number']}",
                callback_data=(
                    f"admin_exam_stage:{stage['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ لوحة الإدارة",
            callback_data="admin_back",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def exam_list_keyboard(exams, stage_id):
    keyboard = []

    for exam in exams:
        exam_id = exam["id"]

        title = exam.get(
            "title",
            "امتحان",
        )

        keyboard.append([
            InlineKeyboardButton(
                text=f"📋 {title}",
                callback_data=(
                    f"manage_exam:"
                    f"{exam_id}:"
                    f"{stage_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "➕ إضافة موعد امتحان",
            callback_data=f"add_exam:{stage_id}",
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ رجوع للمراحل",
            callback_data="admin_exams",
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🏠 لوحة الإدارة",
            callback_data="admin_back",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def manage_exam_keyboard(exam_id, stage_id, is_active):
    keyboard = [
        [
            InlineKeyboardButton(
                "✏️ تعديل الموعد",
                callback_data=(
                    f"edit_exam:{exam_id}:{stage_id}"
                ),
            )
        ],
    ]

    if is_active:
        keyboard.append([
            InlineKeyboardButton(
                "🔒 تعطيل الموعد",
                callback_data=(
                    f"disable_exam:"
                    f"{exam_id}:{stage_id}"
                ),
            )
        ])
    else:
        keyboard.append([
            InlineKeyboardButton(
                "🔓 تفعيل الموعد",
                callback_data=(
                    f"enable_exam:"
                    f"{exam_id}:{stage_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "🗑️ حذف الموعد",
            callback_data=(
                f"delete_exam:"
                f"{exam_id}:{stage_id}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ قائمة المواعيد",
            callback_data=(
                f"admin_exam_list:{stage_id}"
            ),
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def exam_type_keyboard(prefix):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🧪 كويز",
                callback_data=f"{prefix}:quiz",
            )
        ],
        [
            InlineKeyboardButton(
                "📝 ميد",
                callback_data=f"{prefix}:midterm",
            )
        ],
        [
            InlineKeyboardButton(
                "🎓 فاينل",
                callback_data=f"{prefix}:final",
            )
        ],
        [
            InlineKeyboardButton(
                "📌 أخرى",
                callback_data=f"{prefix}:other",
            )
        ],
        [
            InlineKeyboardButton(
                "❌ إلغاء",
                callback_data="cancel_exam",
            )
        ],
    ])


# ============================================================
# Main admin section
# ============================================================

async def admin_exams(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await can_manage_exams(
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

    await query.edit_message_text(
        "📋 إدارة مواعيد الامتحانات\n\n"
        "اختر المرحلة:",
        reply_markup=admin_exam_stages_keyboard(
            stages
        ),
    )


# ============================================================
# Stage list
# ============================================================

async def admin_exam_stage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await can_manage_exams(
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

    response = (
        supabase
        .table("exam_dates")
        .select(
            "id, stage_id, subject_id, exam_type, "
            "title, exam_date, exam_time, notes, "
            "is_active, deleted_at"
        )
        .eq("stage_id", stage_id)
        .is_("deleted_at", "null")
        .order("exam_date")
        .order("exam_time")
        .execute()
    )

    exams = response.data or []

    await query.edit_message_text(
        "📋 مواعيد الامتحانات\n\n"
        f"عدد المواعيد: {len(exams)}\n\n"
        "اختر موعدًا لإدارته أو أضف موعدًا جديدًا:",
        reply_markup=exam_list_keyboard(
            exams,
            stage_id,
        ),
    )


# ============================================================
# Add exam
# ============================================================

async def add_exam_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    if not await can_manage_exams(
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

    context.user_data["exam_stage_id"] = stage_id
    context.user_data.pop("exam_id", None)

    await query.answer()

    await query.edit_message_text(
        "➕ إضافة موعد امتحان\n\n"
        "اختر نوع الامتحان:",
        reply_markup=exam_type_keyboard(
            "add_exam_type"
        ),
    )

    return ADD_EXAM_TYPE


async def add_exam_type(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return ADD_EXAM_TYPE

    exam_type = query.data.split(":", 1)[1]

    context.user_data["exam_type"] = exam_type

    await query.answer()

    await query.edit_message_text(
        "➕ إضافة موعد امتحان\n\n"
        "أرسل اسم الامتحان.\n\n"
        "مثال:\n"
        "Midterm 1"
    )

    return ADD_EXAM_TITLE


async def add_exam_title(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_EXAM_TITLE

    title = (
        update.message.text or ""
    ).strip()

    if not title:
        await update.message.reply_text(
            "❌ اسم الامتحان لا يمكن أن يكون فارغًا."
        )
        return ADD_EXAM_TITLE

    context.user_data["exam_title"] = title

    stage_id = context.user_data.get(
        "exam_stage_id"
    )

    response = (
        supabase
        .table("subjects")
        .select(
            "id, name, is_active"
        )
        .eq("stage_id", stage_id)
        .eq("is_active", True)
        .order("sort_order")
        .order("id")
        .execute()
    )

    subjects = response.data or []

    keyboard = [
        [
            InlineKeyboardButton(
                "📌 بدون تحديد مادة",
                callback_data="exam_subject:none",
            )
        ]
    ]

    for subject in subjects:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📘 {subject['name']}",
                callback_data=(
                    f"exam_subject:{subject['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "❌ إلغاء",
            callback_data="cancel_exam",
        )
    ])

    await update.message.reply_text(
        "➕ إضافة موعد امتحان\n\n"
        "اختر المادة المرتبطة بالامتحان:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )

    return ADD_EXAM_SUBJECT


async def add_exam_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return ADD_EXAM_SUBJECT

    value = query.data.split(
        ":",
        1,
    )[1]

    context.user_data["exam_subject_id"] = (
        None
        if value == "none"
        else int(value)
    )

    await query.answer()

    await query.edit_message_text(
        "➕ إضافة موعد امتحان\n\n"
        "أرسل تاريخ الامتحان بهذا الشكل:\n"
        "YYYY-MM-DD\n\n"
        "مثال:\n"
        "2026-10-15"
    )

    return ADD_EXAM_DATE


async def add_exam_date(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_EXAM_DATE

    value = (
        update.message.text or ""
    ).strip()

    try:
        parsed = datetime.strptime(
            value,
            "%Y-%m-%d",
        ).date()

    except ValueError:
        await update.message.reply_text(
            "❌ التاريخ غير صحيح.\n\n"
            "استخدم الصيغة:\n"
            "YYYY-MM-DD"
        )
        return ADD_EXAM_DATE

    context.user_data["exam_date"] = str(parsed)

    await update.message.reply_text(
        "➕ إضافة موعد امتحان\n\n"
        "أرسل وقت الامتحان بصيغة:\n"
        "HH:MM\n\n"
        "مثال:\n"
        "09:30\n\n"
        "إذا ماكو وقت محدد، أرسل:\n"
        "لا يوجد"
    )

    return ADD_EXAM_TIME


async def add_exam_time(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_EXAM_TIME

    value = (
        update.message.text or ""
    ).strip()

    if value in {
        "لا يوجد",
        "لا",
        "-",
    }:
        context.user_data["exam_time"] = None

    else:
        try:
            parsed = datetime.strptime(
                value,
                "%H:%M",
            ).time()

            context.user_data["exam_time"] = (
                parsed.strftime("%H:%M:%S")
            )

        except ValueError:
            await update.message.reply_text(
                "❌ الوقت غير صحيح.\n\n"
                "استخدم:\n"
                "HH:MM\n\n"
                "مثال:\n"
                "09:30"
            )
            return ADD_EXAM_TIME

    await update.message.reply_text(
        "➕ إضافة موعد امتحان\n\n"
        "أرسل أي ملاحظات إضافية.\n\n"
        "إذا ماكو ملاحظات، أرسل:\n"
        "لا يوجد"
    )

    return ADD_EXAM_NOTES


async def add_exam_notes(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_EXAM_NOTES

    value = (
        update.message.text or ""
    ).strip()

    notes = (
        None
        if value in {
            "لا يوجد",
            "لا",
            "-",
        }
        else value
    )

    stage_id = context.user_data.get(
        "exam_stage_id"
    )

    payload = {
        "stage_id": stage_id,
        "subject_id": context.user_data.get(
            "exam_subject_id"
        ),
        "exam_type": context.user_data.get(
            "exam_type"
        ),
        "title": context.user_data.get(
            "exam_title"
        ),
        "exam_date": context.user_data.get(
            "exam_date"
        ),
        "exam_time": context.user_data.get(
            "exam_time"
        ),
        "notes": notes,
        "is_active": True,
        "deleted_at": None,
    }

    try:
        supabase.table(
            "exam_dates"
        ).insert(payload).execute()

    except Exception as exc:
        print(
            "ADD EXAM ERROR:",
            type(exc).__name__,
            exc,
        )

        await update.message.reply_text(
            "❌ تعذر إضافة موعد الامتحان."
        )

        return ConversationHandler.END

    context.user_data.pop(
        "exam_stage_id",
        None,
    )
    context.user_data.pop(
        "exam_subject_id",
        None,
    )
    context.user_data.pop(
        "exam_type",
        None,
    )
    context.user_data.pop(
        "exam_title",
        None,
    )
    context.user_data.pop(
        "exam_date",
        None,
    )
    context.user_data.pop(
        "exam_time",
        None,
    )

    await update.message.reply_text(
        "✅ تم إضافة موعد الامتحان بنجاح.\n\n"
        "يمكنك الآن العودة إلى إدارة المواعيد."
    )

    return ConversationHandler.END


# ============================================================
# Manage exam
# ============================================================

async def manage_exam(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await can_manage_exams(
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

    exam_id = int(parts[1])
    stage_id = int(parts[2])

    response = (
        supabase
        .table("exam_dates")
        .select(
            "id, stage_id, subject_id, exam_type, "
            "title, exam_date, exam_time, notes, "
            "is_active, deleted_at, subjects(name)"
        )
        .eq("id", exam_id)
        .eq("stage_id", stage_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        await query.answer(
            "❌ الموعد غير موجود.",
            show_alert=True,
        )
        return

    exam = rows[0]

    subject_data = exam.get("subjects")

    subject_name = "بدون مادة"

    if isinstance(subject_data, dict):
        subject_name = (
            subject_data.get("name")
            or "بدون مادة"
        )

    exam_type = EXAM_TYPES.get(
        exam.get("exam_type"),
        "📌 أخرى",
    )

    time_value = exam.get("exam_time")

    if time_value:
        time_value = str(time_value)[:5]
    else:
        time_value = "غير محدد"

    notes = exam.get("notes")

    text = (
        "📋 إدارة موعد الامتحان\n\n"
        f"📌 النوع: {exam_type}\n"
        f"📖 العنوان: {exam.get('title')}\n"
        f"📘 المادة: {subject_name}\n"
        f"📅 التاريخ: {exam.get('exam_date')}\n"
        f"⏰ الوقت: {time_value}\n"
    )

    if notes:
        text += f"ℹ️ الملاحظات: {notes}\n"

    text += (
        "\n"
        f"الحالة: "
        f"{'🟢 فعال' if exam.get('is_active') else '🔴 معطل'}"
    )

    await query.answer()

    await query.edit_message_text(
        text,
        reply_markup=manage_exam_keyboard(
            exam_id,
            stage_id,
            exam.get("is_active", True),
        ),
    )


# ============================================================
# Edit exam
# ============================================================

async def edit_exam_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    if not await can_manage_exams(
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

    exam_id = int(parts[1])
    stage_id = int(parts[2])

    response = (
        supabase
        .table("exam_dates")
        .select(
            "id, stage_id, subject_id, exam_type, "
            "title, exam_date, exam_time, notes"
        )
        .eq("id", exam_id)
        .eq("stage_id", stage_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        await query.answer(
            "❌ الموعد غير موجود.",
            show_alert=True,
        )
        return ConversationHandler.END

    exam = rows[0]

    context.user_data["exam_id"] = exam_id
    context.user_data["exam_stage_id"] = stage_id
    context.user_data["exam_subject_id"] = exam.get(
        "subject_id"
    )
    context.user_data["exam_type"] = exam.get(
        "exam_type"
    )
    context.user_data["exam_title"] = exam.get(
        "title"
    )
    context.user_data["exam_date"] = exam.get(
        "exam_date"
    )
    context.user_data["exam_time"] = exam.get(
        "exam_time"
    )
    context.user_data["exam_notes"] = exam.get(
        "notes"
    )

    await query.answer()

    await query.edit_message_text(
        "✏️ تعديل موعد الامتحان\n\n"
        "اختر النوع الجديد:",
        reply_markup=exam_type_keyboard(
            "edit_exam_type"
        ),
    )

    return EDIT_EXAM_TYPE


async def edit_exam_type(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    value = query.data.split(
        ":",
        1,
    )[1]

    context.user_data["exam_type"] = value

    await query.answer()

    await query.edit_message_text(
        "✏️ تعديل موعد الامتحان\n\n"
        "أرسل اسم الامتحان الجديد:"
    )

    return EDIT_EXAM_TITLE


async def edit_exam_title(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return EDIT_EXAM_TITLE

    title = (
        update.message.text or ""
    ).strip()

    if not title:
        await update.message.reply_text(
            "❌ الاسم لا يمكن أن يكون فارغًا."
        )
        return EDIT_EXAM_TITLE

    context.user_data["exam_title"] = title

    stage_id = context.user_data.get(
        "exam_stage_id"
    )

    response = (
        supabase
        .table("subjects")
        .select(
            "id, name, is_active"
        )
        .eq("stage_id", stage_id)
        .eq("is_active", True)
        .order("sort_order")
        .order("id")
        .execute()
    )

    subjects = response.data or []

    keyboard = [
        [
            InlineKeyboardButton(
                "📌 بدون تحديد مادة",
                callback_data="edit_exam_subject:none",
            )
        ]
    ]

    for subject in subjects:
        keyboard.append([
            InlineKeyboardButton(
                f"📘 {subject['name']}",
                callback_data=(
                    f"edit_exam_subject:"
                    f"{subject['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "❌ إلغاء",
            callback_data="cancel_exam",
        )
    ])

    await update.message.reply_text(
        "اختر المادة الجديدة:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )

    return EDIT_EXAM_SUBJECT


async def edit_exam_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    value = query.data.split(
        ":",
        1,
    )[1]

    context.user_data["exam_subject_id"] = (
        None
        if value == "none"
        else int(value)
    )

    await query.answer()

    await query.edit_message_text(
        "✏️ تعديل موعد الامتحان\n\n"
        "أرسل التاريخ الجديد:\n"
        "YYYY-MM-DD"
    )

    return EDIT_EXAM_DATE


async def edit_exam_date(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return EDIT_EXAM_DATE

    value = (
        update.message.text or ""
    ).strip()

    try:
        parsed = datetime.strptime(
            value,
            "%Y-%m-%d",
        ).date()

    except ValueError:
        await update.message.reply_text(
            "❌ التاريخ غير صحيح.\n"
            "استخدم YYYY-MM-DD"
        )
        return EDIT_EXAM_DATE

    context.user_data["exam_date"] = str(parsed)

    await update.message.reply_text(
        "أرسل الوقت الجديد بصيغة:\n"
        "HH:MM\n\n"
        "أو أرسل: لا يوجد"
    )

    return EDIT_EXAM_TIME


async def edit_exam_time(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return EDIT_EXAM_TIME

    value = (
        update.message.text or ""
    ).strip()

    if value in {
        "لا يوجد",
        "لا",
        "-",
    }:
        context.user_data["exam_time"] = None

    else:
        try:
            parsed = datetime.strptime(
                value,
                "%H:%M",
            ).time()

            context.user_data["exam_time"] = (
                parsed.strftime("%H:%M:%S")
            )

        except ValueError:
            await update.message.reply_text(
                "❌ الوقت غير صحيح."
            )
            return EDIT_EXAM_TIME

    await update.message.reply_text(
        "أرسل الملاحظات الجديدة.\n\n"
        "أو أرسل: لا يوجد"
    )

    return EDIT_EXAM_NOTES


async def edit_exam_notes(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return EDIT_EXAM_NOTES

    value = (
        update.message.text or ""
    ).strip()

    notes = (
        None
        if value in {
            "لا يوجد",
            "لا",
            "-",
        }
        else value
    )

    exam_id = context.user_data.get(
        "exam_id"
    )

    payload = {
        "subject_id": context.user_data.get(
            "exam_subject_id"
        ),
        "exam_type": context.user_data.get(
            "exam_type"
        ),
        "title": context.user_data.get(
            "exam_title"
        ),
        "exam_date": context.user_data.get(
            "exam_date"
        ),
        "exam_time": context.user_data.get(
            "exam_time"
        ),
        "notes": notes,
        "updated_at": datetime.utcnow().isoformat(),
    }

    try:
        (
            supabase
            .table("exam_dates")
            .update(payload)
            .eq("id", exam_id)
            .execute()
        )

    except Exception as exc:
        print(
            "EDIT EXAM ERROR:",
            type(exc).__name__,
            exc,
        )

        await update.message.reply_text(
            "❌ تعذر تعديل الموعد."
        )

        return ConversationHandler.END

    for key in [
        "exam_id",
        "exam_stage_id",
        "exam_subject_id",
        "exam_type",
        "exam_title",
        "exam_date",
        "exam_time",
        "exam_notes",
    ]:
        context.user_data.pop(
            key,
            None,
        )

    await update.message.reply_text(
        "✅ تم تعديل موعد الامتحان بنجاح."
    )

    return ConversationHandler.END


# ============================================================
# Disable
# ============================================================

async def disable_exam(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await can_manage_exams(
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

    exam_id = int(parts[1])
    stage_id = int(parts[2])

    try:
        (
            supabase
            .table("exam_dates")
            .update({
                "is_active": False,
                "updated_at": datetime.utcnow().isoformat(),
            })
            .eq("id", exam_id)
            .eq("stage_id", stage_id)
            .execute()
        )

    except Exception as exc:
        print(
            "DISABLE EXAM ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ تعذر تعطيل الموعد.",
            show_alert=True,
        )
        return

    await query.answer(
        "✅ تم تعطيل الموعد."
    )

    await manage_exam(
        update,
        context,
    )


# ============================================================
# Enable
# ============================================================

async def enable_exam(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await can_manage_exams(
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

    exam_id = int(parts[1])
    stage_id = int(parts[2])

    try:
        (
            supabase
            .table("exam_dates")
            .update({
                "is_active": True,
                "updated_at": datetime.utcnow().isoformat(),
            })
            .eq("id", exam_id)
            .eq("stage_id", stage_id)
            .execute()
        )

    except Exception as exc:
        print(
            "ENABLE EXAM ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ تعذر تفعيل الموعد.",
            show_alert=True,
        )
        return

    await query.answer(
        "✅ تم تفعيل الموعد."
    )

    await manage_exam(
        update,
        context,
    )


# ============================================================
# Delete
# ============================================================

async def delete_exam(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await can_manage_exams(
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

    exam_id = int(parts[1])
    stage_id = int(parts[2])

    await query.answer()

    await query.edit_message_text(
        "⚠️ تأكيد حذف موعد الامتحان\n\n"
        "الحذف هنا سيكون حذفًا منطقيًا، "
        "بحيث لا تضيع البيانات نهائيًا.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🗑️ نعم، احذف الموعد",
                    callback_data=(
                        f"confirm_delete_exam:"
                        f"{exam_id}:{stage_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data=(
                        f"manage_exam:"
                        f"{exam_id}:{stage_id}"
                    ),
                )
            ],
        ]),
    )


async def confirm_delete_exam(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await can_manage_exams(
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

    exam_id = int(parts[1])
    stage_id = int(parts[2])

    try:
        (
            supabase
            .table("exam_dates")
            .update({
                "deleted_at": datetime.utcnow().isoformat(),
                "is_active": False,
                "updated_at": datetime.utcnow().isoformat(),
            })
            .eq("id", exam_id)
            .eq("stage_id", stage_id)
            .execute()
        )

    except Exception as exc:
        print(
            "DELETE EXAM ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ تعذر حذف الموعد.",
            show_alert=True,
        )
        return

    await query.answer(
        "✅ تم حذف الموعد."
    )

    await admin_exam_stage(
        update,
        context,
    )


# ============================================================
# Cancel
# ============================================================

async def cancel_exam(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is not None:
        await query.answer()
        await query.edit_message_text(
            "❌ تم إلغاء العملية."
        )

    for key in [
        "exam_id",
        "exam_stage_id",
        "exam_subject_id",
        "exam_type",
        "exam_title",
        "exam_date",
        "exam_time",
        "exam_notes",
    ]:
        context.user_data.pop(
            key,
            None,
        )

    return ConversationHandler.END


# ============================================================
# Conversation handler
# ============================================================

def exam_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                add_exam_start,
                pattern=r"^add_exam:",
            ),
            CallbackQueryHandler(
                edit_exam_start,
                pattern=r"^edit_exam:",
            ),
        ],

        states={
            ADD_EXAM_TYPE: [
                CallbackQueryHandler(
                    add_exam_type,
                    pattern=r"^add_exam_type:",
                ),
            ],

            ADD_EXAM_TITLE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    add_exam_title,
                ),
            ],

            ADD_EXAM_SUBJECT: [
                CallbackQueryHandler(
                    add_exam_subject,
                    pattern=r"^exam_subject:",
                ),
            ],

            ADD_EXAM_DATE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    add_exam_date,
                ),
            ],

            ADD_EXAM_TIME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    add_exam_time,
                ),
            ],

            ADD_EXAM_NOTES: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    add_exam_notes,
                ),
            ],

            EDIT_EXAM_TYPE: [
                CallbackQueryHandler(
                    edit_exam_type,
                    pattern=r"^edit_exam_type:",
                ),
            ],

            EDIT_EXAM_TITLE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    edit_exam_title,
                ),
            ],

            EDIT_EXAM_SUBJECT: [
                CallbackQueryHandler(
                    edit_exam_subject,
                    pattern=r"^edit_exam_subject:",
                ),
            ],

            EDIT_EXAM_DATE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    edit_exam_date,
                ),
            ],

            EDIT_EXAM_TIME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    edit_exam_time,
                ),
            ],

            EDIT_EXAM_NOTES: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    edit_exam_notes,
                ),
            ],
        },

        fallbacks=[
            CallbackQueryHandler(
                cancel_exam,
                pattern=r"^cancel_exam$",
            ),
        ],

        per_user=True,
        per_chat=True,
    )
