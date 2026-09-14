from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from bot.database.client import supabase


# ============================================================
# Helpers
# ============================================================

def owner_error():
    return "⛔ هذا الاختيار مو إلك."


def invalid_selection():
    return "❌ اختيار غير صالح."


def main_button(user_id):
    return [
        InlineKeyboardButton(
            text="🏠 القائمة الرئيسية",
            callback_data=f"back_main:{user_id}",
        )
    ]


# ============================================================
# Keyboards
# ============================================================

def grades_stage_keyboard(stages, user_id):
    keyboard = []

    for stage in stages:
        stage_id = stage["id"]
        stage_number = stage["stage_number"]
        is_active = stage.get("is_active", False)

        if is_active:
            callback_data = (
                f"main:grades_stage:"
                f"{stage_id}:{user_id}"
            )
            text = f"📚 المرحلة {stage_number}"
        else:
            callback_data = (
                f"main:grades_locked:"
                f"{stage_id}:{user_id}"
            )
            text = f"🔒 المرحلة {stage_number}"

        keyboard.append([
            InlineKeyboardButton(
                text=text,
                callback_data=callback_data,
            )
        ])

    keyboard.append(main_button(user_id))

    return InlineKeyboardMarkup(keyboard)


def grades_files_keyboard(files, stage_id, user_id):
    keyboard = []

    for grade_file in files:
        file_id = grade_file["id"]
        name = grade_file.get("name") or "ملف الدرجات"

        keyboard.append([
            InlineKeyboardButton(
                text=f"📝 {name}",
                callback_data=(
                    f"main:grade_file:"
                    f"{file_id}:{stage_id}:{user_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="📚 إرسال جميع ملفات الدرجات",
            callback_data=(
                f"main:grades_all:"
                f"{stage_id}:{user_id}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            text="🔙 رجوع للمراحل",
            callback_data=(
                f"main:grades_back:{user_id}"
            ),
        )
    ])

    keyboard.append(main_button(user_id))

    return InlineKeyboardMarkup(keyboard)


def grades_empty_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="🔙 رجوع للمراحل",
                callback_data=(
                    f"main:grades_back:{user_id}"
                ),
            )
        ],
        main_button(user_id),
    ])


# ============================================================
# Student: show stages
# ============================================================

async def show_grades(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    user_id = query.from_user.id

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
            "GRADES STAGES ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.edit_message_text(
            "❌ تعذر تحميل المراحل حالياً.",
            reply_markup=InlineKeyboardMarkup([
                main_button(user_id)
            ]),
        )
        return

    if not stages:
        await query.edit_message_text(
            "📝 الدرجات\n\n"
            "❌ لا توجد مراحل دراسية حالياً.",
            reply_markup=grades_empty_keyboard(user_id),
        )
        return

    await query.edit_message_text(
        "📝 الدرجات\n\n"
        "اختر المرحلة الدراسية:",
        reply_markup=grades_stage_keyboard(
            stages,
            user_id,
        ),
    )


# ============================================================
# Student: show files
# ============================================================

async def show_grade_files(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    stage_id: int,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    user_id = query.from_user.id

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

        if not stages:
            await query.edit_message_text(
                "❌ المرحلة غير موجودة.",
                reply_markup=grades_empty_keyboard(
                    user_id
                ),
            )
            return

        stage = stages[0]

        if not stage.get("is_active", False):
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
                "telegram_file_id, file_type, "
                "file_size, is_active, deleted_at"
            )
            .eq("stage_id", stage_id)
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .order("id")
            .execute()
        )

        files = response.data or []

    except Exception as exc:
        print(
            "GRADE FILES ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.edit_message_text(
            "❌ تعذر تحميل ملفات الدرجات.",
            reply_markup=grades_empty_keyboard(
                user_id
            ),
        )
        return

    if not files:
        await query.edit_message_text(
            "📝 الدرجات\n\n"
            f"📚 المرحلة {stage['stage_number']}\n\n"
            "❌ لا توجد ملفات درجات متوفرة "
            "لهذه المرحلة حالياً.",
            reply_markup=grades_empty_keyboard(
                user_id
            ),
        )
        return

    await query.edit_message_text(
        "📝 الدرجات\n\n"
        f"📚 المرحلة {stage['stage_number']}\n\n"
        "اختر الملف الذي تريد فتحه:",
        reply_markup=grades_files_keyboard(
            files,
            stage_id,
            user_id,
        ),
    )


# ============================================================
# Student: send one file
# ============================================================

async def send_grade_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: int,
    stage_id: int,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    user_id = query.from_user.id

    try:
        response = (
            supabase
            .table("grade_files")
            .select(
                "id, stage_id, name, description, "
                "telegram_file_id, file_type, "
                "file_size, is_active, deleted_at"
            )
            .eq("id", file_id)
            .eq("stage_id", stage_id)
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )

        rows = response.data or []

    except Exception as exc:
        print(
            "GRADE FILE READ ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ تعذر تحميل الملف.",
            show_alert=True,
        )
        return

    if not rows:
        await query.answer(
            "❌ الملف غير متوفر حالياً.",
            show_alert=True,
        )
        return

    grade_file = rows[0]

    telegram_file_id = grade_file.get(
        "telegram_file_id"
    )

    if not telegram_file_id:
        await query.answer(
            "❌ الملف لا يحتوي على ملف تيليجرام.",
            show_alert=True,
        )
        return

    await query.answer()

    description = (
        grade_file.get("description") or ""
    ).strip()

    caption = (
        f"📝 "
        f"{grade_file.get('name') or 'ملف الدرجات'}"
    )

    if description:
        caption += f"\n\n{description}"

    file_type = (
        grade_file.get("file_type") or "document"
    ).lower()

    try:
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

    except Exception as exc:
        print(
            "GRADE FILE SEND ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.message.reply_text(
            "❌ حدث خطأ أثناء إرسال ملف الدرجات."
        )


# ============================================================
# Student: send all files
# ============================================================

async def send_all_grade_files(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    stage_id: int,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    try:
        response = (
            supabase
            .table("grade_files")
            .select(
                "id, stage_id, name, description, "
                "telegram_file_id, file_type, "
                "file_size, is_active, deleted_at"
            )
            .eq("stage_id", stage_id)
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .order("id")
            .execute()
        )

        files = response.data or []

    except Exception as exc:
        print(
            "ALL GRADE FILES ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ تعذر تحميل الملفات.",
            show_alert=True,
        )
        return

    if not files:
        await query.answer(
            "❌ لا توجد ملفات درجات.",
            show_alert=True,
        )
        return

    await query.answer()

    sent_count = 0

    for grade_file in files:
        telegram_file_id = grade_file.get(
            "telegram_file_id"
        )

        if not telegram_file_id:
            continue

        description = (
            grade_file.get("description") or ""
        ).strip()

        caption = (
            f"📝 "
            f"{grade_file.get('name') or 'ملف الدرجات'}"
        )

        if description:
            caption += f"\n\n{description}"

        file_type = (
            grade_file.get("file_type") or "document"
        ).lower()

        try:
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

            sent_count += 1

        except Exception as exc:
            print(
                "GRADE FILE SEND ERROR:",
                type(exc).__name__,
                exc,
            )

    if sent_count == 0:
        await query.message.reply_text(
            "❌ تعذر إرسال ملفات الدرجات."
        )


# ============================================================
# Locked stage
# ============================================================

async def grades_locked(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    await query.answer(
        "🔒 هذه المرحلة غير متاحة حالياً.",
        show_alert=True,
    )


# ============================================================
# Main grades callback
# ============================================================

async def grades_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    data = query.data or ""
    parts = data.split(":")

    # --------------------------------------------------------
    # Every grades callback must start with main:grades...
    # --------------------------------------------------------

    if len(parts) < 3 or parts[0] != "main":
        await query.answer(
            invalid_selection(),
            show_alert=True,
        )
        return

    action = parts[1]

    # --------------------------------------------------------
    # Owner is always the LAST part
    # --------------------------------------------------------

    owner_id = parts[-1]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            owner_error(),
            show_alert=True,
        )
        return

    # --------------------------------------------------------
    # Show grades stages
    # main:grades:user_id
    # --------------------------------------------------------

    if action == "grades":
        await query.answer()

        await show_grades(
            update,
            context,
        )
        return

    # --------------------------------------------------------
    # Select stage
    # main:grades_stage:stage_id:user_id
    # --------------------------------------------------------

    if action == "grades_stage":
        if len(parts) != 4:
            await query.answer(
                invalid_selection(),
                show_alert=True,
            )
            return

        try:
            stage_id = int(parts[2])
        except (TypeError, ValueError):
            await query.answer(
                "❌ المرحلة غير صالحة.",
                show_alert=True,
            )
            return

        await query.answer()

        await show_grade_files(
            update,
            context,
            stage_id,
        )
        return

    # --------------------------------------------------------
    # Locked stage
    # main:grades_locked:stage_id:user_id
    # --------------------------------------------------------

    if action == "grades_locked":
        await grades_locked(
            update,
            context,
        )
        return

    # --------------------------------------------------------
    # One grade file
    # main:grade_file:file_id:stage_id:user_id
    # --------------------------------------------------------

    if action == "grade_file":
        if len(parts) != 5:
            await query.answer(
                invalid_selection(),
                show_alert=True,
            )
            return

        try:
            file_id = int(parts[2])
            stage_id = int(parts[3])
        except (TypeError, ValueError):
            await query.answer(
                "❌ بيانات الملف غير صالحة.",
                show_alert=True,
            )
            return

        await send_grade_file(
            update,
            context,
            file_id,
            stage_id,
        )
        return

    # --------------------------------------------------------
    # All grade files
    # main:grades_all:stage_id:user_id
    # --------------------------------------------------------

    if action == "grades_all":
        if len(parts) != 4:
            await query.answer(
                invalid_selection(),
                show_alert=True,
            )
            return

        try:
            stage_id = int(parts[2])
        except (TypeError, ValueError):
            await query.answer(
                "❌ المرحلة غير صالحة.",
                show_alert=True,
            )
            return

        await send_all_grade_files(
            update,
            context,
            stage_id,
        )
        return

    # --------------------------------------------------------
    # Back to grades stages
    # main:grades_back:user_id
    # --------------------------------------------------------

    if action == "grades_back":
        if len(parts) != 3:
            await query.answer(
                invalid_selection(),
                show_alert=True,
            )
            return

        await query.answer()

        await show_grades(
            update,
            context,
        )
        return

    await query.answer(
        "❌ اختيار غير معروف.",
        show_alert=True,
    )
