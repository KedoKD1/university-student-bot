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
from bot.utils.permissions import (
    PERMISSION_MANAGE_SCHEDULES,
    has_permission,
)


ADD_SCHEDULE_IMAGE = 1


async def has_schedule_permission(user_id: int) -> bool:
    return await has_permission(
        user_id,
        PERMISSION_MANAGE_SCHEDULES,
    )


def is_schedule_session_owner(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> bool:
    return (
        context.user_data.get("schedule_admin_id")
        == user_id
    )


async def check_schedule_access(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if query is None or query.from_user is None:
        return False

    user_id = query.from_user.id

    if not await has_schedule_permission(user_id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return False

    if not is_schedule_session_owner(
        context,
        user_id,
    ):
        await query.answer(
            "⛔ هذه جلسة جداول ليست لك.",
            show_alert=True,
        )
        return False

    return True


async def check_schedule_message_access(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    user = update.effective_user

    if user is None:
        return False

    user_id = user.id

    if not await has_schedule_permission(user_id):
        return False

    if not is_schedule_session_owner(
        context,
        user_id,
    ):
        return False

    return True


def clear_schedule_conversation(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    for key in (
        "schedule_stage_id",
        "schedule_admin_id",
    ):
        context.user_data.pop(
            key,
            None,
        )


def parse_stage_callback(
    callback_data: str,
):
    parts = callback_data.split(":")

    if len(parts) != 3:
        return None, None

    return parts[1], parts[2]


def parse_schedule_callback(
    callback_data: str,
):
    parts = callback_data.split(":")

    if len(parts) != 3:
        return None, None

    return parts[1], parts[2]


async def admin_schedules(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    user_id = query.from_user.id

    if not await has_schedule_permission(user_id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    clear_schedule_conversation(context)

    context.user_data["schedule_admin_id"] = user_id

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
                    f"{'🟢' if stage.get('is_active') else '🔴'} "
                    f"المرحلة {stage['stage_number']}"
                ),
                callback_data=(
                    f"admin_schedule_stage:"
                    f"{stage['id']}:"
                    f"{user_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ لوحة الإدارة",
            callback_data=(
                f"admin_schedule_back:"
                f"{user_id}"
            ),
        )
    ])

    await query.edit_message_text(
        "📅 إدارة الجداول\n\n"
        "اختر المرحلة:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def admin_schedule_stage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await has_schedule_permission(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    stage_id, owner_id = parse_stage_callback(
        query.data
    )

    if stage_id is None or owner_id is None:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    try:
        owner_id = int(owner_id)
    except ValueError:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    if query.from_user.id != owner_id:
        await query.answer(
            "⛔ هذه الجلسة ليست لك.",
            show_alert=True,
        )
        return

    context.user_data["schedule_admin_id"] = owner_id

    await query.answer()

    stage_response = (
        supabase
        .table("stages")
        .select("id, stage_number, is_active")
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

    keyboard = [
        [
            InlineKeyboardButton(
                text="➕ إضافة/استبدال صورة الجدول",
                callback_data=(
                    f"add_schedule:"
                    f"{stage_id}:"
                    f"{owner_id}"
                ),
            )
        ]
    ]

    if schedules:
        keyboard.append([
            InlineKeyboardButton(
                text="🗑️ حذف الجدول",
                callback_data=(
                    f"delete_schedule:"
                    f"{schedules[0]['id']}:"
                    f"{owner_id}"
                ),
            )
        ])
        status = "🟢 يوجد جدول محفوظ حالياً"
    else:
        status = "🔴 لا توجد صورة جدول حالياً"

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للمراحل",
            callback_data=(
                f"admin_schedules_back:"
                f"{owner_id}"
            ),
        )
    ])

    await query.edit_message_text(
        "📅 إدارة الجدول\n\n"
        f"📚 المرحلة {stage['stage_number']}\n\n"
        f"{status}\n\n"
        "اختر العملية:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def admin_schedules_back(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await has_schedule_permission(
        query.from_user.id
    ):
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

    try:
        owner_id = int(parts[1])
    except ValueError:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    if query.from_user.id != owner_id:
        await query.answer(
            "⛔ هذه الجلسة ليست لك.",
            show_alert=True,
        )
        return

    context.user_data["schedule_admin_id"] = owner_id

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
                    f"{'🟢' if stage.get('is_active') else '🔴'} "
                    f"المرحلة {stage['stage_number']}"
                ),
                callback_data=(
                    f"admin_schedule_stage:"
                    f"{stage['id']}:"
                    f"{owner_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ لوحة الإدارة",
            callback_data=(
                f"admin_schedule_back:"
                f"{owner_id}"
            ),
        )
    ])

    await query.edit_message_text(
        "📅 إدارة الجداول\n\n"
        "اختر المرحلة:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def admin_schedule_back(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await has_schedule_permission(
        query.from_user.id
    ):
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

    try:
        owner_id = int(parts[1])
    except ValueError:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    if query.from_user.id != owner_id:
        await query.answer(
            "⛔ هذه الجلسة ليست لك.",
            show_alert=True,
        )
        return

    await query.answer()

    context.user_data["schedule_admin_id"] = owner_id

    keyboard = [
        [
            InlineKeyboardButton(
                text="⬅️ لوحة الإدارة",
                callback_data="admin_back",
            )
        ]
    ]

    await query.edit_message_text(
        "🛠️ لوحة إدارة الجداول\n\n"
        "يمكنك العودة إلى لوحة الإدارة الرئيسية.",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def start_add_schedule(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    user_id = query.from_user.id

    if not await has_schedule_permission(user_id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    stage_id = parts[1]

    try:
        owner_id = int(parts[2])
    except ValueError:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    if user_id != owner_id:
        await query.answer(
            "⛔ هذه الجلسة ليست لك.",
            show_alert=True,
        )
        return ConversationHandler.END

    context.user_data["schedule_stage_id"] = stage_id
    context.user_data["schedule_admin_id"] = user_id

    await query.answer()

    await query.edit_message_text(
        "📅 إضافة جدول\n\n"
        "أرسل صورة الجدول الآن.\n\n"
        "🖼️ يجب إرسال الجدول كصورة.\n\n"
        "❌ للإلغاء أرسل /cancel"
    )

    return ADD_SCHEDULE_IMAGE


async def receive_schedule_image(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ADD_SCHEDULE_IMAGE

    if not await check_schedule_message_access(
        update,
        context,
    ):
        return ADD_SCHEDULE_IMAGE

    stage_id = context.user_data.get(
        "schedule_stage_id"
    )

    if not stage_id:
        await update.message.reply_text(
            "❌ انتهت بيانات العملية.\n"
            "ابدأ من لوحة الإدارة مرة أخرى."
        )
        clear_schedule_conversation(context)
        return ConversationHandler.END

    if not update.message.photo:
        await update.message.reply_text(
            "❌ أرسل صورة فقط.\n\n"
            "🖼️ أرسل صورة الجدول:"
        )
        return ADD_SCHEDULE_IMAGE

    photo = update.message.photo[-1]
    telegram_file_id = photo.file_id

    try:
        stage_response = (
            supabase
            .table("stages")
            .select("id")
            .eq("id", stage_id)
            .limit(1)
            .execute()
        )

        if not stage_response.data:
            raise ValueError(
                "Stage does not exist."
            )

        existing = (
            supabase
            .table("schedules")
            .select("id")
            .eq("stage_id", stage_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )

        existing_rows = existing.data or []

        schedule_data = {
            "stage_id": stage_id,
            "telegram_file_id": telegram_file_id,
            "is_active": True,
        }

        if existing_rows:
            response = (
                supabase
                .table("schedules")
                .update(schedule_data)
                .eq(
                    "id",
                    existing_rows[0]["id"],
                )
                .execute()
            )
        else:
            response = (
                supabase
                .table("schedules")
                .insert(schedule_data)
                .execute()
            )

        if not response.data:
            raise ValueError(
                "Supabase returned no saved schedule."
            )

    except Exception as exc:
        print(
            "SCHEDULE SAVE ERROR:"
            f" {type(exc).__name__}: {exc}"
        )

        await update.message.reply_text(
            "❌ تعذر حفظ صورة الجدول.\n\n"
            "تم تسجيل الخطأ في Railway Logs."
        )

        clear_schedule_conversation(context)

        return ConversationHandler.END

    await update.message.reply_text(
        "✅ تم حفظ صورة الجدول بنجاح."
    )

    clear_schedule_conversation(context)

    return ConversationHandler.END


async def delete_schedule(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await has_schedule_permission(
        query.from_user.id
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    schedule_id, owner_id = parse_schedule_callback(
        query.data
    )

    if schedule_id is None or owner_id is None:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    try:
        owner_id = int(owner_id)
    except ValueError:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    if query.from_user.id != owner_id:
        await query.answer(
            "⛔ هذه الجلسة ليست لك.",
            show_alert=True,
        )
        return

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

    try:
        supabase.table("schedules").update({
            "is_active": False,
            "telegram_file_id": None,
        }).eq(
            "id",
            schedule_id,
        ).execute()

    except Exception as exc:
        print(
            "SCHEDULE DELETE ERROR:"
            f" {type(exc).__name__}: {exc}"
        )

        await query.edit_message_text(
            "❌ تعذر حذف الجدول."
        )

        return

    await query.edit_message_text(
        "✅ تم حذف صورة الجدول.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text="⬅️ إدارة المرحلة",
                    callback_data=(
                        f"admin_schedule_stage:"
                        f"{stage_id}:"
                        f"{owner_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛠️ لوحة الإدارة",
                    callback_data=(
                        f"admin_schedule_back:"
                        f"{owner_id}"
                    ),
                )
            ],
        ]),
    )


async def cancel_schedule(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    if user is None:
        return ConversationHandler.END

    if not await has_schedule_permission(user.id):
        return ConversationHandler.END

    if not is_schedule_session_owner(
        context,
        user.id,
    ):
        return ConversationHandler.END

    clear_schedule_conversation(context)

    if update.message:
        await update.message.reply_text(
            "❌ تم إلغاء العملية."
        )

    return ConversationHandler.END


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
