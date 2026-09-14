from datetime import date
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes
from bot.database.client import supabase
DAILY_POINT_LIMIT = 100
LEADERBOARD_LIMIT = 10
DIFFICULTY_POINTS = {
    "easy": 1,
    "medium": 2,
    "hard": 3,
}
COUNT_BONUS = {
    1: 0,
    5: 2,
    10: 5,
}
# ============================================================
# Date
# ============================================================
def get_today():
    return date.today().isoformat()
# ============================================================
# User helpers
# ============================================================
def get_internal_user_id(
    telegram_id,
):
    """
    Convert Telegram user ID into the internal
    users.id used by leaderboard_points.
    """
    try:
        telegram_id = int(telegram_id)
    except (
        TypeError,
        ValueError,
    ):
        return None
    try:
        result = (
            supabase
            .table("users")
            .select("id")
            .eq(
                "telegram_id",
                telegram_id,
            )
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        return int(
            rows[0]["id"]
        )
    except Exception as exc:
        print(
            "LEADERBOARD USER ID ERROR:",
            type(exc).__name__,
            exc,
        )
        return None
# ============================================================
# Point calculation
# ============================================================
def calculate_quiz_base_points(
    difficulty,
    question_count,
    correct_count,
):
    """
    Calculate competitive leaderboard points.
    Difficulty:
        Easy   = 1 point per correct answer
        Medium = 2 points per correct answer
        Hard   = 3 points per correct answer
    Question count bonus:
        1  question  = +0
        5  questions = +2
        10 questions = +5
    No points are awarded if the student
    gets zero answers correct.
    """
    difficulty = str(
        difficulty or ""
    ).strip().lower()
    try:
        question_count = int(
            question_count
        )
    except (
        TypeError,
        ValueError,
    ):
        question_count = 0
    try:
        correct_count = int(
            correct_count
        )
    except (
        TypeError,
        ValueError,
    ):
        correct_count = 0
    difficulty_points = DIFFICULTY_POINTS.get(
        difficulty,
        0,
    )
    if (
        difficulty_points <= 0
        or correct_count <= 0
    ):
        return 0
    base_points = (
        correct_count
        * difficulty_points
    )
    count_bonus = COUNT_BONUS.get(
        question_count,
        0,
    )
    return (
        base_points
        + count_bonus
    )
# ============================================================
# Daily points
# ============================================================
def get_user_daily_points(
    user_id,
):
    """
    Get the number of competitive points
    earned by one internal users.id today.
    """
    try:
        user_id = int(
            user_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0
    try:
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
                get_today(),
            )
            .execute()
        )
    except Exception as exc:
        print(
            "LEADERBOARD DAILY LOAD ERROR:",
            type(exc).__name__,
            exc,
        )
        return 0
    rows = result.data or []
    return sum(
        int(
            row.get("points") or 0
        )
        for row in rows
    )
# ============================================================
# Award quiz points
# ============================================================
def award_quiz_points(
    user_id,
    quiz_id,
    difficulty,
    question_count,
    correct_count=None,
):
    """
    Award competitive leaderboard points.
    IMPORTANT:
    This function is intentionally synchronous because
    quizzes.py calls it synchronously.
    The database is the source of truth for the
    number of correct answers whenever possible.
    Returns:
        {
            "base_points": int,
            "awarded_points": int,
            "daily_total": int,
            "daily_remaining": int,
        }
    """
    # --------------------------------------------------------
    # Validate IDs
    # --------------------------------------------------------
    try:
        user_id = int(
            user_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return {
            "base_points": 0,
            "awarded_points": 0,
            "daily_total": 0,
            "daily_remaining": DAILY_POINT_LIMIT,
        }
    try:
        quiz_id = int(
            quiz_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return {
            "base_points": 0,
            "awarded_points": 0,
            "daily_total": get_user_daily_points(
                user_id
            ),
            "daily_remaining": DAILY_POINT_LIMIT,
        }
    # --------------------------------------------------------
    # Prevent duplicate awarding
    # --------------------------------------------------------
    try:
        existing = (
            supabase
            .table("leaderboard_points")
            .select(
                "points, point_date"
            )
            .eq(
                "quiz_id",
                quiz_id,
            )
            .limit(1)
            .execute()
        )
        existing_rows = (
            existing.data or []
        )
    except Exception as exc:
        print(
            "LEADERBOARD EXISTING CHECK ERROR:",
            type(exc).__name__,
            exc,
        )
        existing_rows = []
    if existing_rows:
        existing_points = int(
            existing_rows[0].get(
                "points"
            )
            or 0
        )
        daily_total = (
            get_user_daily_points(
                user_id
            )
        )
        return {
            "base_points": existing_points,
            "awarded_points": existing_points,
            "daily_total": daily_total,
            "daily_remaining": max(
                DAILY_POINT_LIMIT
                - daily_total,
                0,
            ),
        }
    # --------------------------------------------------------
    # Get correct answers directly from database
    # --------------------------------------------------------
    try:
        answers_result = (
            supabase
            .table("quiz_answers")
            .select(
                "is_correct"
            )
            .eq(
                "quiz_id",
                quiz_id,
            )
            .execute()
        )
        answer_rows = (
            answers_result.data or []
        )
    except Exception as exc:
        print(
            "LEADERBOARD ANSWERS ERROR:",
            type(exc).__name__,
            exc,
        )
        answer_rows = []
    database_correct_count = sum(
        1
        for row in answer_rows
        if row.get("is_correct") is True
    )
    # If database answer records exist,
    # always trust the database.
    #
    # Otherwise use the value supplied by quizzes.py.
    if answer_rows:
        correct_count = (
            database_correct_count
        )
    else:
        try:
            correct_count = int(
                correct_count or 0
            )
        except (
            TypeError,
            ValueError,
        ):
            correct_count = 0
    # --------------------------------------------------------
    # Calculate maximum points for this quiz
    # --------------------------------------------------------
    base_points = (
        calculate_quiz_base_points(
            difficulty=difficulty,
            question_count=question_count,
            correct_count=correct_count,
        )
    )
    # --------------------------------------------------------
    # No correct answers = no competitive points
    # --------------------------------------------------------
    if base_points <= 0:
        daily_total = (
            get_user_daily_points(
                user_id
            )
        )
        return {
            "base_points": 0,
            "awarded_points": 0,
            "daily_total": daily_total,
            "daily_remaining": max(
                DAILY_POINT_LIMIT
                - daily_total,
                0,
            ),
        }
    # --------------------------------------------------------
    # Daily limit
    # --------------------------------------------------------
    daily_total_before = (
        get_user_daily_points(
            user_id
        )
    )
    remaining = max(
        DAILY_POINT_LIMIT
        - daily_total_before,
        0,
    )
    awarded_points = min(
        base_points,
        remaining,
    )
    # --------------------------------------------------------
    # Daily limit already reached
    # --------------------------------------------------------
    if awarded_points <= 0:
        return {
            "base_points": base_points,
            "awarded_points": 0,
            "daily_total": daily_total_before,
            "daily_remaining": 0,
        }
    # --------------------------------------------------------
    # Insert points
    # --------------------------------------------------------
    today = get_today()
    try:
        inserted = (
            supabase
            .table("leaderboard_points")
            .insert({
                "user_id": user_id,
                "quiz_id": quiz_id,
                "points": awarded_points,
                "point_date": today,
            })
            .execute()
        )
    except Exception as exc:
        print(
            "LEADERBOARD INSERT ERROR:",
            type(exc).__name__,
            exc,
        )
        # ----------------------------------------------------
        # Possible duplicate caused by another request.
        # Check again before reporting failure.
        # ----------------------------------------------------
        try:
            duplicate_check = (
                supabase
                .table("leaderboard_points")
                .select("points")
                .eq(
                    "quiz_id",
                    quiz_id,
                )
                .limit(1)
                .execute()
            )
            duplicate_rows = (
                duplicate_check.data or []
            )
            if duplicate_rows:
                duplicate_points = int(
                    duplicate_rows[0].get(
                        "points"
                    )
                    or 0
                )
                daily_total = (
                    get_user_daily_points(
                        user_id
                    )
                )
                return {
                    "base_points": base_points,
                    "awarded_points": duplicate_points,
                    "daily_total": daily_total,
                    "daily_remaining": max(
                        DAILY_POINT_LIMIT
                        - daily_total,
                        0,
                    ),
                }
        except Exception as duplicate_exc:
            print(
                "LEADERBOARD DUPLICATE CHECK ERROR:",
                type(duplicate_exc).__name__,
                duplicate_exc,
            )
        return {
            "base_points": base_points,
            "awarded_points": 0,
            "daily_total": daily_total_before,
            "daily_remaining": remaining,
        }
    inserted_rows = (
        inserted.data or []
    )
    # --------------------------------------------------------
    # Verify insertion
    # --------------------------------------------------------
    if not inserted_rows:
        return {
            "base_points": base_points,
            "awarded_points": 0,
            "daily_total": daily_total_before,
            "daily_remaining": remaining,
        }
    # --------------------------------------------------------
    # Final daily total
    # --------------------------------------------------------
    daily_total = (
        daily_total_before
        + awarded_points
    )
    return {
        "base_points": base_points,
        "awarded_points": awarded_points,
        "daily_total": daily_total,
        "daily_remaining": max(
            DAILY_POINT_LIMIT
            - daily_total,
            0,
        ),
    }
# ============================================================
# Leaderboard keyboard
# ============================================================
def leaderboard_keyboard(
    user_id,
):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="🔄 تحديث المتصدرين",
                callback_data=(
                    f"leaderboard:show:"
                    f"{user_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="🧪 الرجوع للاختبارات",
                callback_data=(
                    f"quiz:menu:"
                    f"{user_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="🏠 القائمة الرئيسية",
                callback_data=(
                    f"back_main:"
                    f"{user_id}"
                ),
            )
        ],
    ])
# ============================================================
# Display leaderboard
# ============================================================
async def show_leaderboard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if (
        query is None
        or query.from_user is None
    ):
        return
    telegram_id = query.from_user.id
    await query.answer()
    # --------------------------------------------------------
    # Resolve Telegram ID -> internal users.id
    # --------------------------------------------------------
    internal_user_id = (
        get_internal_user_id(
            telegram_id
        )
    )
    # --------------------------------------------------------
    # Load leaderboard
    # --------------------------------------------------------
    try:
        result = (
            supabase
            .table("leaderboard_points")
            .select(
                "user_id, points"
            )
            .execute()
        )
    except Exception as exc:
        print(
            "LEADERBOARD LOAD ERROR:",
            type(exc).__name__,
            exc,
        )
        await query.edit_message_text(
            "❌ تعذر تحميل قائمة المتصدرين حالياً.\n\n"
            "حاول مرة ثانية بعد قليل.",
            reply_markup=leaderboard_keyboard(
                telegram_id
            ),
        )
        return
    rows = result.data or []
    if not rows:
        await query.edit_message_text(
            "🏆 المتصدرين\n\n"
            "لا توجد نقاط مسجلة حتى الآن.\n\n"
            "ابدأ بالاختبارات واجمع نقاطك "
            "حتى تظهر في قائمة المتصدرين.",
            reply_markup=leaderboard_keyboard(
                telegram_id
            ),
        )
        return
    # --------------------------------------------------------
    # Aggregate total points per internal user ID
    # --------------------------------------------------------
    totals = {}
    for row in rows:
        ranked_user_id = row.get(
            "user_id"
        )
        if ranked_user_id is None:
            continue
        try:
            ranked_user_id = int(
                ranked_user_id
            )
        except (
            TypeError,
            ValueError,
        ):
            continue
        try:
            points = int(
                row.get("points") or 0
            )
        except (
            TypeError,
            ValueError,
        ):
            points = 0
        totals[ranked_user_id] = (
            totals.get(
                ranked_user_id,
                0,
            )
            + points
        )
    if not totals:
        await query.edit_message_text(
            "🏆 المتصدرين\n\n"
            "لا توجد نقاط مسجلة حتى الآن.",
            reply_markup=leaderboard_keyboard(
                telegram_id
            ),
        )
        return
    # --------------------------------------------------------
    # Sort ranking
    # --------------------------------------------------------
    ranking = sorted(
        totals.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    )
    # --------------------------------------------------------
    # Get top users
    # --------------------------------------------------------
    top_user_ids = [
        ranked_user_id
        for ranked_user_id, _ in (
            ranking[
                :LEADERBOARD_LIMIT
            ]
        )
    ]
    users = {}
    try:
        users_result = (
            supabase
            .table("users")
            .select(
                "id, telegram_id, username, first_name"
            )
            .in_(
                "id",
                top_user_ids,
            )
            .execute()
        )
        for user in (
            users_result.data or []
        ):
            try:
                users[
                    int(user["id"])
                ] = user
            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                continue
    except Exception as exc:
        print(
            "LEADERBOARD USERS ERROR:",
            type(exc).__name__,
            exc,
        )
    # --------------------------------------------------------
    # Build text
    # --------------------------------------------------------
    lines = [
        "🏆 **قائمة المتصدرين**",
        "",
        "أعلى الطلاب حسب مجموع نقاط الاختبارات:",
        "",
    ]
    medals = {
        1: "🥇",
        2: "🥈",
        3: "🥉",
    }
    for position, (
        ranked_user_id,
        points,
    ) in enumerate(
        ranking[
            :LEADERBOARD_LIMIT
        ],
        start=1,
    ):
        user = users.get(
            ranked_user_id,
            {},
        )
        username = (
            user.get("username")
            if isinstance(
                user,
                dict,
            )
            else None
        )
        first_name = (
            user.get("first_name")
            if isinstance(
                user,
                dict,
            )
            else None
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
            display_name = "طالب"
        prefix = medals.get(
            position,
            f"{position}.",
        )
        lines.append(
            f"{prefix} {display_name} — "
            f"**{points} نقطة**"
        )
    # --------------------------------------------------------
    # Current user rank
    # --------------------------------------------------------
    current_total = 0
    current_rank = None
    if internal_user_id is not None:
        current_total = totals.get(
            internal_user_id,
            0,
        )
        for position, (
            ranked_user_id,
            _,
        ) in enumerate(
            ranking,
            start=1,
        ):
            if (
                int(ranked_user_id)
                == int(internal_user_id)
            ):
                current_rank = position
                break
    lines.extend([
        "",
        "━━━━━━━━━━━━━━",
        "",
        f"👤 نقاطك: **{current_total}**",
    ])
    if current_rank is not None:
        lines.append(
            f"📊 ترتيبك: **#{current_rank}**"
        )
    else:
        lines.append(
            "📊 ترتيبك: غير مصنف"
        )
    # --------------------------------------------------------
    # Today's points
    # --------------------------------------------------------
    if internal_user_id is not None:
        try:
            daily_points = (
                get_user_daily_points(
                    internal_user_id
                )
            )
        except Exception as exc:
            print(
                "LEADERBOARD DAILY POINTS ERROR:",
                type(exc).__name__,
                exc,
            )
            daily_points = 0
    else:
        daily_points = 0
    lines.extend([
        "",
        f"📅 نقاطك اليوم: "
        f"**{daily_points}/{DAILY_POINT_LIMIT}**",
    ])
    if (
        daily_points
        >= DAILY_POINT_LIMIT
    ):
        lines.append(
            "🔒 وصلت للحد اليومي للنقاط."
        )
    else:
        lines.append(
            f"🎯 المتبقي اليوم: "
            f"**{DAILY_POINT_LIMIT - daily_points} نقطة**"
        )
    # --------------------------------------------------------
    # Send
    # --------------------------------------------------------
    try:
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=leaderboard_keyboard(
                telegram_id
            ),
        )
    except Exception as exc:
        print(
            "LEADERBOARD MESSAGE ERROR:",
            type(exc).__name__,
            exc,
        )
# ============================================================
# Leaderboard callback
# ============================================================
async def leaderboard_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if (
        query is None
        or query.from_user is None
        or not query.data
    ):
        return
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return
    owner_id = parts[2]
    # --------------------------------------------------------
    # Ownership protection
    # --------------------------------------------------------
    if (
        str(query.from_user.id)
        != str(owner_id)
    ):
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return
    action = parts[1]
    if action == "show":
        await show_leaderboard(
            update,
            context,
        )
        return
    await query.answer(
        "❌ اختيار غير معروف.",
        show_alert=True,
    )
