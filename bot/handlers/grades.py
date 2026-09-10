from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import ContextTypes

from bot.database.client import supabase


# ============================================================
# Helpers
# ============================================================

def grades_stage_keyboard(stages, user_id):
    keyboard = []

    for stage in stages:
        stage_id = stage["id"]
        stage_number = stage["stage_number"]
        is_active = stage["is_active"]

        if is_active:
            keyboard.append([
                InlineKeyboardButton(
                    f"📚 المرحلة {stage_number}",
                    callback_data=(
                        f"grades_stage:{stage_id}:{user_id}"
                    ),
                )
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(
                    f"🔒 المرحلة {stage_number}",
                    callback_data=(
                        f"grades_locked:{stage_id}:{user_id}"
                    ),
                )
            ])

    keyboard.append([
        InlineKeyboardButton(
            "🏠 القائمة الرئيسية",
            callback_data=f"back_main:{user_id}",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def grades_files_keyboard(
    files,
    stage_id,
    user_id,
):
    keyboard = []

    for file in files:
        file_id = file["id"]
        name = file.get("name") or "ملف الدرجات"

        keyboard.append([
            InlineKeyboardButton(
                f"📝 {name}",
                callback_data=(
                    f"grade_file:{file_id}:{stage_id}:{user_id}"
                ),
            )
        ])

    if len(files) > 1:
        keyboard.append([
            InlineKeyboardButton(
                "📚 جميع ملفات الدرجات",
                callback_data=(
                    f"grades_all:{stage_id}:{user_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ رجوع للمراحل",
            callback_data=(
                f"grades_back:{user_id}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🏠 القائمة الرئيسية",
            callback_data=f"back_main:{user_id}",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


# ============================================================
# Student: choose stage
# ============================================================

async def show_grades(
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

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
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

    if not stages:
        await query.edit_message_text(
            "❌ لا توجد مراحل دراسية حالياً."
        )
        return

    await query.edit_message_text(
        "📝 الدرجات الجامعية\n\n"
        "اختر المرحلة الدراسية:",
        reply_markup=grades_stage_keyboard(
            stages,
            query.from_user.id,
        ),
    )


# ============================================================
# Student: choose stage
# ============================================================

async def grades_stage(
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

    if not stage["is_active"]:
        await query.answer(
            "🔒 هذه المرحلة غير متاحة حالياً.",
            show_alert=True,
        )
        return

    response = (
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

    files = response.data or []

    if not files:
        await query.edit_message_text(
            f"📝 درجات المرحلة {stage['stage_number']}\n\n"
            "❌ لا توجد ملفات درجات متاحة حالياً.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ رجوع للمراحل",
                        callback_data=(
                            f"grades_back:{owner_id}"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🏠 القائمة الرئيسية",
                        callback_data=(
                            f"back_main:{owner_id}"
                        ),
                    )
                ],
            ]),
        )
        return

    text = (
        f"📝 درجات المرحلة {stage['stage_number']}\n\n"
        "اختر الملف الذي تريد فتحه:"
    )

    await query.edit_message_text(
        text,
        reply_markup=grades_files_keyboard(
            files,
            stage_id,
            query.from_user.id,
        ),
    )


# ============================================================
# Student: locked stage
# ============================================================

async def grades_locked(
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

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return

    await query.answer(
        "🔒 هذه المرحلة غير متاحة حالياً.",
        show_alert=True,
    )


# ============================================================
# Student: back to stages
# ============================================================

async def grades_back(
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

    await query.answer()

    await show_grades(
        update,
        context,
    )


# ============================================================
# Student: send one grade file
# ============================================================

async def grade_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    if len(parts) != 4:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    file_id = parts[1]
    stage_id = parts[2]
    owner_id = parts[3]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.",
            show_alert=True,
        )
        return

    await query.answer()

    response = (
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
        .limit(1)
        .execute()
    )

    files = response.data or []

    if not files:
        await query.answer(
            "❌ الملف غير موجود أو لم يعد متاحاً.",
            show_alert=True,
        )
        return

    file = files[0]

    telegram_file_id = file.get("telegram_file_id")

    if not telegram_file_id:
        await query.answer(
            "❌ ملف الدرجات غير متوفر حالياً.",
            show_alert=True,
        )
        return

    name = file.get("name") or "ملف الدرجات"
    description = file.get("description")

    caption = f"📝 {name}"

    if description:
        caption += f"\n\n{description}"

    try:
        file_type = (
            str(file.get("file_type") or "")
            .lower()
            .strip()
        )

        if file_type in {"photo", "image", "jpg", "jpeg", "png"}:
            await query.message.reply_photo(
                photo=telegram_file_id,
                caption=caption[:1024],
            )

        elif file_type in {"video", "mp4"}:
            await query.message.reply_video(
                video=telegram_file_id,
                caption=caption[:1024],
            )

        elif file_type in {"audio", "mp3", "m4a"}:
            await query.message.reply_audio(
                audio=telegram_file_id,
                caption=caption[:1024],
            )

        else:
            await query.message.reply_document(
                document=telegram_file_id,
                caption=caption[:1024],
            )

    except Exception as exc:
        print(
            "GRADE FILE SEND ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.message.reply_text(
            "❌ تعذر إرسال ملف الدرجات."
        )


# ============================================================
# Student: send all grade files
# ============================================================

async def grades_all(
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

    await query.answer(
        "⏳ جارٍ إرسال الملفات..."
    )

    response = (
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

    files = response.data or []

    if not files:
        await query.message.reply_text(
            "❌ لا توجد ملفات درجات متاحة."
        )
        return

    sent = 0

    for file in files:
        telegram_file_id = file.get("telegram_file_id")

        if not telegram_file_id:
            continue

        name = file.get("name") or "ملف الدرجات"
        description = file.get("description")

        caption = f"📝 {name}"

        if description:
            caption += f"\n\n{description}"

        try:
            file_type = (
                str(file.get("file_type") or "")
                .lower()
                .strip()
            )

            if file_type in {
                "photo",
                "image",
                "jpg",
                "jpeg",
                "png",
            }:
                await query.message.reply_photo(
                    photo=telegram_file_id,
                    caption=caption[:1024],
                )

            elif file_type in {
                "video",
                "mp4",
            }:
                await query.message.reply_video(
                    video=telegram_file_id,
                    caption=caption[:1024],
                )

            elif file_type in {
                "audio",
                "mp3",
                "m4a",
            }:
                await query.message.reply_audio(
                    audio=telegram_file_id,
                    caption=caption[:1024],
                )

            else:
                await query.message.reply_document(
                    document=telegram_file_id,
                    caption=caption[:1024],
                )

            sent += 1

        except Exception as exc:
            print(
                "GRADE ALL SEND ERROR:",
                type(exc).__name__,
                exc,
            )

    if sent == 0:
        await query.message.reply_text(
            "❌ تعذر إرسال ملفات الدرجات."
        )
    else:
        await query.message.reply_text(
            f"✅ تم إرسال {sent} ملف من ملفات الدرجات."
        )
