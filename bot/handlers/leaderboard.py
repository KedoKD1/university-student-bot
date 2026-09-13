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
“easy”: 1,
“medium”: 2,
“hard”: 3,
}

COUNT_BONUS = {
1: 0,
5: 2,
10: 5,
}

def calculate_quiz_base_points(
difficulty,
question_count,
correct_count,
):
“””
Competitive leaderboard points.

Each correct answer receives points based
on difficulty.
A question-count bonus is added when the
student gets at least one answer correct.
"""
difficulty_points = DIFFICULTY_POINTS.get(
    difficulty,
    0,
)
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
if correct_count <= 0:
    return 0
base_points = (
    correct_count
    * difficulty_points
)
count_bonus = COUNT_BONUS.get(
    question_count,
    0,
)
return base_points + count_bonus

def get_today():
return date.today().isoformat()

async def get_user_daily_points(
user_id,
):
result = (
supabase
.table(“leaderboard_points”)
.select(“points”)
.eq(
“user_id”,
user_id,
)
.eq(
“point_date”,
get_today(),
)
.execute()
)

rows = result.data or []
return sum(
    int(row.get("points") or 0)
    for row in rows
)

async def award_quiz_points(
user_id,
quiz_id,
difficulty,
question_count,
correct_count,
):
“””
Award competitive points for a completed quiz.

Daily limit:
    100 points per student per day.
Returns:
    {
        "base_points": int,
        "awarded_points": int,
        "daily_total": int,
        "daily_remaining": int,
    }
"""
base_points = calculate_quiz_base_points(
    difficulty=difficulty,
    question_count=question_count,
    correct_count=correct_count,
)
if base_points <= 0:
    return {
        "base_points": 0,
        "awarded_points": 0,
        "daily_total": await get_user_daily_points(
            user_id
        ),
        "daily_remaining": DAILY_POINT_LIMIT,
    }
# Prevent awarding the same quiz twice.
existing = (
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
existing_rows = existing.data or []
if existing_rows:
    daily_total = await get_user_daily_points(
        user_id
    )
    return {
        "base_points": base_points,
        "awarded_points": int(
            existing_rows[0].get("points") or 0
        ),
        "daily_total": daily_total,
        "daily_remaining": max(
            DAILY_POINT_LIMIT - daily_total,
            0,
        ),
    }
daily_total_before = (
    await get_user_daily_points(
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
if awarded_points <= 0:
    return {
        "base_points": base_points,
        "awarded_points": 0,
        "daily_total": daily_total_before,
        "daily_remaining": 0,
    }
today = get_today()
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
inserted_rows = inserted.data or []
if not inserted_rows:
    return {
        "base_points": base_points,
        "awarded_points": 0,
        "daily_total": daily_total_before,
        "daily_remaining": remaining,
    }
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

def leaderboard_keyboard(
user_id,
):
return InlineKeyboardMarkup([
[
InlineKeyboardButton(
text=“🔄 تحديث المتصدرين”,
callback_data=(
f”leaderboard:show:{user_id}”
),
)
],
[
InlineKeyboardButton(
text=“🏠 القائمة الرئيسية”,
callback_data=(
f”back_main:{user_id}”
),
)
],
])

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
owner_id = query.from_user.id
await query.answer()
# Get all accumulated points.
result = (
    supabase
    .table("leaderboard_points")
    .select(
        "user_id, points"
    )
    .execute()
)
rows = result.data or []
if not rows:
    await query.edit_message_text(
        "🏆 المتصدرين\n\n"
        "لا توجد نقاط مسجلة حتى الآن.\n\n"
        "ابدأ بالاختبارات واجمع نقاطك "
        "حتى تظهر في قائمة المتصدرين.",
        reply_markup=leaderboard_keyboard(
            owner_id
        ),
    )
    return
totals = {}
for row in rows:
    user_id = row.get("user_id")
    if user_id is None:
        continue
    points = int(
        row.get("points") or 0
    )
    totals[user_id] = (
        totals.get(user_id, 0)
        + points
    )
if not totals:
    await query.edit_message_text(
        "🏆 المتصدرين\n\n"
        "لا توجد نقاط مسجلة حتى الآن.",
        reply_markup=leaderboard_keyboard(
            owner_id
        ),
    )
    return
# Sort highest score first.
ranking = sorted(
    totals.items(),
    key=lambda item: item[1],
    reverse=True,
)
top_user_ids = [
    user_id
    for user_id, _ in ranking[
        :LEADERBOARD_LIMIT
    ]
]
users_result = (
    supabase
    .table("users")
    .select(
        "id, username, first_name"
    )
    .in_(
        "id",
        top_user_ids,
    )
    .execute()
)
users = {}
for user in (
    users_result.data or []
):
    users[user["id"]] = user
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
    username = user.get(
        "username"
    )
    first_name = user.get(
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
    prefix = medals.get(
        position,
        f"{position}.",
    )
    lines.append(
        f"{prefix} {display_name} — "
        f"**{points} نقطة**"
    )
# Current user's total and rank.
current_total = totals.get(
    owner_id,
    0,
)
current_rank = None
for position, (
    ranked_user_id,
    _,
) in enumerate(
    ranking,
    start=1,
):
    if (
        str(ranked_user_id)
        == str(owner_id)
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
daily_points = (
    await get_user_daily_points(
        owner_id
    )
)
lines.extend([
    "",
    f"📅 نقاطك اليوم: **{daily_points}/{DAILY_POINT_LIMIT}**",
])
if daily_points >= DAILY_POINT_LIMIT:
    lines.append(
        "🔒 وصلت للحد اليومي للنقاط."
    )
else:
    lines.append(
        f"🎯 المتبقي اليوم: "
        f"**{DAILY_POINT_LIMIT - daily_points} نقطة**"
    )
await query.edit_message_text(
    "\n".join(lines),
    parse_mode="Markdown",
    reply_markup=leaderboard_keyboard(
        owner_id
    ),
)

async def leaderboard_callback(
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
if len(parts) != 3:
    await query.answer(
        "❌ اختيار غير صالح.",
        show_alert=True,
    )
    return
owner_id = parts[2]
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
