from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from bot.database.client import supabase


DAILY_POINT_LIMIT = 100
LEADERBOARD_LIMIT = 10


def owner_error():
    return (
        "⛔ هذا الاختيار مو إلك.\n"
        "استخدم /start حتى تحصل على قائمتك الخاصة."
    )


def check_owner(query, owner_id):
    if query is None or query.from_user is None:
        return False

    return str(query.from_user.id) == str(owner_id)


def leaderboard_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔙 رجوع للاختبارات",
                callback_data=f"main:quizzes:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 القائمة الرئيسية",
                callback_data=f"back_main:{user_id}",
            )
        ],
    ])


def calculate_quiz_base_points(
    difficulty,
    question_count,
):
    difficulty_points = {
        "easy": 1,
        "medium": 2,
        "hard": 3,
    }

    count_bonus = {
        1: 0,
        5: 2,
        10: 5,
    }

    per_question = difficulty_points.get(
        difficulty,
        1,
    )

    bonus = count_bonus.get(
        int(question_count),
        0,
    )

    return (
        per_question * int(question_count)
    ) + bonus


def get_user_daily_points(
    user_id,
):
    result = (
        supabase
        .table("leaderboard_points")
        .select("points")
        .eq(
            "user_id",
            user_id,
        )
        .eq(
            "point_date",
            "now()::date",
        )
        .execute()
    )

    rows = result.data or []

    return sum(
        int(row.get("points") or 0)
        for row in rows
    )


def award_quiz_points(
    user_id,
    quiz_id,
    difficulty,
    question_count,
):
    existing = (
        supabase
        .table("leaderboard_points")
        .select(
            "id, points"
        )
        .eq(
            "quiz_id",
            quiz_id,
        )
        .limit(1)
        .execute()
    )

    if existing.data:
        return int(
            existing.data[0].get("points") or 0
        )

    base_points = calculate_quiz_base_points(
        difficulty,
        question_count,
    )

    daily_result = (
        supabase
        .table("leaderboard_points")
        .select("points")
        .eq(
            "user_id",
            user_id,
        )
        .execute()
    )

    daily_rows = daily_result.data or []

    daily_points = sum(
        int(row.get("points") or 0)
        for row in daily_rows
    )

    remaining = max(
        DAILY_POINT_LIMIT - daily_points,
        0,
    )

    awarded_points = min(
        base_points,
        remaining,
    )

    (
        supabase
        .table("leaderboard_points")
        .insert({
            "user_id": user_id,
            "quiz_id": quiz_id,
            "points": awarded_points,
        })
        .execute()
    )

    return awarded_points


async def show_leaderboard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    owner_id = parts[2]

    if not check_owner(
        query,
        owner_id,
    ):
        await query.answer(
            owner_error(),
            show_alert=True,
        )
        return

    try:
        result = (
            supabase
            .table("leaderboard_points")
            .select(
                "user_id, points, users("
                "username, first_name"
                ")"
            )
            .execute()
        )

        rows = result.data or []

        totals = {}

        for row in rows:
            user_id = row.get("user_id")

            if user_id is None:
                continue

            points = int(
                row.get("points") or 0
            )

            if user_id not in totals:
                totals[user_id] = {
                    "points": 0,
                    "username": None,
                    "first_name": None,
                }

            totals[user_id]["points"] += points

            user_data = row.get("users")

            if isinstance(
                user_data,
                dict,
            ):
                totals[user_id][
                    "username"
                ] = user_data.get(
                    "username"
                )

                totals[user_id][
                    "first_name"
                ] = user_data.get(
                    "first_name"
                )

        ranking = sorted(
            totals.values(),
            key=lambda item: item["points"],
            reverse=True,
        )[:LEADERBOARD_LIMIT]

        if not ranking:
            text = (
                "🏆 قائمة المتصدرين\n\n"
                "لا توجد نقاط مسجلة حالياً.\n\n"
                "ابدأ أول اختبار وكن أول متصدر!"
            )

        else:
            lines = [
                "🏆 قائمة المتصدرين",
                "",
                "أفضل 10 طلاب حسب مجموع النقاط:",
                "",
            ]

            medals = [
                "🥇",
                "🥈",
                "🥉",
            ]

            for index, student in enumerate(
                ranking,
                start=1,
            ):
                username = student.get(
                    "username"
                )

                first_name = student.get(
                    "first_name"
                )

                if username:
                    display_name = (
                        f"@{username}"
                    )

                elif first_name:
                    display_name = str(
                        first_name
                    )

                else:
                    display_name = (
                        "طالب"
                    )

                if index <= 3:
                    prefix = medals[index - 1]
                else:
                    prefix = f"{index}."

                lines.append(
                    f"{prefix} {display_name} — "
                    f"{student['points']} نقطة"
                )

            text = "\n".join(lines)

        await query.answer()

        await query.edit_message_text(
            text,
            reply_markup=leaderboard_keyboard(
                query.from_user.id
            ),
        )

    except Exception as exc:
        print(
            "LEADERBOARD ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ حدث خطأ أثناء تحميل قائمة المتصدرين.",
            show_alert=True,
        )
