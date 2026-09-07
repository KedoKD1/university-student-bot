from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes

from bot.database.client import supabase
from bot.keyboards.main_menu import back_main_keyboard


async def show_schedule_stages(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    await query.answer()

    user_id = query.from_user.id

    response = (
        supabase
        .table("stages")
        .select("id, stage_number, is_active")
        .order("stage_number")
        .execute()
    )

    stages = response.data or []

    keyboard = []

    for stage in stages:
        if not stage["is_active"]:
            continue

        keyboard.append([
            InlineKeyboardButton(
                text=f"📚 المرحلة {stage['stage_number']}",
                callback_data=(
                    f"schedule_stage:"
                    f"{stage['id']}:{user_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="🏠 القائمة الرئيسية",
            callback_data=f"back_main:{user_id}",
        )
    ])

    await query.edit_message_text(
        "📅 الجداول\n\n"
        "اختر المرحلة الدراسية:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_schedule(
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
    owner_id = parts[2]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return

    await query.answer()

    response = (
        supabase
        .table("schedules")
        .select("telegram_file_id")
        .eq("stage_id", stage_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    schedules = response.data or []

    if not schedules:
        await query.edit_message_text(
            "📅 الجدول\n\n"
            "لا يوجد جدول مضاف لهذه المرحلة حالياً.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        text="⬅️ رجوع للمراحل",
                        callback_data=(
                            f"schedule_back_stages:"
                            f"{owner_id}"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🏠 القائمة الرئيسية",
                        callback_data=(
                            f"back_main:{owner_id}"
                        ),
                    )
                ],
            ]),
        )
        return

    telegram_file_id = schedules[0].get(
        "telegram_file_id"
    )

    if not telegram_file_id:
        await query.edit_message_text(
            "⚠️ لم يتم ربط صورة الجدول بهذه المرحلة.",
            reply_markup=back_main_keyboard(
                owner_id
            ),
        )
        return

    await query.message.reply_photo(
        photo=telegram_file_id,
        caption="📅 جدول المرحلة الدراسية",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text="🏠 القائمة الرئيسية",
                    callback_data=(
                        f"back_main:{owner_id}"
                    ),
                )
            ]
        ]),
    )


async def schedule_back_stages(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    owner_id = parts[1]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return

    await show_schedule_stages(
        update,
        context,
    )
