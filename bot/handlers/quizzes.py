import json
import re

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from bot.database.client import supabase
from bot.services.file_text import (
    download_telegram_file,
    extract_text_from_bytes,
)
from bot.services.ai_quiz import (
    AIQuizError,
    generate_questions,
)


QUIZ_TYPES = {
    "true_false": "☑️ صح / خطأ",
    "multiple_choice": "🔘 اختيار من متعدد",
    "enumeration": "🔢 تعداد",
}

DIFFICULTIES = {
    "easy": "🟢 سهل",
    "medium": "🟡 متوسط",
    "hard": "🔴 صعب",
}

SECTIONS = {
    "theoretical": "📖 النظري",
    "practical": "🧪 العملي",
}

QUESTION_COUNTS = (1, 5, 10)


# ============================================================
# Helpers
# ============================================================

def owner_error():
    return (
        "⛔ هذا الاختيار مو إلك.\n"
        "استخدم /start حتى تحصل على قائمتك الخاصة."
    )


def check_owner(query, owner_id):
    if query is None or query.from_user is None:
        return False

    return str(query.from_user.id) == str(owner_id)


def normalize(value):
    """
    General normalization used for comparisons.

    Keeps English content intact while removing:
    - extra spaces
    - surrounding punctuation
    - case differences
    """

    if value is None:
        return ""

    value = str(value).strip().lower()

    value = value.replace("\u200b", "")
    value = value.replace("\ufeff", "")

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_key(value):
    """
    Normalize MCQ answer keys.

    Examples:
        A
        a
        A.
        A)
        (A)
        option A
    all become:
        a
    """

    value = normalize(value)

    value = re.sub(
        r"^(?:option|choice)\s*",
        "",
        value,
    )

    value = re.sub(
        r"^[\(\[\{]\s*",
        "",
        value,
    )

    value = re.sub(
        r"[\)\]\}\.\:\-]\s*$",
        "",
        value,
    )

    value = value.strip()

    if value in {"a", "b", "c", "d"}:
        return value

    return value


def parse_json(value):
    if isinstance(
        value,
        (
            dict,
            list,
            bool,
            int,
            float,
        ),
    ):
        return value

    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return ""

        try:
            return json.loads(value)
        except Exception:
            return value

    return value


def get_options(question):
    options = parse_json(
        question.get("options")
    )

    if isinstance(options, dict):
        return [
            (
                str(key),
                str(value),
            )
            for key, value in options.items()
        ]

    if isinstance(options, list):
        return [
            (
                str(index),
                str(value),
            )
            for index, value in enumerate(options)
        ]

    return []


def get_correct_answer(question):
    return parse_json(
        question.get("correct_answer")
    )


def extract_correct_scalar(value):
    """
    Extract the actual answer from common JSON shapes.

    Supports:
        "A"
        {"answer": "A"}
        {"correct_answer": "A"}
        {"correct": "A"}
        ["A"]
    """

    value = parse_json(value)

    if isinstance(value, dict):

        preferred_keys = (
            "answer",
            "correct_answer",
            "correct",
            "value",
            "key",
        )

        for key in preferred_keys:
            if key in value:
                return extract_correct_scalar(
                    value[key]
                )

        if len(value) == 1:
            only_value = next(
                iter(value.values())
            )

            return extract_correct_scalar(
                only_value
            )

        return ""

    if isinstance(value, list):

        if len(value) == 1:
            return extract_correct_scalar(
                value[0]
            )

        return ""

    return value


def format_correct_answer(question):
    correct = get_correct_answer(question)

    if isinstance(correct, dict):

        scalar = extract_correct_scalar(
            correct
        )

        if scalar not in (
            None,
            "",
        ):
            # For MCQ, convert key to the
            # actual option text.
            if question.get(
                "question_type"
            ) == "multiple_choice":

                key = normalize_key(
                    scalar
                )

                for option_key, option_value in get_options(
                    question
                ):
                    if normalize_key(
                        option_key
                    ) == key:
                        return (
                            f"{option_key.upper()}: "
                            f"{option_value}"
                        )

            return str(scalar)

        return ", ".join(
            f"{key}: {value}"
            for key, value in correct.items()
        )

    if isinstance(correct, list):
        return ", ".join(
            str(value)
            for value in correct
        )

    if correct is True:
        return "True"

    if correct is False:
        return "False"

    return str(correct or "")


def normalize_true_false(value):
    value = normalize(value)

    aliases = {
        "true": "true",
        "t": "true",
        "yes": "true",
        "صح": "true",
        "صحيح": "true",

        "false": "false",
        "f": "false",
        "no": "false",
        "خطأ": "false",
        "خطا": "false",
        "خاطئ": "false",
    }

    return aliases.get(
        value,
        value,
    )


def resolve_mcq_key(
    question,
    value,
):
    """
    Convert any MCQ answer representation
    into A/B/C/D.

    Supports:
        A
        a
        A.
        A)
        option A
        actual option text
    """

    value = parse_json(value)

    if isinstance(value, dict):
        value = extract_correct_scalar(
            value
        )

    if isinstance(value, list):

        if len(value) == 1:
            value = value[0]
        else:
            return ""

    normalized_value = normalize_key(
        value
    )

    if normalized_value in {
        "a",
        "b",
        "c",
        "d",
    }:
        return normalized_value

    # If AI/database stores the actual
    # option text instead of its key.
    normalized_text = normalize(
        value
    )

    for key, option_text in get_options(
        question
    ):

        if normalized_text == normalize(
            option_text
        ):
            return normalize_key(key)

    return normalized_value


def split_enumeration_answer(value):
    """
    Convert enumeration answer into
    normalized individual items.
    """

    value = parse_json(value)

    if isinstance(value, dict):

        value = list(
            value.values()
        )

    if isinstance(value, list):

        values = value

    else:

        values = re.split(
            r"[,،;؛\n]+",
            str(value or ""),
        )

    result = set()

    for item in values:

        item = str(item or "").strip()

        if not item:
            continue

        # Remove common list numbering:
        # 1.
        # 2)
        # -
        # •
        item = re.sub(
            r"^\s*(?:\d+[\.\)]|[-•*])\s*",
            "",
            item,
        )

        item = normalize(item)

        if item:
            result.add(item)

    return result


def answer_is_correct(
    question,
    answer,
):
    """
    Reliable answer comparison.

    True / False:
        Normalized semantic comparison.

    Multiple Choice:
        Compare the actual A/B/C/D key.
        Also accepts the option text itself.

    Enumeration:
        Compare normalized required items.
    """

    question_type = question.get(
        "question_type"
    )

    correct_answer = get_correct_answer(
        question
    )

    # ========================================================
    # True / False
    # ========================================================

    if question_type == "true_false":

        student = normalize_true_false(
            answer
        )

        correct = normalize_true_false(
            extract_correct_scalar(
                correct_answer
            )
        )

        return (
            student in {
                "true",
                "false",
            }
            and student == correct
        )

    # ========================================================
    # Multiple Choice
    # ========================================================

    if question_type == "multiple_choice":

        student_key = resolve_mcq_key(
            question,
            answer,
        )

        correct_key = resolve_mcq_key(
            question,
            correct_answer,
        )

        return (
            student_key in {
                "a",
                "b",
                "c",
                "d",
            }
            and correct_key in {
                "a",
                "b",
                "c",
                "d",
            }
            and student_key == correct_key
        )

    # ========================================================
    # Enumeration
    # ========================================================

    if question_type == "enumeration":

        student_values = (
            split_enumeration_answer(
                answer
            )
        )

        correct_values = (
            split_enumeration_answer(
                correct_answer
            )
        )

        if not correct_values:
            return False

        # Require all correct items.
        return correct_values.issubset(
            student_values
        )

    return False


def build_feedback_text(
    question,
    correct,
):
    if correct:

        return (
            "✅ Correct!\n\n"
            "Your answer is correct."
        )

    correct_answer = format_correct_answer(
        question
    )

    return (
        "❌ Incorrect!\n\n"
        f"Correct answer: {correct_answer}"
    )


# ============================================================
# Keyboards
# ============================================================

def main_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🏠 القائمة الرئيسية",
                callback_data=(
                    f"back_main:{user_id}"
                ),
            )
        ]
    ])


def quizzes_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📚 اختيار المرحلة",
                callback_data=(
                    f"quiz:stages:{user_id}"
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
    ])


def next_question_keyboard(
    quiz_id,
    question_index,
    owner_id,
):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➡️ السؤال التالي",
                callback_data=(
                    f"quiz:next:"
                    f"{quiz_id}:"
                    f"{question_index}:"
                    f"{owner_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 إنهاء الاختبار",
                callback_data=(
                    f"quiz:cancel:"
                    f"{quiz_id}:"
                    f"{owner_id}"
                ),
            )
        ],
    ])


# ============================================================
# User
# ============================================================

async def ensure_quiz_user(
    telegram_user,
    stage_id,
):
    result = (
        supabase
        .table("users")
        .select(
            "id, telegram_id, username, first_name, "
            "stage_id, is_active"
        )
        .eq(
            "telegram_id",
            telegram_user.id,
        )
        .limit(1)
        .execute()
    )

    rows = result.data or []

    payload = {
        "telegram_id": telegram_user.id,
        "username": telegram_user.username,
        "first_name": telegram_user.first_name,
        "stage_id": stage_id,
        "is_active": True,
    }

    if rows:

        user = rows[0]

        (
            supabase
            .table("users")
            .update(payload)
            .eq(
                "id",
                user["id"],
            )
            .execute()
        )

        return user["id"]

    created = (
        supabase
        .table("users")
        .insert(payload)
        .execute()
    )

    created_rows = (
        created.data or []
    )

    if not created_rows:
        return None

    return created_rows[0]["id"]


# ============================================================
# Main quiz menu
# ============================================================

async def show_quizzes(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return

    user_id = query.from_user.id

    context.user_data.pop(
        "quiz_setup",
        None,
    )

    await query.answer()

    await query.edit_message_text(
        "🧪 الاختبارات\n\n"
        "اختبر معلوماتك في مواد المرحلة الدراسية.\n\n"
        "اختر المرحلة للبدء:",
        reply_markup=quizzes_keyboard(
            user_id
        ),
    )


# ============================================================
# Stages
# ============================================================

async def show_quiz_stages(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    user_id = query.from_user.id

    stages = (
        supabase
        .table("stages")
        .select(
            "id, stage_number, is_active"
        )
        .order("stage_number")
        .execute()
        .data
        or []
    )

    keyboard = []

    for stage in stages:

        stage_id = stage["id"]
        stage_number = stage[
            "stage_number"
        ]

        if stage.get("is_active"):

            keyboard.append([
                InlineKeyboardButton(
                    f"📚 المرحلة {stage_number}",
                    callback_data=(
                        f"quiz:subjects:"
                        f"{stage_id}:"
                        f"{user_id}"
                    ),
                )
            ])

        else:

            keyboard.append([
                InlineKeyboardButton(
                    f"🔒 المرحلة {stage_number}",
                    callback_data=(
                        f"quiz:locked:"
                        f"{stage_id}:"
                        f"{user_id}"
                    ),
                )
            ])

    keyboard.append([
        InlineKeyboardButton(
            "🔙 رجوع",
            callback_data=(
                f"main:quizzes:{user_id}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🏠 القائمة الرئيسية",
            callback_data=(
                f"back_main:{user_id}"
            ),
        )
    ])

    await query.answer()

    await query.edit_message_text(
        "🧪 الاختبارات\n\n"
        "اختر المرحلة الدراسية:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# Subjects
# ============================================================

async def show_quiz_subjects(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    parts = query.data.split(":")

    if len(parts) != 4:

        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )

        return

    stage_id = int(parts[2])
    owner_id = parts[3]

    if not check_owner(
        query,
        owner_id,
    ):

        await query.answer(
            owner_error(),
            show_alert=True,
        )

        return

    subjects = (
        supabase
        .table("subjects")
        .select(
            "id, name, is_active, sort_order"
        )
        .eq(
            "stage_id",
            stage_id,
        )
        .order("sort_order")
        .execute()
        .data
        or []
    )

    keyboard = []

    for subject in subjects:

        subject_id = subject["id"]
        name = subject["name"]

        if subject.get("is_active"):

            keyboard.append([
                InlineKeyboardButton(
                    f"📘 {name}",
                    callback_data=(
                        f"quiz:section:"
                        f"{stage_id}:"
                        f"{subject_id}:"
                        f"{owner_id}"
                    ),
                )
            ])

        else:

            keyboard.append([
                InlineKeyboardButton(
                    f"🔒 {name}",
                    callback_data=(
                        f"quiz:subject_locked:"
                        f"{stage_id}:"
                        f"{subject_id}:"
                        f"{owner_id}"
                    ),
                )
            ])

    keyboard.append([
        InlineKeyboardButton(
            "🔙 رجوع للمراحل",
            callback_data=(
                f"quiz:stages:{owner_id}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🏠 القائمة الرئيسية",
            callback_data=(
                f"back_main:{owner_id}"
            ),
        )
    ])

    await query.answer()

    await query.edit_message_text(
        "🧪 الاختبارات\n\n"
        "اختر المادة:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# Section
# ============================================================

async def show_quiz_sections(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    parts = query.data.split(":")

    if len(parts) != 5:

        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )

        return

    stage_id = parts[2]
    subject_id = parts[3]
    owner_id = parts[4]

    if not check_owner(
        query,
        owner_id,
    ):

        await query.answer(
            owner_error(),
            show_alert=True,
        )

        return

    keyboard = [
        [
            InlineKeyboardButton(
                "📖 النظري",
                callback_data=(
                    f"quiz:files:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"theoretical:"
                    f"{owner_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "🧪 العملي",
                callback_data=(
                    f"quiz:files:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"practical:"
                    f"{owner_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 رجوع للمادة",
                callback_data=(
                    f"quiz:subjects:"
                    f"{stage_id}:"
                    f"{owner_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 القائمة الرئيسية",
                callback_data=(
                    f"back_main:{owner_id}"
                ),
            )
        ],
    ]

    await query.answer()

    await query.edit_message_text(
        "🧪 الاختبارات\n\n"
        "اختر القسم:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# Files
# ============================================================

async def show_quiz_files(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    parts = query.data.split(":")

    if len(parts) != 6:

        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )

        return

    stage_id = parts[2]
    subject_id = parts[3]
    section = parts[4]
    owner_id = parts[5]

    if not check_owner(
        query,
        owner_id,
    ):

        await query.answer(
            owner_error(),
            show_alert=True,
        )

        return

    files_result = (
        supabase
        .table("files")
        .select(
            "id, name, description, "
            "telegram_file_id, file_type, "
            "file_size, sort_order"
        )
        .eq(
            "subject_id",
            int(subject_id),
        )
        .eq(
            "section_type",
            section,
        )
        .eq(
            "is_active",
            True,
        )
        .is_(
            "deleted_at",
            "null",
        )
        .order("sort_order")
        .execute()
    )

    files = files_result.data or []

    if not files:

        await query.answer(
            "❌ لا توجد ملفات بهذا القسم حالياً.",
            show_alert=True,
        )

        return

    keyboard = [
        [
            InlineKeyboardButton(
                "📚 اختبار شامل من كل الملفات",
                callback_data=(
                    f"quiz:source:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"{section}:"
                    f"all:"
                    f"{owner_id}"
                ),
            )
        ]
    ]

    for file in files:

        file_id = file["id"]

        file_name = (
            file.get("name")
            or f"ملف {file_id}"
        )

        keyboard.append([
            InlineKeyboardButton(
                f"📄 {file_name}",
                callback_data=(
                    f"quiz:source:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"{section}:"
                    f"{file_id}:"
                    f"{owner_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "🔙 رجوع للقسم",
            callback_data=(
                f"quiz:section:"
                f"{stage_id}:"
                f"{subject_id}:"
                f"{owner_id}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🏠 القائمة الرئيسية",
            callback_data=(
                f"back_main:{owner_id}"
            ),
        )
    ])

    await query.answer()

    await query.edit_message_text(
        "🧪 الاختبارات\n\n"
        f"{SECTIONS.get(section, section)}\n\n"
        "اختر مصدر الأسئلة:\n\n"
        "📚 الاختبار الشامل يستخدم جميع ملفات "
        "هذا القسم.\n"
        "📄 أو اختر ملفاً واحداً لإنشاء الاختبار "
        "منه فقط.",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# Source
# ============================================================

async def show_quiz_source(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    parts = query.data.split(":")

    if len(parts) != 7:

        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )

        return

    stage_id = parts[2]
    subject_id = parts[3]
    section = parts[4]
    source = parts[5]
    owner_id = parts[6]

    if not check_owner(
        query,
        owner_id,
    ):

        await query.answer(
            owner_error(),
            show_alert=True,
        )

        return

    context.user_data[
        "quiz_setup"
    ] = {
        "stage_id": int(stage_id),
        "subject_id": int(subject_id),
        "section": section,
        "source": source,
        "owner_id": str(owner_id),
    }

    keyboard = []

    for quiz_type, title in QUIZ_TYPES.items():

        keyboard.append([
            InlineKeyboardButton(
                title,
                callback_data=(
                    f"quiz:difficulty:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"{section}:"
                    f"{source}:"
                    f"{quiz_type}:"
                    f"{owner_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "🔙 رجوع للملفات",
            callback_data=(
                f"quiz:files:"
                f"{stage_id}:"
                f"{subject_id}:"
                f"{section}:"
                f"{owner_id}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🏠 القائمة الرئيسية",
            callback_data=(
                f"back_main:{owner_id}"
            ),
        )
    ])

    await query.answer()

    source_text = (
        "📚 جميع ملفات القسم"
        if source == "all"
        else "📄 الملف المحدد"
    )

    await query.edit_message_text(
        "🧪 الاختبارات\n\n"
        f"{source_text}\n\n"
        "اختر نوع الأسئلة:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# Question type / Difficulty
# ============================================================

async def show_quiz_types(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    parts = query.data.split(":")

    if len(parts) != 8:

        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )

        return

    stage_id = parts[2]
    subject_id = parts[3]
    section = parts[4]
    source = parts[5]
    question_type = parts[6]
    owner_id = parts[7]

    if not check_owner(
        query,
        owner_id,
    ):

        await query.answer(
            owner_error(),
            show_alert=True,
        )

        return

    keyboard = []

    for difficulty, title in DIFFICULTIES.items():

        keyboard.append([
            InlineKeyboardButton(
                title,
                callback_data=(
                    f"quiz:count:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"{section}:"
                    f"{source}:"
                    f"{question_type}:"
                    f"{difficulty}:"
                    f"{owner_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "🔙 رجوع لنوع الأسئلة",
            callback_data=(
                f"quiz:difficulty:"
                f"{stage_id}:"
                f"{subject_id}:"
                f"{section}:"
                f"{source}:"
                f"{question_type}:"
                f"{owner_id}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🏠 القائمة الرئيسية",
            callback_data=(
                f"back_main:{owner_id}"
            ),
        )
    ])

    await query.answer()

    await query.edit_message_text(
        "🧪 الاختبارات\n\n"
        "اختر مستوى الصعوبة:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# Question count
# ============================================================

async def show_quiz_counts(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    parts = query.data.split(":")

    if len(parts) != 9:

        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )

        return

    stage_id = parts[2]
    subject_id = parts[3]
    section = parts[4]
    source = parts[5]
    question_type = parts[6]
    difficulty = parts[7]
    owner_id = parts[8]

    if not check_owner(
        query,
        owner_id,
    ):

        await query.answer(
            owner_error(),
            show_alert=True,
        )

        return

    keyboard = []

    for count in QUESTION_COUNTS:

        keyboard.append([
            InlineKeyboardButton(
                f"📝 {count} أسئلة",
                callback_data=(
                    f"quiz:start:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"{section}:"
                    f"{source}:"
                    f"{question_type}:"
                    f"{difficulty}:"
                    f"{count}:"
                    f"{owner_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "🔙 رجوع للصعوبة",
            callback_data=(
                f"quiz:difficulty:"
                f"{stage_id}:"
                f"{subject_id}:"
                f"{section}:"
                f"{source}:"
                f"{question_type}:"
                f"{owner_id}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🏠 القائمة الرئيسية",
            callback_data=(
                f"back_main:{owner_id}"
            ),
        )
    ])

    await query.answer()

    await query.edit_message_text(
        "🧪 الاختبارات\n\n"
        "كم سؤال تريد؟",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# Load source files
# ============================================================

async def load_quiz_source_files(
    telegram_bot,
    subject_id,
    section,
    source,
):
    query = (
        supabase
        .table("files")
        .select(
            "id, name, description, "
            "telegram_file_id, file_type, "
            "file_size, sort_order"
        )
        .eq(
            "subject_id",
            subject_id,
        )
        .eq(
            "section_type",
            section,
        )
        .eq(
            "is_active",
            True,
        )
        .is_(
            "deleted_at",
            "null",
        )
        .order("sort_order")
        .execute()
    )

    files = query.data or []

    if source != "all":

        files = [
            file
            for file in files
            if str(file["id"]) == str(source)
        ]

    if not files:
        return []

    loaded = []

    for file in files:

        telegram_file_id = file.get(
            "telegram_file_id"
        )

        if not telegram_file_id:
            continue

        try:

            data = await download_telegram_file(
                telegram_bot,
                telegram_file_id,
            )

            text = extract_text_from_bytes(
                data=data,
                file_type=file.get(
                    "file_type"
                ),
                file_name=file.get(
                    "name"
                ),
            )

            text = str(
                text or ""
            ).strip()

            if not text:
                continue

            loaded.append({
                "id": file["id"],
                "name": (
                    file.get("name")
                    or f"ملف {file['id']}"
                ),
                "text": text,
            })

        except Exception as exc:

            print(
                "QUIZ FILE LOAD ERROR:",
                file.get("id"),
                type(exc).__name__,
                exc,
            )

    return loaded


def build_source_text(
    loaded_files
):
    sections = []

    for index, file in enumerate(
        loaded_files,
        start=1,
    ):

        sections.append(
            "==================================================\n"
            f"SOURCE FILE {index}\n"
            f"FILE ID: {file['id']}\n"
            f"FILE NAME: {file['name']}\n"
            "==================================================\n"
            f"{file['text']}"
        )

    return "\n\n".join(
        sections
    )


# ============================================================
# Start quiz
# ============================================================

async def start_quiz(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    parts = query.data.split(":")

    if len(parts) != 10:

        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )

        return

    stage_id = int(parts[2])
    subject_id = int(parts[3])
    section = parts[4]
    source = parts[5]
    question_type = parts[6]
    difficulty = parts[7]
    question_count = int(parts[8])
    owner_id = parts[9]

    if not check_owner(
        query,
        owner_id,
    ):

        await query.answer(
            owner_error(),
            show_alert=True,
        )

        return

    generating_key = (
        f"quiz_generating:{owner_id}"
    )

    if context.user_data.get(
        generating_key
    ):

        await query.answer(
            "⏳ الاختبار قيد الإنشاء، انتظر قليلاً.",
            show_alert=True,
        )

        return

    if context.user_data.get(
        f"quiz_active:{owner_id}"
    ):

        await query.answer(
            "⚠️ لديك اختبار قيد التنفيذ حالياً.",
            show_alert=True,
        )

        return

    context.user_data[
        generating_key
    ] = True

    await query.answer(
        "🤖 جاري إنشاء الاختبار..."
    )

    try:

        if question_count not in QUESTION_COUNTS:
            raise ValueError(
                "Invalid question count"
            )

        if question_type not in QUIZ_TYPES:
            raise ValueError(
                "Invalid question type"
            )

        if difficulty not in DIFFICULTIES:
            raise ValueError(
                "Invalid difficulty"
            )

        await query.edit_message_text(
            "🤖 جاري إنشاء الاختبار...\n\n"
            "⏳ يتم الآن قراءة الملفات وتحضير الأسئلة.\n"
            "لا تحتاج تضغط أي شيء، انتظر فقط..."
        )

        user_id = await ensure_quiz_user(
            query.from_user,
            stage_id,
        )

        if user_id is None:
            raise RuntimeError(
                "Unable to create quiz user"
            )

        loaded_files = (
            await load_quiz_source_files(
                context.bot,
                subject_id,
                section,
                source,
            )
        )

        if not loaded_files:

            await query.edit_message_text(
                "❌ ما گدرت ألقى محتوى قابل للقراءة "
                "ضمن الملفات المحددة.\n\n"
                "تأكد أن الملف موجود وأنه يحتوي "
                "على نص قابل للاستخراج.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🔙 رجوع للملفات",
                            callback_data=(
                                f"quiz:files:"
                                f"{stage_id}:"
                                f"{subject_id}:"
                                f"{section}:"
                                f"{owner_id}"
                            ),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 القائمة الرئيسية",
                            callback_data=(
                                f"back_main:{owner_id}"
                            ),
                        )
                    ],
                ]),
            )

            return

        source_text = build_source_text(
            loaded_files
        )

        generated_questions = (
            await generate_questions(
                source_text=source_text,
                question_type=question_type,
                difficulty=difficulty,
                count=question_count,
            )
        )

        if not generated_questions:

            raise AIQuizError(
                "لم يتم إنشاء أسئلة."
            )

        generated_questions = (
            generated_questions[:question_count]
        )

        if len(
            generated_questions
        ) != question_count:

            raise AIQuizError(
                "الذكاء الاصطناعي لم يُرجع العدد المطلوب "
                "من الأسئلة."
            )

        total_score = float(
            question_count
        )

        quiz_result = (
            supabase
            .table("quizzes")
            .insert({
                "user_id": user_id,
                "subject_id": subject_id,
                "section_type": section,
                "difficulty": difficulty,
                "question_count": question_count,
                "score": 0,
                "total_score": total_score,
            })
            .execute()
        )

        quiz_rows = (
            quiz_result.data or []
        )

        if not quiz_rows:

            raise RuntimeError(
                "Quiz record was not created"
            )

        quiz_id = quiz_rows[0]["id"]

        selected_questions = []

        for index, question in enumerate(
            generated_questions
        ):

            if source != "all":

                file_id = loaded_files[0]["id"]

            else:

                file_id = loaded_files[
                    index % len(loaded_files)
                ]["id"]

            question_insert = (
                supabase
                .table("questions")
                .insert({
                    "file_id": file_id,
                    "question_type": question_type,
                    "question_text": question[
                        "question_text"
                    ],
                    "options": question.get(
                        "options"
                    ),
                    "correct_answer": question.get(
                        "correct_answer"
                    ),
                    "explanation": question.get(
                        "explanation"
                    ),
                    "difficulty": difficulty,
                    "points": 1,
                })
                .execute()
            )

            question_rows = (
                question_insert.data or []
            )

            if not question_rows:

                raise RuntimeError(
                    "Generated question was not saved"
                )

            saved_question = (
                question_rows[0]
            )

            selected_questions.append(
                saved_question
            )

            (
                supabase
                .table("quiz_questions")
                .insert({
                    "quiz_id": quiz_id,
                    "question_id": (
                        saved_question["id"]
                    ),
                    "question_order": (
                        index + 1
                    ),
                })
                .execute()
            )

        context.user_data[
            f"quiz:{quiz_id}"
        ] = {
            "quiz_id": quiz_id,
            "stage_id": stage_id,
            "subject_id": subject_id,
            "section": section,
            "source": source,
            "question_type": question_type,
            "difficulty": difficulty,
            "questions": selected_questions,
            "index": 0,
            "score": 0.0,
            "total_score": total_score,
            "user_id": str(owner_id),
            "answer_lock": False,
            "waiting_next": False,
        }

        context.user_data[
            f"quiz_active:{owner_id}"
        ] = True

        context.user_data.pop(
            "quiz_setup",
            None,
        )

        await send_current_question(
            query,
            context,
            quiz_id,
        )

    except AIQuizError as exc:

        print(
            "AI QUIZ ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.edit_message_text(
            "⚠️ ما گدرت أنشئ الاختبار حالياً.\n\n"
            f"السبب: {exc}",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔄 محاولة مرة ثانية",
                        callback_data=(
                            f"quiz:start:"
                            f"{stage_id}:"
                            f"{subject_id}:"
                            f"{section}:"
                            f"{source}:"
                            f"{question_type}:"
                            f"{difficulty}:"
                            f"{question_count}:"
                            f"{owner_id}"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 رجوع للملفات",
                        callback_data=(
                            f"quiz:files:"
                            f"{stage_id}:"
                            f"{subject_id}:"
                            f"{section}:"
                            f"{owner_id}"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🏠 القائمة الرئيسية",
                        callback_data=(
                            f"back_main:{owner_id}"
                        ),
                    )
                ],
            ]),
        )

    except Exception as exc:

        print(
            "QUIZ START ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.edit_message_text(
            "❌ حدث خطأ أثناء إنشاء الاختبار.\n\n"
            "حاول مرة ثانية.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔄 محاولة مرة ثانية",
                        callback_data=(
                            f"quiz:start:"
                            f"{stage_id}:"
                            f"{subject_id}:"
                            f"{section}:"
                            f"{source}:"
                            f"{question_type}:"
                            f"{difficulty}:"
                            f"{question_count}:"
                            f"{owner_id}"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🏠 القائمة الرئيسية",
                        callback_data=(
                            f"back_main:{owner_id}"
                        ),
                    )
                ],
            ]),
        )

    finally:

        context.user_data.pop(
            generating_key,
            None,
        )


# ============================================================
# Question keyboard
# ============================================================

def build_question_keyboard(
    state,
    question,
):
    quiz_id = state["quiz_id"]
    index = state["index"]
    owner_id = state["user_id"]

    question_type = question.get(
        "question_type"
    )

    keyboard = []

    if question_type == "true_false":

        keyboard = [
            [
                InlineKeyboardButton(
                    "True",
                    callback_data=(
                        f"quiz:answer:"
                        f"{quiz_id}:"
                        f"{index}:"
                        f"true:"
                        f"{owner_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "False",
                    callback_data=(
                        f"quiz:answer:"
                        f"{quiz_id}:"
                        f"{index}:"
                        f"false:"
                        f"{owner_id}"
                    ),
                )
            ],
        ]

    elif question_type == "multiple_choice":

        for key, value in get_options(
            question
        ):

            display_key = (
                str(key).upper()
            )

            keyboard.append([
                InlineKeyboardButton(
                    f"{display_key}. {value}",
                    callback_data=(
                        f"quiz:answer:"
                        f"{quiz_id}:"
                        f"{index}:"
                        f"{display_key}:"
                        f"{owner_id}"
                    ),
                )
            ])

    elif question_type == "enumeration":

        keyboard = [
            [
                InlineKeyboardButton(
                    "🏠 إنهاء الاختبار",
                    callback_data=(
                        f"quiz:cancel:"
                        f"{quiz_id}:"
                        f"{owner_id}"
                    ),
                )
            ]
        ]

        return InlineKeyboardMarkup(
            keyboard
        )

    keyboard.append([
        InlineKeyboardButton(
            "🏠 إنهاء الاختبار",
            callback_data=(
                f"quiz:cancel:"
                f"{quiz_id}:"
                f"{owner_id}"
            ),
        )
    ])

    return InlineKeyboardMarkup(
        keyboard
    )


# ============================================================
# Send current question
# ============================================================

async def send_current_question(
    query,
    context,
    quiz_id,
):
    state = context.user_data.get(
        f"quiz:{quiz_id}"
    )

    if not state:

        await query.edit_message_text(
            "❌ انتهت جلسة الاختبار.",
            reply_markup=main_keyboard(
                query.from_user.id
            ),
        )

        return

    index = state["index"]
    questions = state["questions"]

    if index >= len(questions):

        await finish_quiz(
            query.message,
            context,
            state,
        )

        return

    question = questions[index]

    question_number = index + 1
    total_questions = len(questions)

    text = (
        f"🧪 Question {question_number} "
        f"of {total_questions}\n\n"
        f"{question.get('question_text', '')}"
    )

    question_type = question.get(
        "question_type"
    )

    if question_type == "enumeration":

        text += (
            "\n\n"
            "✍️ Write your answer in English.\n"
            "You can separate the items with commas."
        )

        context.user_data[
            f"quiz_waiting:{quiz_id}"
        ] = True

    else:

        context.user_data.pop(
            f"quiz_waiting:{quiz_id}",
            None,
        )

    state["waiting_next"] = False

    keyboard = build_question_keyboard(
        state,
        question,
    )

    await query.edit_message_text(
        text,
        reply_markup=keyboard,
    )


# ============================================================
# Answer callback
# ============================================================

async def quiz_answer(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    parts = query.data.split(":")

    if len(parts) != 6:

        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )

        return

    quiz_id = int(parts[2])
    question_index = int(parts[3])
    answer = parts[4]
    owner_id = parts[5]

    if not check_owner(
        query,
        owner_id,
    ):

        await query.answer(
            owner_error(),
            show_alert=True,
        )

        return

    state = context.user_data.get(
        f"quiz:{quiz_id}"
    )

    if not state:

        await query.answer(
            "❌ انتهت جلسة الاختبار.",
            show_alert=True,
        )

        return

    if state["index"] != question_index:

        await query.answer(
            "⚠️ هذا السؤال لم يعد فعالاً.",
            show_alert=True,
        )

        return

    if state.get("answer_lock"):

        await query.answer(
            "⏳ تم تسجيل إجابتك.",
            show_alert=True,
        )

        return

    if state.get("waiting_next"):

        await query.answer(
            "➡️ اضغط السؤال التالي.",
            show_alert=True,
        )

        return

    state["answer_lock"] = True

    try:

        question = state[
            "questions"
        ][question_index]

        correct = answer_is_correct(
            question,
            answer,
        )

        await query.answer()

        await save_answer(
            query.message,
            context,
            state,
            question,
            question_index,
            answer,
            correct=correct,
        )

    except Exception as exc:

        print(
            "QUIZ ANSWER ERROR:",
            type(exc).__name__,
            exc,
        )

        state["answer_lock"] = False

        await query.answer(
            "❌ حدث خطأ أثناء تسجيل الإجابة.",
            show_alert=True,
        )


# ============================================================
# Next question callback
# ============================================================

async def quiz_next(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    parts = query.data.split(":")

    if len(parts) != 5:

        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )

        return

    quiz_id = int(parts[2])
    previous_index = int(parts[3])
    owner_id = parts[4]

    if not check_owner(
        query,
        owner_id,
    ):

        await query.answer(
            owner_error(),
            show_alert=True,
        )

        return

    state = context.user_data.get(
        f"quiz:{quiz_id}"
    )

    if not state:

        await query.answer(
            "❌ انتهت جلسة الاختبار.",
            show_alert=True,
        )

        return

    if state["index"] != previous_index:

        await query.answer(
            "⚠️ هذا السؤال لم يعد فعالاً.",
            show_alert=True,
        )

        return

    if not state.get(
        "waiting_next"
    ):

        await query.answer(
            "⚠️ لا يوجد سؤال بانتظار الانتقال.",
            show_alert=True,
        )

        return

    await query.answer()

    state["waiting_next"] = False
    state["answer_lock"] = False

    await send_current_question(
        query,
        context,
        quiz_id,
    )


# ============================================================
# Text answer
# ============================================================

async def handle_quiz_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if (
        update.message is None
        or update.effective_user is None
    ):
        return False

    user_id = update.effective_user.id

    for key, state in list(
        context.user_data.items()
    ):

        if not key.startswith("quiz:"):
            continue

        if not isinstance(
            state,
            dict,
        ):
            continue

        if state.get(
            "user_id"
        ) != str(user_id):
            continue

        quiz_id = state["quiz_id"]

        waiting_key = (
            f"quiz_waiting:{quiz_id}"
        )

        if not context.user_data.get(
            waiting_key
        ):
            continue

        if state.get(
            "answer_lock"
        ):
            return True

        if state.get(
            "waiting_next"
        ):
            return True

        answer = (
            update.message.text or ""
        ).strip()

        if not answer:
            return True

        state["answer_lock"] = True

        context.user_data.pop(
            waiting_key,
            None,
        )

        question_index = state[
            "index"
        ]

        question = state[
            "questions"
        ][question_index]

        try:

            correct = answer_is_correct(
                question,
                answer,
            )

            await save_answer(
                update.message,
                context,
                state,
                question,
                question_index,
                answer,
                correct=correct,
            )

        except Exception as exc:

            print(
                "QUIZ TEXT ANSWER ERROR:",
                type(exc).__name__,
                exc,
            )

            state["answer_lock"] = False

            await update.message.reply_text(
                "❌ حدث خطأ أثناء تسجيل الإجابة.\n"
                "حاول إرسال إجابتك مرة ثانية."
            )

        return True

    return False


# ============================================================
# Save answer + feedback
# ============================================================

async def save_answer(
    message,
    context,
    state,
    question,
    question_index,
    answer,
    correct=None,
):
    if state["index"] != question_index:
        return

    if correct is None:

        correct = answer_is_correct(
            question,
            answer,
        )

    points = float(
        question.get("points") or 1
    )

    earned_points = (
        points
        if correct
        else 0.0
    )

    # ========================================================
    # Save answer FIRST.
    #
    # The database is now the source of truth.
    # ========================================================

    try:

        (
            supabase
            .table("quiz_answers")
            .upsert(
                {
                    "quiz_id": state["quiz_id"],
                    "question_id": question["id"],
                    "user_answer": parse_json(
                        answer
                    ),
                    "is_correct": bool(
                        correct
                    ),
                    "points": earned_points,
                },
                on_conflict=(
                    "quiz_id,question_id"
                ),
            )
            .execute()
        )

    except Exception as exc:

        print(
            "QUIZ ANSWER SAVE ERROR:",
            type(exc).__name__,
            exc,
        )

        # Do NOT advance the question if
        # the answer could not be recorded.
        state["answer_lock"] = False

        await message.reply_text(
            "❌ ما گدرت أحفظ إجابتك.\n"
            "حاول مرة ثانية."
        )

        return

    # ========================================================
    # Only after successful database save,
    # update runtime state.
    # ========================================================

    state["score"] += earned_points

    state["index"] += 1

    state["waiting_next"] = True

    state["answer_lock"] = False

    # ========================================================
    # Feedback
    # ========================================================

    feedback = build_feedback_text(
        question,
        correct,
    )

    # ========================================================
    # Final question:
    #
    # Show feedback FIRST.
    # Then calculate the final result
    # from database records.
    # ========================================================

    if state["index"] >= len(
        state["questions"]
    ):

        await message.reply_text(
            feedback
        )

        await finish_quiz(
            message,
            context,
            state,
        )

        return

    # ========================================================
    # Normal question
    # ========================================================

    next_index = state["index"]

    await message.reply_text(
        feedback,
        reply_markup=next_question_keyboard(
            state["quiz_id"],
            next_index,
            state["user_id"],
        ),
    )


# ============================================================
# Calculate result from database
# ============================================================

async def calculate_quiz_result(
    quiz_id,
):
    """
    Database is the source of truth.

    Returns:
        score
        total_score
        percentage
    """

    answers_result = (
        supabase
        .table("quiz_answers")
        .select(
            "is_correct, points"
        )
        .eq(
            "quiz_id",
            quiz_id,
        )
        .execute()
    )

    answers = (
        answers_result.data or []
    )

    score = 0.0

    for answer in answers:

        if answer.get(
            "is_correct"
        ):

            score += float(
                answer.get("points") or 0
            )

    quiz_result = (
        supabase
        .table("quizzes")
        .select(
            "question_count, total_score"
        )
        .eq(
            "id",
            quiz_id,
        )
        .limit(1)
        .execute()
    )

    quiz_rows = (
        quiz_result.data or []
    )

    if quiz_rows:

        quiz = quiz_rows[0]

        question_count = int(
            quiz.get(
                "question_count"
            ) or 0
        )

        stored_total = float(
            quiz.get(
                "total_score"
            ) or 0
        )

        if stored_total > 0:
            total_score = stored_total

        elif question_count > 0:
            total_score = float(
                question_count
            )

        else:
            total_score = float(
                len(answers)
            )

    else:

        total_score = float(
            len(answers)
        )

    percentage = (
        (score / total_score) * 100
        if total_score > 0
        else 0.0
    )

    return (
        score,
        total_score,
        percentage,
    )


# ============================================================
# Finish
# ============================================================

async def finish_quiz(
    message,
    context,
    state,
):
    quiz_id = state["quiz_id"]

    # ========================================================
    # IMPORTANT:
    # Calculate everything from Supabase.
    # ========================================================

    try:

        (
            score,
            total_score,
            percentage,
        ) = await calculate_quiz_result(
            quiz_id
        )

    except Exception as exc:

        print(
            "QUIZ RESULT CALCULATION ERROR:",
            type(exc).__name__,
            exc,
        )

        # Fallback only if database calculation
        # itself fails.
        score = float(
            state.get("score") or 0
        )

        total_score = float(
            state.get("total_score") or 0
        )

        percentage = (
            (score / total_score) * 100
            if total_score > 0
            else 0.0
        )

    # ========================================================
    # Save final result.
    # ========================================================

    try:

        (
            supabase
            .table("quizzes")
            .update({
                "score": score,
                "total_score": total_score,
            })
            .eq(
                "id",
                quiz_id,
            )
            .execute()
        )

    except Exception as exc:

        print(
            "QUIZ RESULT SAVE ERROR:",
            type(exc).__name__,
            exc,
        )

    # ========================================================
    # Result message
    # ========================================================

    if percentage >= 90:

        result_icon = "🏆"
        result_text = "ممتاز جداً!"

    elif percentage >= 75:

        result_icon = "🎉"
        result_text = "نتيجة ممتازة!"

    elif percentage >= 50:

        result_icon = "👍"
        result_text = (
            "جيد، استمر بالمراجعة!"
        )

    else:

        result_icon = "📚"
        result_text = (
            "راجع المادة وحاول مرة ثانية."
        )

    text = (
        f"{result_icon} انتهى الاختبار!\n\n"
        f"📊 النتيجة: "
        f"{score:g} / {total_score:g}\n"
        f"📈 النسبة: "
        f"{percentage:.1f}%\n\n"
        f"{result_text}\n\n"
        "💾 تم حفظ محاولة الاختبار."
    )

    owner_id = state["user_id"]

    await message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🧪 اختبار جديد",
                    callback_data=(
                        f"main:quizzes:"
                        f"{owner_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 القائمة الرئيسية",
                    callback_data=(
                        f"back_main:"
                        f"{owner_id}"
                    ),
                )
            ],
        ]),
    )

    # ========================================================
    # Cleanup
    # ========================================================

    context.user_data.pop(
        f"quiz:{quiz_id}",
        None,
    )

    context.user_data.pop(
        f"quiz_waiting:{quiz_id}",
        None,
    )

    context.user_data.pop(
        f"quiz_active:{owner_id}",
        None,
    )

    context.user_data.pop(
        f"quiz_generating:{owner_id}",
        None,
    )


# ============================================================
# Cancel
# ============================================================

async def cancel_quiz(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    parts = query.data.split(":")

    if len(parts) != 4:

        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )

        return

    quiz_id = int(parts[2])
    owner_id = parts[3]

    if not check_owner(
        query,
        owner_id,
    ):

        await query.answer(
            owner_error(),
            show_alert=True,
        )

        return

    context.user_data.pop(
        f"quiz:{quiz_id}",
        None,
    )

    context.user_data.pop(
        f"quiz_waiting:{quiz_id}",
        None,
    )

    context.user_data.pop(
        f"quiz_generating:{owner_id}",
        None,
    )

    context.user_data.pop(
        f"quiz_active:{owner_id}",
        None,
    )

    await query.answer(
        "تم إنهاء الاختبار."
    )

    await query.edit_message_text(
        "🧪 تم إنهاء الاختبار.\n\n"
        "يمكنك بدء اختبار جديد من القائمة.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🧪 اختبار جديد",
                    callback_data=(
                        f"main:quizzes:"
                        f"{query.from_user.id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 القائمة الرئيسية",
                    callback_data=(
                        f"back_main:"
                        f"{query.from_user.id}"
                    ),
                )
            ],
        ]),
    )


# ============================================================
# Locked
# ============================================================

async def quiz_locked(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    parts = query.data.split(":")

    if len(parts) != 4:

        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )

        return

    owner_id = parts[3]

    if not check_owner(
        query,
        owner_id,
    ):

        await query.answer(
            owner_error(),
            show_alert=True,
        )

        return

    await query.answer(
        "🔒 هذه المرحلة غير متاحة حالياً.",
        show_alert=True,
    )


async def quiz_subject_locked(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    parts = query.data.split(":")

    if len(parts) != 5:

        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )

        return

    owner_id = parts[4]

    if not check_owner(
        query,
        owner_id,
    ):

        await query.answer(
            owner_error(),
            show_alert=True,
        )

        return

    await query.answer(
        "🔒 هذه المادة غير متاحة حالياً.",
        show_alert=True,
    )


# ============================================================
# Callback router
# ============================================================

async def quiz_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return

    parts = query.data.split(":")

    if len(parts) < 2:

        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )

        return

    action = parts[1]

    handlers = {
        "stages": show_quiz_stages,
        "subjects": show_quiz_subjects,
        "section": show_quiz_sections,
        "files": show_quiz_files,
        "source": show_quiz_source,
        "difficulty": show_quiz_types,
        "count": show_quiz_counts,
        "start": start_quiz,
        "answer": quiz_answer,
        "next": quiz_next,
        "cancel": cancel_quiz,
        "locked": quiz_locked,
        "subject_locked": quiz_subject_locked,
    }

    handler = handlers.get(
        action
    )

    if handler is None:

        await query.answer(
            "❌ اختيار غير معروف.",
            show_alert=True,
        )

        return

    await handler(
        update,
        context,
    )
