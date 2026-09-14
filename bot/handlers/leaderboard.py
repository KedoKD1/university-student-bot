from datetime import datetime, timezone, timedelta

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from bot.database.client import supabase


# ============================================================
# Configuration
# ============================================================

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
# Helpers
# ============================================================

def owner_error():
    return "⛔ هذا الاختيار مو إلك."


def invalid_selection():
    return "❌ اختيار غير صالح."


def get_user_display_name(user_data):
    """
    ترتيب عرض اسم المستخدم:
    1. username
    2. first_name + last_name
    3. first_name
    4. Telegram ID
    """

    if not user_data:
        return "مستخدم"

    username = (
        user_data.get("username")
        or ""
    ).strip()

    if username:
        return f"@{username.lstrip('@')}"

    first_name = (
        user_data.get("first_name")
        or ""
    ).strip()

    last_name = (
        user_data.get("last_name")
        or ""
    ).strip()

    full_name = " ".join(
        part
        for part in (
            first_name,
            last_name,
        )
        if part
    ).strip()

    if full_name:
        return full_name

    telegram_id = user_data.get("telegram_id")

    if telegram_id is not None:
        return f"مستخدم {telegram_id}"

    return "مستخدم"


# ============================================================
# User mapping
# ============================================================

async def get_internal_user_id(telegram_id):
    """
    تحويل Telegram ID إلى users.id.
    """

    try:
        response = (
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

        rows = response.data or []

        if not rows:
            return None

        return rows[0].get("id")

    except Exception as exc:
        print(
            "GET INTERNAL USER ERROR:",
            type(exc).__name__,
            exc,
        )

        return None


# ============================================================
# Latest Telegram display data
# ============================================================

async def get_user_display_data(telegram_ids):
    """
    جلب أحدث بيانات المستخدمين.
    """

    if not telegram_ids:
        return {}

    clean_ids = []

    for telegram_id in telegram_ids:

        if telegram_id is None:
            continue

        try:
            clean_ids.append(
                int(telegram_id)
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

    clean_ids = list(
        dict.fromkeys(clean_ids)
    )

    if not clean_ids:
        return {}

    result = {}

    # --------------------------------------------------------
    # Primary source
    # --------------------------------------------------------

    try:

        response = (
            supabase
            .table("telegram_users")
            .select(
                "telegram_id, username, "
                "first_name, last_name"
            )
            .in_(
                "telegram_id",
                clean_ids,
            )
            .execute()
        )

        rows = response.data or []

        for row in rows:

            telegram_id = row.get(
                "telegram_id"
            )

            if telegram_id is None:
                continue

            try:
                telegram_id = int(
                    telegram_id
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

            result[telegram_id] = row

    except Exception as exc:

        print(
            "TELEGRAM USERS DISPLAY ERROR:",
            type(exc).__name__,
            exc,
        )

    # --------------------------------------------------------
    # Fallback
    # --------------------------------------------------------

    missing_ids = [
        telegram_id
        for telegram_id in clean_ids
        if telegram_id not in result
    ]

    if missing_ids:

        try:

            response = (
                supabase
                .table("users")
                .select(
                    "telegram_id, username, "
                    "first_name, last_name"
                )
                .in_(
                    "telegram_id",
                    missing_ids,
                )
                .execute()
            )

            rows = response.data or []

            for row in rows:

                telegram_id = row.get(
                    "telegram_id"
                )

                if telegram_id is None:
                    continue

                try:
                    telegram_id = int(
                        telegram_id
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    continue

                result[telegram_id] = row

        except Exception as exc:

            print(
                "USERS DISPLAY FALLBACK ERROR:",
                type(exc).__name__,
                exc,
            )

    return result


# ============================================================
# Daily time
# ============================================================

def get_today_start():
    """
    بداية اليوم بتوقيت العراق UTC+3،
    ثم تحويلها إلى UTC حتى تتوافق مع PostgreSQL timestamptz.
    """

    iraq_offset = timedelta(
        hours=3
    )

    now_iraq = (
        datetime.now(timezone.utc)
        + iraq_offset
    )

    start_iraq = now_iraq.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    start_utc = (
        start_iraq
        - iraq_offset
    )

    return start_utc.replace(
        tzinfo=timezone.utc
    ).isoformat()


# ============================================================
# Quiz points calculation
# ============================================================

def get_points_for_quiz(
    difficulty,
    question_count,
    correct_count=None,
):
    """
    حساب نقاط الاختبار.

    Easy   = 1 نقطة لكل إجابة صحيحة
    Medium = 2 نقاط لكل إجابة صحيحة
    Hard   = 3 نقاط لكل إجابة صحيحة

    Bonus:
    1 سؤال  = +0
    5 أسئلة = +2
    10 أسئلة = +5

    إذا correct_count غير موجود،
    يتم اعتبار جميع الأسئلة صحيحة
    للتوافق مع الاستدعاءات القديمة.
    """

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
        if correct_count is None:
            correct_count = question_count
        else:
            correct_count = int(
                correct_count
            )

    except (
        TypeError,
        ValueError,
    ):
        correct_count = 0

    correct_count = max(
        min(
            correct_count,
            question_count,
        ),
        0,
    )

    difficulty_points = (
        DIFFICULTY_POINTS.get(
            difficulty,
            0,
        )
    )

    count_bonus = COUNT_BONUS.get(
        question_count,
        0,
    )

    # لا توجد نقاط إذا لم تكن هناك إجابة صحيحة.
    if correct_count <= 0:
        return 0

    return (
        difficulty_points
        * correct_count
        + count_bonus
    )


# ============================================================
# Award quiz points
# ============================================================

async def award_quiz_points(
    telegram_id=None,
    difficulty=None,
    question_count=None,
    user_id=None,
    quiz_id=None,
    correct_count=None,
):
    """
    إضافة نقاط للطالب بعد إنهاء الاختبار.

    تدعم الدالة الاستدعاء الحالي الموجود
    داخل quizzes.py:

        user_id
        quiz_id
        difficulty
        question_count
        correct_count

    كما تدعم الاستدعاء القديم:

        telegram_id
        difficulty
        question_count
    """

    # --------------------------------------------------------
    # Normalize question count
    # --------------------------------------------------------

    try:
        question_count = int(
            question_count
        )

    except (
        TypeError,
        ValueError,
    ):
        question_count = 0

    if question_count <= 0:
        return {
            "awarded_points": 0,
            "requested_points": 0,
            "daily_points": 0,
            "remaining_points": DAILY_POINT_LIMIT,
            "daily_limit": DAILY_POINT_LIMIT,
        }

    # --------------------------------------------------------
    # Calculate requested points
    # --------------------------------------------------------

    requested_points = get_points_for_quiz(
        difficulty=difficulty,
        question_count=question_count,
        correct_count=correct_count,
    )

    if requested_points <= 0:
        return {
            "awarded_points": 0,
            "requested_points": 0,
            "daily_points": 0,
            "remaining_points": DAILY_POINT_LIMIT,
            "daily_limit": DAILY_POINT_LIMIT,
        }

    # --------------------------------------------------------
    # Resolve internal user ID
    # --------------------------------------------------------

    internal_user_id = None

    # Current quizzes.py already sends database_user_id
    if user_id is not None:

        try:
            internal_user_id = int(
                user_id
            )

        except (
            TypeError,
            ValueError,
        ):
            internal_user_id = None

    # Fallback: resolve from Telegram ID
    if internal_user_id is None:

        if telegram_id is None:
            print(
                "POINTS ERROR: no user identifier."
            )

            return {
                "awarded_points": 0,
                "requested_points": requested_points,
                "daily_points": 0,
                "remaining_points": DAILY_POINT_LIMIT,
                "daily_limit": DAILY_POINT_LIMIT,
            }

        internal_user_id = (
            await get_internal_user_id(
                telegram_id
            )
        )

    if internal_user_id is None:

        print(
            "POINTS ERROR: internal user not found:",
            telegram_id,
        )

        return {
            "awarded_points": 0,
            "requested_points": requested_points,
            "daily_points": 0,
            "remaining_points": DAILY_POINT_LIMIT,
            "daily_limit": DAILY_POINT_LIMIT,
        }

    # --------------------------------------------------------
    # Today's points
    # --------------------------------------------------------

    today_start = get_today_start()

    daily_points = 0

    try:

        response = (
            supabase
            .table("leaderboard_points")
            .select("points")
            .eq(
                "user_id",
                internal_user_id,
            )
            .gte(
                "created_at",
                today_start,
            )
            .execute()
        )

        rows = response.data or []

        for row in rows:

            try:

                daily_points += int(
                    row.get(
                        "points",
                        0,
                    )
                    or 0
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

    except Exception as exc:

        print(
            "DAILY POINTS ERROR:",
            type(exc).__name__,
            exc,
        )

        return {
            "awarded_points": 0,
            "requested_points": requested_points,
            "daily_points": 0,
            "remaining_points": DAILY_POINT_LIMIT,
            "daily_limit": DAILY_POINT_LIMIT,
        }

    # --------------------------------------------------------
    # Remaining daily points
    # --------------------------------------------------------

    remaining_points = max(
        DAILY_POINT_LIMIT - daily_points,
        0,
    )

    awarded_points = min(
        requested_points,
        remaining_points,
    )

    # --------------------------------------------------------
    # Daily limit reached
    # --------------------------------------------------------

    if awarded_points <= 0:

        return {
            "awarded_points": 0,
            "requested_points": requested_points,
            "daily_points": daily_points,
            "remaining_points": remaining_points,
            "daily_limit": DAILY_POINT_LIMIT,
        }

    # --------------------------------------------------------
    # Insert points
    # --------------------------------------------------------

    try:

        supabase.table(
            "leaderboard_points"
        ).insert(
            {
                "user_id": internal_user_id,
                "points": awarded_points,
                "reason": (
                    f"quiz:{difficulty}:"
                    f"{question_count}:"
                    f"{correct_count}"
                ),
            }
        ).execute()

    except Exception as exc:

        print(
            "AWARD POINTS ERROR:",
            type(exc).__name__,
            exc,
        )

        return {
            "awarded_points": 0,
            "requested_points": requested_points,
            "daily_points": daily_points,
            "remaining_points": remaining_points,
            "daily_limit": DAILY_POINT_LIMIT,
        }

    new_daily_points = (
        daily_points
        + awarded_points
    )

    new_remaining_points = max(
        DAILY_POINT_LIMIT
        - new_daily_points,
        0,
    )

    return {
        "awarded_points": awarded_points,
        "requested_points": requested_points,
        "daily_points": new_daily_points,
        "remaining_points": new_remaining_points,
        "daily_limit": DAILY_POINT_LIMIT,
    }


# ============================================================
# Leaderboard keyboard
# ============================================================

def leaderboard_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="🔄 تحديث",
                callback_data=(
                    f"leaderboard:refresh:"
                    f"{user_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 رجوع للاختبارات",
                callback_data=(
                    f"main:quizzes:"
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
# Get today's points
# ============================================================

async def get_today_points(
    internal_user_id,
):
    if internal_user_id is None:
        return 0

    try:

        today_start = get_today_start()

        response = (
            supabase
            .table("leaderboard_points")
            .select("points")
            .eq(
                "user_id",
                internal_user_id,
            )
            .gte(
                "created_at",
                today_start,
            )
            .execute()
        )

        rows = response.data or []

        total = 0

        for row in rows:

            try:
                total += int(
                    row.get(
                        "points",
                        0,
                    )
                    or 0
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

        return total

    except Exception as exc:

        print(
            "GET TODAY POINTS ERROR:",
            type(exc).__name__,
            exc,
        )

        return 0


# ============================================================
# Show leaderboard
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

    user_id = query.from_user.id

    # --------------------------------------------------------
    # Load all leaderboard points
    # --------------------------------------------------------

    try:

        response = (
            supabase
            .table("leaderboard_points")
            .select(
                "user_id, points"
            )
            .execute()
        )

        rows = response.data or []

    except Exception as exc:

        print(
            "LEADERBOARD POINTS ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.edit_message_text(
            "🏆 لوحة المتصدرين\n\n"
            "❌ تعذر تحميل لوحة المتصدرين حالياً.",
            reply_markup=leaderboard_keyboard(
                user_id
            ),
        )

        return

    # --------------------------------------------------------
    # Aggregate total points
    # --------------------------------------------------------

    totals = {}

    for row in rows:

        internal_user_id = row.get(
            "user_id"
        )

        if internal_user_id is None:
            continue

        try:

            internal_user_id = int(
                internal_user_id
            )

            points = int(
                row.get(
                    "points",
                    0,
                )
                or 0
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        if points <= 0:
            continue

        totals[internal_user_id] = (
            totals.get(
                internal_user_id,
                0,
            )
            + points
        )

    # --------------------------------------------------------
    # Current user
    # --------------------------------------------------------

    current_internal_id = (
        await get_internal_user_id(
            user_id
        )
    )

    current_total_points = 0

    if current_internal_id is not None:

        current_total_points = totals.get(
            int(current_internal_id),
            0,
        )

    current_daily_points = (
        await get_today_points(
            current_internal_id
        )
    )

    current_remaining_points = max(
        DAILY_POINT_LIMIT
        - current_daily_points,
        0,
    )

    # --------------------------------------------------------
    # Ranking
    # --------------------------------------------------------

    ranking = sorted(
        totals.items(),
        key=lambda item: (
            item[1],
            -item[0],
        ),
        reverse=True,
    )[:LEADERBOARD_LIMIT]

    # --------------------------------------------------------
    # User mapping
    # --------------------------------------------------------

    internal_ids = [
        internal_user_id
        for internal_user_id, _ in ranking
    ]

    telegram_ids = []

    internal_to_telegram = {}

    if internal_ids:

        try:

            response = (
                supabase
                .table("users")
                .select(
                    "id, telegram_id"
                )
                .in_(
                    "id",
                    internal_ids,
                )
                .execute()
            )

            user_rows = (
                response.data or []
            )

            for row in user_rows:

                internal_id = row.get(
                    "id"
                )

                telegram_id = row.get(
                    "telegram_id"
                )

                if (
                    internal_id is None
                    or telegram_id is None
                ):
                    continue

                try:

                    internal_id = int(
                        internal_id
                    )

                    telegram_id = int(
                        telegram_id
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    continue

                internal_to_telegram[
                    internal_id
                ] = telegram_id

                telegram_ids.append(
                    telegram_id
                )

        except Exception as exc:

            print(
                "LEADERBOARD USER MAP ERROR:",
                type(exc).__name__,
                exc,
            )

    # --------------------------------------------------------
    # Display data
    # --------------------------------------------------------

    display_data = (
        await get_user_display_data(
            telegram_ids
        )
    )

    # --------------------------------------------------------
    # Build leaderboard
    # --------------------------------------------------------

    lines = [
    "🏆 لوحة المتصدرين",
    "",
    "أفضل الطلاب حسب مجموع النقاط:",
    "",
]

    if not ranking:

        lines.extend([
            "لا توجد نقاط مسجلة حتى الآن.",
            "",
            "ابدأ بحل الاختبارات واجمع نقاطك! 🧪",
        ])

    else:

        medals = {
            1: "🥇",
            2: "🥈",
            3: "🥉",
        }

        for position, (
            internal_user_id,
            points,
        ) in enumerate(
            ranking,
            start=1,
        ):

            telegram_id = (
                internal_to_telegram.get(
                    internal_user_id
                )
            )

            user_data = display_data.get(
                telegram_id,
                {
                    "telegram_id": telegram_id
                },
            )

            display_name = (
                get_user_display_name(
                    user_data
                )
            )

            prefix = medals.get(
                position,
                f"{position}.",
            )

            lines.append(
                f"{prefix} "
                f"{display_name} — "
                f"⭐ {points} نقطة"
            )

    # --------------------------------------------------------
    # Current user's total rank
    # --------------------------------------------------------

    if current_internal_id is not None:

        full_ranking = sorted(
            totals.items(),
            key=lambda item: (
                item[1],
                -item[0],
            ),
            reverse=True,
        )

        current_rank = None

        for index, (
            internal_user_id,
            _points,
        ) in enumerate(
            full_ranking,
            start=1,
        ):

            if int(
                internal_user_id
            ) == int(
                current_internal_id
            ):

                current_rank = index
                break

        lines.extend([
            "",
            "━━━━━━━━━━━━━━",
            "",
            (
                f"👤 مجموع نقاطك: "
                f"⭐ {current_total_points}"
            ),
        ])

        if current_rank is not None:

            lines.append(
                f"📊 ترتيبك: #{current_rank}"
            )


        lines.extend([
            (
                f"📅 نقاطك اليوم: "
                f"⭐ {current_daily_points} / "
                f"{DAILY_POINT_LIMIT}"
            ),
            (
                f"🔥 المتبقي لك اليوم: "
                f"{current_remaining_points} نقطة"
            ),
        ])


    # --------------------------------------------------------
    # Send
    # --------------------------------------------------------

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=leaderboard_keyboard(
            user_id
        ),
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

    # Expected:
    #
    # leaderboard:refresh:user_id
    #

    if len(parts) != 3:

        await query.answer(
            invalid_selection(),
            show_alert=True,
        )

        return

    if parts[0] != "leaderboard":

        await query.answer(
            invalid_selection(),
            show_alert=True,
        )

        return

    action = parts[1]
    owner_id = parts[2]

    try:

        owner_id = int(
            owner_id
        )

    except (
        TypeError,
        ValueError,
    ):

        await query.answer(
            invalid_selection(),
            show_alert=True,
        )

        return

    if query.from_user.id != owner_id:

        await query.answer(
            owner_error(),
            show_alert=True,
        )

        return

    if action == "refresh":

        await query.answer(
            "🔄 تم تحديث لوحة المتصدرين."
        )

        await show_leaderboard(
            update,
            context,
        )

        return

    await query.answer(
        "❌ اختيار غير معروف.",
        show_alert=True,
    )
