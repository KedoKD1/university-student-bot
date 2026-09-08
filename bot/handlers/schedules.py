from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database.client import supabase


def schedule_stages_keyboard(stages, user_id):
    keyboard = []

    for stage in stages:
        if stage["is_active"]:
            text = f"📚 المرحلة {stage['stage_number']}"
            callback_data = (
                f"student_schedule_stage:"
                f"{stage['id']}:{user_id}"
            )
        else:
            text = f"🔒 المرحلة {stage['stage_number']}"
            callback_data = (
                f"locked_schedule:"
                f"{stage['id']}:{user_id}"
            )

        keyboard.append([
            InlineKeyboardButton(
                text=text,
                callback_data=callback_data,
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ القائمة الرئيسية",
            callback_data=f"back_main:{user_id}",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def schedule_back_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="⬅️ رجوع للمراحل",
                callback_data=f"main:schedule:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🏠 القائمة الرئيسية",
                callback_data=f"back_main:{user_id}",
            )
        ],
    ])


async def show_schedules(
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

    user_id = int(parts[2])

    if query.from_user.id != user_id:
        await query.answer(
            "⛔ هذه القائمة ليست لك.",
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

    if not stages:
        await query.edit_message_text(
            "❌ لا توجد مراحل دراسية حاليًا."
        )
        return

    await query.edit_message_text(
        "📅 الجداول الدراسية\n\n"
        "اختر المرحلة الدراسية:",
        reply_markup=schedule_stages_keyboard(
            stages,
            user_id,
        ),
    )


async def student_schedule_stage(
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

    stage_id = parts[1]
    user_id = int(parts[2])

    if query.from_user.id != user_id:
        await query.answer(
            "⛔ هذا الزر ليس لك.",
            show_alert=True,
        )
        return

    await query.answer()

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
            "❌ المرحلة غير موجودة."
        )
        return

    stage = stages[0]

    if not stage["is_active"]:
        await query.answer(
            "🔒 هذه المرحلة غير متاحة حاليًا.",
            show_alert=True,
        )
        return

    response = (
        supabase
        .table("schedules")
        .select(
            "id, stage_id, telegram_file_id, is_active"
        )
        .eq("stage_id", stage_id)
        .eq("is_active", True)
        .not_.is_(
            "telegram_file_id",
            "null",
        )
        .order("id", desc=True)
        .limit(1)
        .execute()
    )

    schedules = response.data or []

    if not schedules:
        await query.edit_message_text(
            f"📅 جدول المرحلة {stage['stage_number']}\n\n"
            "⚠️ لا يوجد جدول دراسي مضاف لهذه المرحلة حاليًا.",
            reply_markup=schedule_back_keyboard(
                user_id
            ),
        )
        return

    schedule = schedules[0]

    await query.edit_message_text(
        f"📅 جدول المرحلة {stage['stage_number']}\n\n"
        "⏳ جاري عرض الجدول..."
    )

    try:
        await query.message.reply_photo(
            photo=schedule["telegram_file_id"],
            caption=(
                f"📅 جدول المرحلة "
                f"{stage['stage_number']}"
            ),
        )

    except Exception as exc:
        print(
            f"SCHEDULE SEND ERROR: {exc}"
        )

        await query.message.reply_text(
            "❌ حدث خطأ أثناء عرض الجدول."
        )
        return

    await query.message.reply_text(
        "اختر الإجراء:",
        reply_markup=schedule_back_keyboard(
            user_id
        ),
    )


async def locked_schedule(
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

    user_id = int(parts[2])

    if query.from_user.id != user_id:
        await query.answer(
            "⛔ هذا الزر ليس لك.",
            show_alert=True,
        )
        return

    await query.answer(
        "🔒 هذه المرحلة غير متاحة حاليًا.",
        show_alert=True,
    )
