from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.database.client import supabase
from bot.handlers.admin import is_admin


ADD_SCHEDULE_IMAGE = 1


def stages_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📚 المرحلة 1",
                callback_data="admin_schedule_stage:1",
            )
        ],
        [
            InlineKeyboardButton(
                "📚 المرحلة 2",
                callback_data="admin_schedule_stage:2",
            )
        ],
        [
            InlineKeyboardButton(
                "📚 المرحلة 3",
                callback_data="admin_schedule_stage:3",
            )
        ],
        [
            InlineKeyboardButton(
                "📚 المرحلة 4",
                callback_data="admin_schedule_stage:4",
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ لوحة الإدارة",
                callback_data="admin_back",
            )
        ],
    ])


async def get_stage_by_number(stage_number):
    response = (
        supabase
        .table("stages")
        .select("id, stage_number, is_active")
        .eq("stage_number", stage_number)
        .limit(1)
        .execute()
    )

    data = response.data or []

    return data[0] if data else None


async def admin_schedules(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    await query.answer()

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
        keyboard.append([
            InlineKeyboardButton(
                text=(
                    f"{'🟢' if stage['is_active'] else '🔴'} "
                    f"المرحلة {stage['stage_number']}"
                ),
                callback_data=(
                    f"admin_schedule_stage:{stage['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ لوحة الإدارة",
            callback_data="admin_back",
        )
    ])

    await query.edit_message_text(
        "📅 إدارة الجداول\n\n"
        "اختر المرحلة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def admin_schedule_stage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    stage_id = parts[1]

    await query.answer()

    stage_response = (
        supabase
        .table("stages")
        .select("id, stage_number")
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

    response = (
        supabase
        .table("schedules")
        .select("*")
        .eq("stage_id", stage_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    schedules = response.data or []

    keyboard = [
        [
            InlineKeyboardButton(
                "➕ إضافة/استبدال صورة الجدول",
                callback_data=(
                    f"add_schedule:{stage_id}"
                ),
            )
        ]
    ]

    if schedules:
        keyboard.append([
            InlineKeyboardButton(
                "🗑️ حذف الجدول",
                callback_data=(
                    f"delete_schedule:{schedules[0]['id']}"
                ),
            )
        ])

        status = "🟢 يوجد جدول محفوظ حالياً"
    else:
        status = "🔴 لا توجد صورة جدول حالياً"

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ رجوع للمراحل",
            callback_data="admin_schedules",
        )
    ])

    await query.edit_message_text(
        "📅 إدارة الجدول\n\n"
        f"📚 المرحلة {stage['stage_number']}\n\n"
        f"{status}\n\n"
        "اختر العملية:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def start_add_schedule(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    parts = query.data.split(":")

    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    stage_id = parts[1]

    context.user_data["schedule_stage_id"] = stage_id

    await query.answer()

    await query.edit_message_text(
        "📅 إضافة جدول\n\n"
        "أرسل صورة الجدول الآن.\n\n"
        "🖼️ يجب إرسال الجدول كصورة."
    )

    return ADD_SCHEDULE_IMAGE


async def receive_schedule_image(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_SCHEDULE_IMAGE

    if not update.message.photo:
        await update.message.reply_text(
            "❌ أرسل صورة فقط.\n\n"
            "🖼️ أرسل صورة الجدول:"
        )
        return ADD_SCHEDULE_IMAGE

    stage_id = context.user_data.get(
        "schedule_stage_id"
    )

    if not stage_id:
        await update.message.reply_text(
            "❌ انتهت بيانات العملية.\n"
            "ابدأ من لوحة الإدارة مرة أخرى."
        )
        return ConversationHandler.END

    photo = update.message.photo[-1]

    telegram_file_id = photo.file_id

    try:
        existing = (
            supabase
            .table("schedules")
            .select("id")
            .eq("stage_id", stage_id)
            .limit(1)
            .execute()
        )

        existing_rows = existing.data or []

        if existing_rows:
            supabase.table("schedules").update({
                "telegram_file_id": telegram_file_id,
                "is_active": True,
            }).eq(
                "id",
                existing_rows[0]["id"],
            ).execute()
        else:
            supabase.table("schedules").insert({
                "stage_id": stage_id,
                "telegram_file_id": telegram_file_id,
                "is_active": True,
            }).execute()

    except Exception:
        await update.message.reply_text(
            "❌ تعذر حفظ صورة الجدول."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "✅ تم حفظ صورة الجدول بنجاح."
    )

    context.user_data.pop(
        "schedule_stage_id",
        None,
    )

    return ConversationHandler.END


async def delete_schedule(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    schedule_id = parts[1]

    response = (
        supabase
        .table("schedules")
        .select("id, stage_id")
        .eq("id", schedule_id)
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        await query.answer(
            "❌ الجدول غير موجود.",
            show_alert=True,
        )
        return

    stage_id = rows[0]["stage_id"]

    await query.answer()

    supabase.table("schedules").update({
        "is_active": False,
        "telegram_file_id": None,
    }).eq(
        "id",
        schedule_id,
    ).execute()

    await query.edit_message_text(
        "✅ تم حذف صورة الجدول.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ إدارة المرحلة",
                    callback_data=(
                        f"admin_schedule_stage:{stage_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "🛠️ لوحة الإدارة",
                    callback_data="admin_back",
                )
            ],
        ]),
    )


def schedule_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                start_add_schedule,
                pattern=r"^add_schedule:",
            ),
        ],
        states={
            ADD_SCHEDULE_IMAGE: [
                MessageHandler(
                    filters.PHOTO,
                    receive_schedule_image,
                ),
            ],
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_schedule,
            ),
        ],
        allow_reentry=True,
    )


async def cancel_schedule(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.pop(
        "schedule_stage_id",
        None,
    )

    if update.message:
        await update.message.reply_text(
            "❌ تم إلغاء العملية."
        )

    return ConversationHandler.END
