from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database.client import supabase
from bot.keyboards.main_menu import main_menu_keyboard


def grades_stage_keyboard(stages, user_id):
    keyboard = []

    for stage in stages:
        stage_id = stage["id"]
        stage_number = stage["stage_number"]
        is_active = stage["is_active"]

        if is_active:
            keyboard.append([
                InlineKeyboardButton(
                    text=f"📚 المرحلة {stage_number}",
                    callback_data=f"main:grades_stage:{stage_id}:{user_id}",
                )
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(
                    text=f"🔒 المرحلة {stage_number}",
                    callback_data=f"main:grades_locked:{stage_id}:{user_id}",
                )
            ])

    keyboard.append([
        InlineKeyboardButton(
            text="🏠 القائمة الرئيسية",
            callback_data=f"back_main:{user_id}",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def grades_files_keyboard(files, stage_id, user_id):
    keyboard = []

    for grade_file in files:
        file_id = grade_file["id"]
        name = grade_file["name"]

        keyboard.append([
            InlineKeyboardButton(
                text=f"📝 {name}",
                callback_data=f"main:grade_file:{file_id}:{stage_id}:{user_id}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="📚 إرسال جميع ملفات الدرجات",
            callback_data=f"main:grades_all:{stage_id}:{user_id}",
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            text="🔙 رجوع للمراحل",
            callback_data=f"main:grades_back:{user_id}",
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            text="🏠 القائمة الرئيسية",
            callback_data=f"back_main:{user_id}",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


async def show_grades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    user_id = query.from_user.id

    result = (
        supabase
        .table("stages")
        .select("id, stage_number, is_active")
        .order("stage_number")
        .execute()
    )

    stages = result.data or []

    await query.edit_message_text(
        "📝 الدرجات\n\n"
        "اختر المرحلة الدراسية:",
        reply_markup=grades_stage_keyboard(stages, user_id),
    )


async def show_grade_files(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    stage_id: int,
):
    query = update.callback_query

    result = (
        supabase
        .table("grade_files")
        .select(
            "id, stage_id, name, description, "
            "telegram_file_id, file_type, file_size, "
            "is_active, deleted_at"
        )
        .eq("stage_id", stage_id)
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .order("id")
        .execute()
    )

    files = result.data or []

    if not files:
        await query.edit_message_text(
            "📝 الدرجات\n\n"
            "❌ لا توجد ملفات درجات متوفرة لهذه المرحلة حالياً.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        text="🔙 رجوع للمراحل",
                        callback_data=f"main:grades_back:{query.from_user.id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🏠 القائمة الرئيسية",
                        callback_data=f"back_main:{query.from_user.id}",
                    )
                ],
            ]),
        )
        return

    await query.edit_message_text(
        "📝 الدرجات\n\n"
        "اختر الملف الذي تريد فتحه:",
        reply_markup=grades_files_keyboard(
            files,
            stage_id,
            query.from_user.id,
        ),
    )


async def send_grade_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: int,
    stage_id: int,
):
    query = update.callback_query

    result = (
        supabase
        .table("grade_files")
        .select(
            "id, stage_id, name, description, "
            "telegram_file_id, file_type, file_size, "
            "is_active, deleted_at"
        )
        .eq("id", file_id)
        .eq("stage_id", stage_id)
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )

    grade_file = result.data

    if not grade_file:
        await query.answer(
            "❌ الملف غير متوفر حالياً.",
            show_alert=True,
        )
        return

    await query.answer()

    description = grade_file.get("description")

    caption = f"📝 {grade_file['name']}"

    if description:
        caption += f"\n\n{description}"

    file_type = grade_file.get("file_type")
    telegram_file_id = grade_file.get("telegram_file_id")

    if file_type == "photo":
        await query.message.reply_photo(
            photo=telegram_file_id,
            caption=caption,
        )

    elif file_type == "video":
        await query.message.reply_video(
            video=telegram_file_id,
            caption=caption,
        )

    elif file_type == "audio":
        await query.message.reply_audio(
            audio=telegram_file_id,
            caption=caption,
        )

    else:
        await query.message.reply_document(
            document=telegram_file_id,
            caption=caption,
        )


async def send_all_grade_files(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    stage_id: int,
):
    query = update.callback_query

    result = (
        supabase
        .table("grade_files")
        .select(
            "id, stage_id, name, description, "
            "telegram_file_id, file_type, file_size"
        )
        .eq("stage_id", stage_id)
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .order("id")
        .execute()
    )

    files = result.data or []

    if not files:
        await query.answer(
            "❌ لا توجد ملفات درجات.",
            show_alert=True,
        )
        return

    await query.answer()

    for grade_file in files:
        description = grade_file.get("description")
        caption = f"📝 {grade_file['name']}"

        if description:
            caption += f"\n\n{description}"

        file_type = grade_file.get("file_type")
        telegram_file_id = grade_file.get("telegram_file_id")

        if file_type == "photo":
            await query.message.reply_photo(
                photo=telegram_file_id,
                caption=caption,
            )

        elif file_type == "video":
            await query.message.reply_video(
                video=telegram_file_id,
                caption=caption,
            )

        elif file_type == "audio":
            await query.message.reply_audio(
                audio=telegram_file_id,
                caption=caption,
            )

        else:
            await query.message.reply_document(
                document=telegram_file_id,
                caption=caption,
            )


async def grades_locked(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    await query.answer(
        "🔒 هذه المرحلة غير متاحة حالياً.",
        show_alert=True,
    )


async def grades_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    if len(parts) < 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    owner_id = parts[-1]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return

    action = parts[1]

    if action == "grades":
        await query.answer()
        await show_grades(update, context)
        return

    if action == "grades_stage":
        if len(parts) != 4:
            await query.answer(
                "❌ اختيار غير صالح.",
                show_alert=True,
            )
            return

        stage_id = int(parts[2])

        await query.answer()
        await show_grade_files(
            update,
            context,
            stage_id,
        )
        return

    if action == "grades_locked":
        await grades_locked(update, context)
        return

    if action == "grade_file":
        if len(parts) != 5:
            await query.answer(
                "❌ اختيار غير صالح.",
                show_alert=True,
            )
            return

        file_id = int(parts[2])
        stage_id = int(parts[3])

        await send_grade_file(
            update,
            context,
            file_id,
            stage_id,
        )
        return

    if action == "grades_all":
        if len(parts) != 4:
            await query.answer(
                "❌ اختيار غير صالح.",
                show_alert=True,
            )
            return

        stage_id = int(parts[2])

        await send_all_grade_files(
            update,
            context,
            stage_id,
        )
        return

    if action == "grades_back":
        await query.answer()
        await show_grades(update, context)
        return

    await query.answer(
        "❌ اختيار غير معروف.",
        show_alert=True,
    )
