import json
import random
import re

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from bot.database.client import supabase


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
    return str(query.from_user.id) == str(owner_id)


def normalize(value):
    value = str(value or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def parse_json(value):
    if isinstance(value, (dict, list, bool, int, float)):
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


def get_correct_values(question):
    correct_answer = parse_json(
        question.get("correct_answer")
    )

    if isinstance(correct_answer, list):
        return correct_answer

    if isinstance(correct_answer, dict):
        return list(correct_answer.values())

    return [correct_answer]


def answer_is_correct(question, answer):
    answer = parse_json(answer)

    correct_values = get_correct_values(question)

    normalized_correct = {
        normalize(value)
        for value in correct_values
    }

    if isinstance(answer, list):
        normalized_answer = {
            normalize(value)
            for value in answer
        }

        return normalized_answer == normalized_correct

    return normalize(answer) in normalized_correct


def main_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🏠 القائمة الرئيسية",
                callback_data=f"back_main:{user_id}",
            )
        ]
    ])


def quizzes_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📚 اختيار المرحلة",
                callback_data=f"quiz:stages:{user_id}",
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
            .eq("id", user["id"])
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

    if query is None or query.from_user is None:
        return

    user_id = query.from_user.id

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
                    f"quiz:type:"
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
                    f"quiz:type:"
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
# Question type
# ============================================================

async def show_quiz_types(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

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

    keyboard = [
        [
            InlineKeyboardButton(
                "☑️ صح / خطأ",
                callback_data=(
                    f"quiz:difficulty:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"{section}:"
                    f"true_false:"
                    f"{owner_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "🔘 اختيار من متعدد",
                callback_data=(
                    f"quiz:difficulty:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"{section}:"
                    f"multiple_choice:"
                    f"{owner_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "🔢 تعداد",
                callback_data=(
                    f"quiz:difficulty:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"{section}:"
                    f"enumeration:"
                    f"{owner_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 رجوع للقسم",
                callback_data=(
                    f"quiz:section:"
                    f"{stage_id}:"
                    f"{subject_id}:"
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
        "اختر نوع الأسئلة:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# Difficulty
# ============================================================

async def show_quiz_difficulties(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

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
    question_type = parts[5]
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
                f"quiz:type:"
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
    question_type = parts[5]
    difficulty = parts[6]
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

    for count in QUESTION_COUNTS:
        keyboard.append([
            InlineKeyboardButton(
                f"📝 {count} أسئلة",
                callback_data=(
                    f"quiz:start:"
                    f"{stage_id}:"
                    f"{subject_id}:"
                    f"{section}:"
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
# Start quiz
# ============================================================

async def start_quiz(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    parts = query.data.split(":")

    if len(parts) != 9:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    stage_id = int(parts[2])
    subject_id = int(parts[3])
    section = parts[4]
    question_type = parts[5]
    difficulty = parts[6]
    question_count = int(parts[7])
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

    if question_count not in QUESTION_COUNTS:
        await query.answer(
            "❌ عدد الأسئلة غير صالح.",
            show_alert=True,
        )
        return

    try:
        user_id = await ensure_quiz_user(
            query.from_user,
            stage_id,
        )

        if user_id is None:
            raise RuntimeError(
                "Unable to create quiz user"
            )

        files_result = (
            supabase
            .table("files")
            .select("id")
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
            .execute()
        )

        files = files_result.data or []

        file_ids = [
            row["id"]
            for row in files
        ]

        if not file_ids:
            await query.answer(
                "❌ لا توجد ملفات بهذا القسم حالياً.",
                show_alert=True,
            )
            return

        questions_result = (
            supabase
            .table("questions")
            .select(
                "id, file_id, question_type, "
                "question_text, options, "
                "correct_answer, explanation, "
                "difficulty, points"
            )
            .in_(
                "file_id",
                file_ids,
            )
            .eq(
                "question_type",
                question_type,
            )
            .eq(
                "difficulty",
                difficulty,
            )
            .execute()
        )

        questions = (
            questions_result.data or []
        )

        if len(questions) < question_count:
            await query.answer(
                "⚠️ عدد الأسئلة المتوفرة حالياً "
                f"{len(questions)} فقط.",
                show_alert=True,
            )
            return

        selected_questions = random.sample(
            questions,
            question_count,
        )

        total_score = sum(
            float(
                question.get("points") or 1
            )
            for question in selected_questions
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

        for order, question in enumerate(
            selected_questions,
            start=1,
        ):
            (
                supabase
                .table("quiz_questions")
                .insert({
                    "quiz_id": quiz_id,
                    "question_id": question["id"],
                    "question_order": order,
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
            "question_type": question_type,
            "difficulty": difficulty,
            "questions": selected_questions,
            "index": 0,
            "score": 0.0,
            "total_score": total_score,
            "user_id": owner_id,
        }

        await query.answer()

        await send_current_question(
            query,
            context,
            quiz_id,
        )

    except Exception as exc:
        print(
            "QUIZ START ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ حدث خطأ أثناء إنشاء الاختبار.",
            show_alert=True,
        )


# ============================================================
# Send question
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

    question = questions[index]

    question_number = index + 1
    total_questions = len(questions)

    text = (
        f"🧪 السؤال {question_number} "
        f"من {total_questions}\n\n"
        f"{question.get('question_text', '')}"
    )

    keyboard = []

    question_type = question.get(
        "question_type"
    )

    if question_type == "true_false":
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ صح",
                    callback_data=(
                        f"quiz:answer:"
                        f"{quiz_id}:"
                        f"{index}:"
                        f"true:"
                        f"{query.from_user.id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ خطأ",
                    callback_data=(
                        f"quiz:answer:"
                        f"{quiz_id}:"
                        f"{index}:"
                        f"false:"
                        f"{query.from_user.id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 إنهاء الاختبار",
                    callback_data=(
                        f"quiz:cancel:"
                        f"{quiz_id}:"
                        f"{query.from_user.id}"
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
                        f"{query.from_user.id}"
                    ),
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "🏠 إنهاء الاختبار",
                callback_data=(
                    f"quiz:cancel:"
                    f"{quiz_id}:"
                    f"{query.from_user.id}"
                ),
            )
        ])

    elif question_type == "enumeration":
        text += (
            "\n\n"
            "✍️ اكتب إجابتك برسالة نصية."
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "🏠 إنهاء الاختبار",
                    callback_data=(
                        f"quiz:cancel:"
                        f"{quiz_id}:"
                        f"{query.from_user.id}"
                    ),
                )
            ]
        ]

        context.user_data[
            f"quiz_waiting:{quiz_id}"
        ] = True

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# Answer
# ============================================================

async def quiz_answer(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

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

        if not isinstance(state, dict):
            continue

        if state.get("user_id") != str(user_id):
            continue

        quiz_id = state["quiz_id"]

        waiting_key = (
            f"quiz_waiting:{quiz_id}"
        )

        if not context.user_data.get(
            waiting_key
        ):
            continue

        answer = update.message.text.strip()

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
        else 0
    )

    state["score"] += earned_points

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

    question = state["questions"][
        state["index"]
    ]

    text = (
        f"🧪 السؤال "
        f"{state['index'] + 1} "
        f"من "
        f"{len(state['questions'])}"
        "\n\n"
        f"{question.get('question_text', '')}"
    )

    keyboard = []

    question_type = question.get(
        "question_type"
    )

    if question_type == "true_false":
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ صح",
                    callback_data=(
                        f"quiz:answer:"
                        f"{state['quiz_id']}:"
                        f"{state['index']}:"
                        f"true:"
                        f"{state['user_id']}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ خطأ",
                    callback_data=(
                        f"quiz:answer:"
                        f"{state['quiz_id']}:"
                        f"{state['index']}:"
                        f"false:"
                        f"{state['user_id']}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 إنهاء الاختبار",
                    callback_data=(
                        f"quiz:cancel:"
                        f"{state['quiz_id']}:"
                        f"{state['user_id']}"
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
                        f"{state['quiz_id']}:"
                        f"{state['index']}:"
                        f"{key}:"
                        f"{state['user_id']}"
                    ),
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "🏠 إنهاء الاختبار",
                callback_data=(
                    f"quiz:cancel:"
                    f"{state['quiz_id']}:"
                    f"{state['user_id']}"
                ),
            )
        ])

    elif question_type == "enumeration":
        text += (
            "\n\n"
            "✍️ اكتب إجابتك برسالة نصية."
        )

        context.user_data[
            f"quiz_waiting:{state['quiz_id']}"
        ] = True

        keyboard = [
            [
                InlineKeyboardButton(
                    "🏠 إنهاء الاختبار",
                    callback_data=(
                        f"quiz:cancel:"
                        f"{state['quiz_id']}:"
                        f"{state['user_id']}"
                    ),
                )
            ]
        ]

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
    score = state["score"]
    total_score = state["total_score"]

    percentage = (
        score / total_score * 100
        if total_score
        else 0
    )

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

    if percentage >= 90:
        result_icon = "🏆"
        result_text = "ممتاز جداً!"
    elif percentage >= 75:
        result_icon = "🎉"
        result_text = "نتيجة ممتازة!"
    elif percentage >= 50:
        result_icon = "👍"
        result_text = "جيد، استمر بالمراجعة!"
    else:
        result_icon = "📚"
        result_text = "راجع المادة وحاول مرة ثانية."

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
        "type": show_quiz_types,
        "difficulty": show_quiz_difficulties,
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
