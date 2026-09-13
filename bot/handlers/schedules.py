from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes
from bot.database.client import supabase
def schedule_stages_keyboard(stages, user_id):
    keyboard = []
    for stage in stages:
        stage_id = stage["id"]
        stage_number = stage["stage_number"]
        is_active = stage.get("is_active", False)
        if is_active:
            text = f"📚 المرحلة {stage_number}"
            callback_data = (
                f"student_schedule_stage:"
                f"{stage_id}:{user_id}"
            )
        else:
            text = f"🔒 المرحلة {stage_number}"
            callback_data = (
                f"locked_schedule:"
                f"{stage_id}:{user_id}"
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
                callback_data=(
                    f"main:schedule:{user_id}"
                ),
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
    try:
        user_id = int(parts[2])
    except ValueError:
        await query.answer(
            "❌ المستخدم غير صالح.",
            show_alert=True,
        )
        return
    if query.from_user.id != user_id:
        await query.answer(
            "⛔ هذه القائمة ليست لك.",
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
            "SCHEDULE STAGES ERROR:",
            type(exc).__name__,
            exc,
        )
        await query.edit_message_text(
            "❌ تعذر تحميل المراحل حالياً.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        text="🏠 القائمة الرئيسية",
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
            "📅 الجداول الدراسية\n\n"
            "❌ لا توجد مراحل دراسية حالياً.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        text="🏠 القائمة الرئيسية",
                        callback_data=(
                            f"back_main:{user_id}"
                        ),
                    )
                ]
            ]),
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
    stage_id = parts[1]
    try:
        user_id = int(parts[2])
    except ValueError:
        await query.answer(
            "❌ المستخدم غير صالح.",
            show_alert=True,
        )
        return
    if query.from_user.id != user_id:
        await query.answer(
            "⛔ هذا الزر ليس لك.",
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
    except Exception as exc:
        print(
            "SCHEDULE STAGE ERROR:",
            type(exc).__name__,
            exc,
        )
        await query.edit_message_text(
            "❌ تعذر تحميل المرحلة.",
            reply_markup=schedule_back_keyboard(
                user_id
            ),
        )
        return
    if not stages:
        await query.edit_message_text(
            "❌ المرحلة غير موجودة.",
            reply_markup=schedule_back_keyboard(
                user_id
            ),
        )
        return
    stage = stages[0]
    if not stage.get("is_active", False):
        await query.answer(
            "🔒 هذه المرحلة غير متاحة حاليًا.",
            show_alert=True,
        )
        return
    try:
        response = (
            supabase
            .table("schedules")
            .select(
                "id, stage_id, "
                "telegram_file_id, is_active"
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
    except Exception as exc:
        print(
            "SCHEDULE READ ERROR:",
            type(exc).__name__,
            exc,
        )
        await query.edit_message_text(
            f"📅 جدول المرحلة "
            f"{stage['stage_number']}\n\n"
            "❌ تعذر تحميل الجدول حالياً.",
            reply_markup=schedule_back_keyboard(
                user_id
            ),
        )
        return
    if not schedules:
        await query.edit_message_text(
            f"📅 جدول المرحلة "
            f"{stage['stage_number']}\n\n"
            "⚠️ لا يوجد جدول دراسي "
            "مضاف لهذه المرحلة حاليًا.",
            reply_markup=schedule_back_keyboard(
                user_id
            ),
        )
        return
    schedule = schedules[0]
    telegram_file_id = schedule.get(
        "telegram_file_id"
    )
    if not telegram_file_id:
        await query.edit_message_text(
            f"📅 جدول المرحلة "
            f"{stage['stage_number']}\n\n"
            "❌ ملف الجدول غير متوفر حالياً.",
            reply_markup=schedule_back_keyboard(
                user_id
            ),
        )
        return
    await query.edit_message_text(
        f"📅 جدول المرحلة "
        f"{stage['stage_number']}\n\n"
        "⏳ جاري عرض الجدول..."
    )
    try:
        await query.message.reply_photo(
            photo=telegram_file_id,
            caption=(
                f"📅 جدول المرحلة "
                f"{stage['stage_number']}"
            ),
        )
    except Exception as exc:
        print(
            "SCHEDULE SEND ERROR:",
            type(exc).__name__,
            exc,
        )
        await query.message.reply_text(
            "❌ حدث خطأ أثناء عرض الجدول.",
            reply_markup=schedule_back_keyboard(
                user_id
            ),
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
    try:
        user_id = int(parts[2])
    except ValueError:
        await query.answer(
            "❌ المستخدم غير صالح.",
            show_alert=True,
        )
        return
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
