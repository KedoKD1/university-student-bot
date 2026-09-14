from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from bot.database.client import supabase


# ============================================================
# Helpers
# ============================================================

EXAM_TYPE_NAMES = {
    "quiz": "🧪 كويز",
    "midterm": "📝 ميد",
    "final": "🎓 فاينل",
    "other": "📌 أخرى",
}


def format_exam_type(exam_type):
    return EXAM_TYPE_NAMES.get(
        exam_type,
        "📌 أخرى",
    )


def format_date(date_value):
    if not date_value:
        return "غير محدد"

    value = str(date_value)
    parts = value.split("-")

    if len(parts) == 3:
        year, month, day = parts
        return f"{day}/{month}/{year}"

    return value


def format_time(time_value):
    if not time_value:
        return ""

    value = str(time_value)

    if len(value) >= 5:
        return value[:5]

    return value


def owner_error():
    return "⛔ هذا الزر ليس لك."


def invalid_selection():
    return "❌ اختيار غير صالح."


# ============================================================
# Keyboards
# ============================================================

def exam_stages_keyboard(stages, user_id):
    keyboard = []

    for stage in stages:
        stage_id = stage["id"]
        stage_number = stage["stage_number"]
        is_active = stage.get("is_active", False)

        if is_active:
            keyboard.append([
                InlineKeyboardButton(
                    text=f"📚 المرحلة {stage_number}",
                    callback_data=(
                        f"exam_stage:"
                        f"{stage_id}:"
                        f"{user_id}"
                    ),
                )
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(
                    text=f"🔒 المرحلة {stage_number}",
                    callback_data=(
                        f"exam_locked:"
                        f"{stage_id}:"
                        f"{user_id}"
                    ),
                )
            ])

    keyboard.append([
        InlineKeyboardButton(
            text="🏠 القائمة الرئيسية",
            callback_data=f"back_main:{user_id}",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def exam_types_keyboard(stage_id, user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🧪 الكويزات",
                callback_data=(
                    f"exam_type:{stage_id}:quiz:{user_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "📝 الميدات",
                callback_data=(
                    f"exam_type:{stage_id}:midterm:{user_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "🎓 الفاينلات",
                callback_data=(
                    f"exam_type:{stage_id}:final:{user_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "📌 أخرى",
                callback_data=(
                    f"exam_type:{stage_id}:other:{user_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "📋 كل المواعيد",
                callback_data=(
                    f"exam_type:{stage_id}:all:{user_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 رجوع للمراحل",
                callback_data=f"exam_back:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 القائمة الرئيسية",
                callback_data=f"back_main:{user_id}",
            )
        ],
    ])


def exam_results_keyboard(stage_id, user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔙 رجوع لأنواع الامتحانات",
                callback_data=(
                    f"exam_stage:"
                    f"{stage_id}:"
                    f"{user_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 القائمة الرئيسية",
                callback_data=f"back_main:{user_id}",
            )
        ],
    ])


# ============================================================
# Student: show stages
# ============================================================

async def show_exam_dates(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    data = query.data or ""
    parts = data.split(":")

    # main:exams:user_id
    if len(parts) != 3 or parts[0] != "main":
        await query.answer(
            invalid_selection(),
            show_alert=True,
        )
        return

    if parts[1] != "exams":
        await query.answer(
            invalid_selection(),
            show_alert=True,
        )
        return

    try:
        user_id = int(parts[2])
    except (TypeError, ValueError):
        await query.answer(
            "❌ المستخدم غير صالح.",
            show_alert=True,
        )
        return

    if query.from_user.id != user_id:
        await query.answer(
            owner_error(),
            show_alert=True,
        )
        return

    await query.answer()

    try:
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

    except Exception as exc:
        print(
            "EXAM STAGES ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.edit_message_text(
            "❌ تعذر تحميل المراحل حالياً.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🏠 القائمة الرئيسية",
                        callback_data=(
                            f"back_main:{user_id}"
                        ),
                    )
                ]
            ]),
        )
        return

    if not stages:
        await query.edit_message_text(
            "📋 مواعيد الامتحانات\n\n"
            "❌ لا توجد مراحل دراسية حالياً.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🏠 القائمة الرئيسية",
                        callback_data=(
                            f"back_main:{user_id}"
                        ),
                    )
                ]
            ]),
        )
        return

    await query.edit_message_text(
        "📋 مواعيد الامتحانات\n\n"
        "اختر المرحلة الدراسية:",
        reply_markup=exam_stages_keyboard(
            stages,
            user_id,
        ),
    )


# ============================================================
# Student: stage
# ============================================================

async def exam_stage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    data = query.data or ""
    parts = data.split(":")

    if len(parts) != 3 or parts[0] != "exam_stage":
        await query.answer(
            invalid_selection(),
            show_alert=True,
        )
        return

    try:
        stage_id = int(parts[1])
        user_id = int(parts[2])
    except (TypeError, ValueError):
        await query.answer(
            invalid_selection(),
            show_alert=True,
        )
        return

    if query.from_user.id != user_id:
        await query.answer(
            owner_error(),
            show_alert=True,
        )
        return

    await query.answer()

    try:
        response = (
            supabase
            .table("stages")
            .select(
                "id, stage_number, is_active"
            )
            .eq("id", stage_id)
            .limit(1)
            .execute()
        )

        stages = response.data or []

    except Exception as exc:
        print(
            "EXAM STAGE ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.edit_message_text(
            "❌ تعذر تحميل المرحلة.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🏠 القائمة الرئيسية",
                        callback_data=(
                            f"back_main:{user_id}"
                        ),
                    )
                ]
            ]),
        )
        return

    if not stages:
        await query.edit_message_text(
            "❌ المرحلة غير موجودة.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 رجوع للمراحل",
                        callback_data=(
                            f"exam_back:{user_id}"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🏠 القائمة الرئيسية",
                        callback_data=(
                            f"back_main:{user_id}"
                        ),
                    )
                ],
            ]),
        )
        return

    stage = stages[0]

    if not stage.get("is_active", False):
        await query.answer(
            "🔒 هذه المرحلة غير متاحة حالياً.",
            show_alert=True,
        )
        return

    await query.edit_message_text(
        f"📋 مواعيد امتحانات المرحلة "
        f"{stage['stage_number']}\n\n"
        "اختر نوع الامتحان:",
        reply_markup=exam_types_keyboard(
            stage_id,
            user_id,
        ),
    )


# ============================================================
# Student: list exams
# ============================================================

async def exam_type(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    data = query.data or ""
    parts = data.split(":")

    if len(parts) != 4 or parts[0] != "exam_type":
        await query.answer(
            invalid_selection(),
            show_alert=True,
        )
        return

    try:
        stage_id = int(parts[1])
        exam_type_value = parts[2]
        user_id = int(parts[3])
    except (TypeError, ValueError):
        await query.answer(
            invalid_selection(),
            show_alert=True,
        )
        return

    if query.from_user.id != user_id:
        await query.answer(
            owner_error(),
            show_alert=True,
        )
        return

    allowed_types = {
        "quiz",
        "midterm",
        "final",
        "other",
        "all",
    }

    if exam_type_value not in allowed_types:
        await query.answer(
            "❌ نوع الامتحان غير صالح.",
            show_alert=True,
        )
        return

    await query.answer()

    try:
        stage_response = (
            supabase
            .table("stages")
            .select(
                "id, stage_number, is_active"
            )
            .eq("id", stage_id)
            .limit(1)
            .execute()
        )

        stages = stage_response.data or []

        if not stages:
            await query.edit_message_text(
                "❌ المرحلة غير موجودة.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🔙 رجوع للمراحل",
                            callback_data=(
                                f"exam_back:{user_id}"
                            ),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 القائمة الرئيسية",
                            callback_data=(
                                f"back_main:{user_id}"
                            ),
                        )
                    ],
                ]),
            )
            return

        stage = stages[0]

        if not stage.get("is_active", False):
            await query.answer(
                "🔒 هذه المرحلة غير متاحة حالياً.",
                show_alert=True,
            )
            return

        stage_number = stage["stage_number"]

        builder = (
            supabase
            .table("exam_dates")
            .select(
                "id, stage_id, subject_id, exam_type, "
                "title, exam_date, exam_time, notes, "
                "subjects(name)"
            )
            .eq("stage_id", stage_id)
            .eq("is_active", True)
            .is_("deleted_at", "null")
        )

        if exam_type_value != "all":
            builder = builder.eq(
                "exam_type",
                exam_type_value,
            )

        response = (
            builder
            .order("exam_date")
            .order("exam_time")
            .execute()
        )

        exams = response.data or []

    except Exception as exc:
        print(
            "EXAM DATES ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.edit_message_text(
            "❌ تعذر تحميل مواعيد الامتحانات.",
            reply_markup=exam_results_keyboard(
                stage_id,
                user_id,
            ),
        )
        return

    if not exams:
        await query.edit_message_text(
            f"📋 مواعيد امتحانات المرحلة "
            f"{stage_number}\n\n"
            "❌ لا توجد مواعيد مسجلة لهذا النوع حالياً.",
            reply_markup=exam_results_keyboard(
                stage_id,
                user_id,
            ),
        )
        return

    lines = [
        f"📋 مواعيد امتحانات المرحلة {stage_number}",
        "",
    ]

    for exam in exams:
        subject_data = exam.get("subjects")

        subject_name = None

        if isinstance(subject_data, dict):
            subject_name = subject_data.get("name")

        title = exam.get("title") or "امتحان"

        lines.append(
            f"{format_exam_type(exam.get('exam_type'))}"
            f" — {title}"
        )

        if subject_name:
            lines.append(
                f"📘 المادة: {subject_name}"
            )

        lines.append(
            "📅 التاريخ: "
            f"{format_date(exam.get('exam_date'))}"
        )

        time_value = format_time(
            exam.get("exam_time")
        )

        if time_value:
            lines.append(
                f"⏰ الوقت: {time_value}"
            )

        notes = exam.get("notes")

        if notes:
            lines.append(
                f"ℹ️ {notes}"
            )

        lines.append("")

    await query.edit_message_text(
        "\n".join(lines).strip(),
        reply_markup=exam_results_keyboard(
            stage_id,
            user_id,
        ),
    )


# ============================================================
# Student: locked stage
# ============================================================

async def exam_locked(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    data = query.data or ""
    parts = data.split(":")

    if len(parts) != 3 or parts[0] != "exam_locked":
        await query.answer(
            invalid_selection(),
            show_alert=True,
        )
        return

    try:
        user_id = int(parts[2])
    except (TypeError, ValueError):
        await query.answer(
            invalid_selection(),
            show_alert=True,
        )
        return

    if query.from_user.id != user_id:
        await query.answer(
            owner_error(),
            show_alert=True,
        )
        return

    await query.answer(
        "🔒 هذه المرحلة غير متاحة حالياً.",
        show_alert=True,
    )


# ============================================================
# Student: back to stages
# ============================================================

async def exam_back(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    data = query.data or ""
    parts = data.split(":")

    if len(parts) != 2 or parts[0] != "exam_back":
        await query.answer(
            invalid_selection(),
            show_alert=True,
        )
        return

    try:
        user_id = int(parts[1])
    except (TypeError, ValueError):
        await query.answer(
            invalid_selection(),
            show_alert=True,
        )
        return

    if query.from_user.id != user_id:
        await query.answer(
            owner_error(),
            show_alert=True,
        )
        return

    # مهم:
    # لا نستدعي show_exam_dates هنا لأن هذا callback
    # exam_back:user_id وليس main:exams:user_id.
    # بدلاً من ذلك نحمّل المراحل مباشرة.

    await query.answer()

    try:
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

    except Exception as exc:
        print(
            "EXAM BACK STAGES ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.edit_message_text(
            "❌ تعذر تحميل المراحل حالياً.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🏠 القائمة الرئيسية",
                        callback_data=(
                            f"back_main:{user_id}"
                        ),
                    )
                ]
            ]),
        )
        return

    if not stages:
        await query.edit_message_text(
            "📋 مواعيد الامتحانات\n\n"
            "❌ لا توجد مراحل دراسية حالياً.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🏠 القائمة الرئيسية",
                        callback_data=(
                            f"back_main:{user_id}"
                        ),
                    )
                ]
            ]),
        )
        return

    await query.edit_message_text(
        "📋 مواعيد الامتحانات\n\n"
        "اختر المرحلة الدراسية:",
        reply_markup=exam_stages_keyboard(
            stages,
            user_id,
        ),
    )
