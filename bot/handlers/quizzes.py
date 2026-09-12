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
    value = str(value or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def parse_json(value):
    if isinstance(
        value,
        (dict, list, bool, int, float),
    ):
        return value

    if value is None:
        return None

    try:
        return json.loads(value)
    except Exception:
        return value


def get_options(question):
    options = parse_json(
        question.get("options")
    )

    if isinstance(options, dict):
        return list(options.items())

    if isinstance(options, list):
        return [
            (str(index), value)
            for index, value in enumerate(options)
        ]

    return []


def get_correct_answer(question):
    return parse_json(
        question.get("correct_answer")
    )


def answer_is_correct(
    question,
    answer,
):
    """
    Compare the student's answer against the stored
    correct answer in a reliable way.

    True/False:
        callback sends true/false
        database stores true/false

    Multiple Choice:
        callback sends A/B/C/D
        database stores A/B/C/D

    Enumeration:
        student's text is compared against all required
        answers from the AI.
    """

    question_type = question.get(
        "question_type"
    )

    answer = parse_json(answer)
    correct_answer = get_correct_answer(
        question
    )

    # ========================================================
    # True / False
    # ========================================================

    if question_type == "true_false":

        student_answer = normalize(
            answer
        )

        correct = normalize(
            correct_answer
        )

        # Support both English and old Arabic values.
        aliases = {
            "true": "true",
            "صح": "true",
            "false": "false",
            "خطأ": "false",
        }

        student_answer = aliases.get(
            student_answer,
            student_answer,
        )

        correct = aliases.get(
            correct,
            correct,
        )

        return (
            student_answer == correct
            and correct in {
                "true",
                "false",
            }
        )

    # ========================================================
    # Multiple Choice
    # ========================================================

    if question_type == "multiple_choice":

        student_answer = normalize(
            answer
        )

        correct = normalize(
            correct_answer
        )

        # The callback sends the option key:
        # A / B / C / D
        #
        # The database also stores:
        # A / B / C / D
        #
        # Therefore compare the keys directly.

        return (
            student_answer == correct
            and correct in {
                "a",
                "b",
                "c",
                "d",
            }
        )

    # ========================================================
    # Enumeration
    # ========================================================

    if question_type == "enumeration":

        if isinstance(answer, list):
            student_values = answer
        else:
            student_values = re.split(
                r"[,،;\n]+",
                str(answer or ""),
            )

        student_values = {
            normalize(value)
            for value in student_values
            if normalize(value)
        }

        if isinstance(
            correct_answer,
            list,
        ):
            correct_values = correct_answer
        else:
            correct_values = [
                correct_answer
            ]

        correct_values = {
            normalize(value)
            for value in correct_values
            if normalize(value)
        }

        if not correct_values:
            return False

        return correct_values.issubset(
            student_values
        )

    return False


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

    created_rows = created.data or []

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
        stage_number = stage["stage_number"]

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

    keyboard = []

    keyboard.append([
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
    ])

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

            text = str(text or "").strip()

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
    loaded_files,
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

    return "\n\n".join(sections)


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

    # ========================================================
    # IMPORTANT:
    # Prevent double-click / duplicate generation.
    # ========================================================

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

    # Mark as generating BEFORE doing any slow operation.
    context.user_data[
        generating_key
    ] = True

    try:

        if question_count not in QUESTION_COUNTS:
            await query.answer(
                "❌ عدد الأسئلة غير صالح.",
                show_alert=True,
            )
            return

        if question_type not in QUIZ_TYPES:
            await query.answer(
                "❌ نوع الأسئلة غير صالح.",
                show_alert=True,
            )
            return

        if difficulty not in DIFFICULTIES:
            await query.answer(
                "❌ مستوى الصعوبة غير صالح.",
                show_alert=True,
            )
            return

        await query.answer(
            "🤖 جاري إعداد الاختبار بالذكاء الاصطناعي..."
        )

        # ----------------------------------------------------
        # User
        # ----------------------------------------------------

        user_id = await ensure_quiz_user(
            query.from_user,
            stage_id,
        )

        if user_id is None:
            raise RuntimeError(
                "Unable to create quiz user"
            )

        # ----------------------------------------------------
        # Load files
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Build source
        # ----------------------------------------------------

        source_text = build_source_text(
            loaded_files
        )

        # ----------------------------------------------------
        # Generate questions
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Create quiz
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Save generated questions
        # ----------------------------------------------------

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

            saved_question = question_rows[0]

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

        # ----------------------------------------------------
        # Runtime state
        # ----------------------------------------------------

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
        }

        context.user_data.pop(
            "quiz_setup",
            None,
        )

        # ----------------------------------------------------
        # Send first question
        # ----------------------------------------------------

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

        # Allow a new quiz after this generation finishes.
        context.user_data.pop(
            generating_key,
            None,
        )


# ============================================================
# Build question keyboard
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
            keyboard.append([
                InlineKeyboardButton(
                    str(value),
                    callback_data=(
                        f"quiz:answer:"
                        f"{quiz_id}:"
                        f"{index}:"
                        f"{key}:"
                        f"{owner_id}"
                    ),
                )
            ])

    elif question_type == "enumeration":

        context_key = (
            f"quiz_waiting:{quiz_id}"
        )

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

        return keyboard

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

    return keyboard


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

    keyboard = build_question_keyboard(
        state,
        question,
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
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

    question = state["questions"][
        question_index
    ]

    await query.answer()

    await save_answer(
        query.message,
        context,
        state,
        question,
        question_index,
        answer,
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

        if state.get("user_id") != str(
            user_id
        ):
            continue

        quiz_id = state["quiz_id"]

        waiting_key = (
            f"quiz_waiting:{quiz_id}"
        )

        if not context.user_data.get(
            waiting_key
        ):
            continue

        answer = (
            update.message.text or ""
        ).strip()

        if not answer:
            return True

        context.user_data.pop(
            waiting_key,
            None,
        )

        question_index = state["index"]

        question = state["questions"][
            question_index
        ]

        await save_answer(
            update.message,
            context,
            state,
            question,
            question_index,
            answer,
        )

        return True

    return False


# ============================================================
# Save answer
# ============================================================

async def save_answer(
    message,
    context,
    state,
    question,
    question_index,
    answer,
):
    # --------------------------------------------------------
    # Prevent duplicate answer submission
    # --------------------------------------------------------

    if state["index"] != question_index:
        return

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

    state["score"] += earned_points

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
                    "is_correct": correct,
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

        # Do not stop the local quiz if the answer
        # was already processed.
        pass

    state["index"] += 1

    if (
        state["index"]
        >= len(state["questions"])
    ):
        await finish_quiz(
            message,
            context,
            state,
        )
        return

    next_question = state[
        "questions"
    ][state["index"]]

    question_number = (
        state["index"] + 1
    )

    total_questions = len(
        state["questions"]
    )

    text = (
        f"🧪 Question {question_number} "
        f"of {total_questions}\n\n"
        f"{next_question.get('question_text', '')}"
    )

    next_type = next_question.get(
        "question_type"
    )

    if next_type == "enumeration":

        context.user_data[
            f"quiz_waiting:{state['quiz_id']}"
        ] = True

        text += (
            "\n\n"
            "✍️ Write your answer in English.\n"
            "You can separate the items with commas."
        )

    else:

        context.user_data.pop(
            f"quiz_waiting:{state['quiz_id']}",
            None,
        )

    keyboard = build_question_keyboard(
        state,
        next_question,
    )

    await message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# Finish
# ============================================================

async def finish_quiz(
    message,
    context,
    state,
):
    score = float(
        state["score"]
    )

    total_score = float(
        state["total_score"]
    )

    percentage = (
        score / total_score * 100
        if total_score > 0
        else 0
    )

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
                state["quiz_id"],
            )
            .execute()
        )

    except Exception as exc:
        print(
            "QUIZ RESULT SAVE ERROR:",
            type(exc).__name__,
            exc,
        )

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
        f"{percentage:.0f}%\n\n"
        f"{result_text}\n\n"
        "💾 تم حفظ محاولة الاختبار."
    )

    await message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🧪 اختبار جديد",
                    callback_data=(
                        f"main:quizzes:"
                        f"{state['user_id']}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 القائمة الرئيسية",
                    callback_data=(
                        f"back_main:"
                        f"{state['user_id']}"
                    ),
                )
            ],
        ]),
    )

    context.user_data.pop(
        f"quiz:{state['quiz_id']}",
        None,
    )

    context.user_data.pop(
        f"quiz_waiting:{state['quiz_id']}",
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
        "cancel": cancel_quiz,
        "locked": quiz_locked,
        "subject_locked": quiz_subject_locked,
    }

    handler = handlers.get(action)

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
