from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def content_keyboard(subject_id, user_id, stage_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="📄 الملفات",
                callback_data=(
                    f"content:files:"
                    f"{subject_id}:{user_id}"
                )
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 الملخصات",
                callback_data=(
                    f"content:summaries:"
                    f"{subject_id}:{user_id}"
                )
            )
        ],
        [
            InlineKeyboardButton(
                text="🎨 الرسومات",
                callback_data=(
                    f"content:drawings:"
                    f"{subject_id}:{user_id}"
                )
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ رجوع للمواد",
                callback_data=(
                    f"back_subjects:"
                    f"{stage_id}:{user_id}"
                )
            )
        ],
    ])


def files_section_keyboard(
    subject_id,
    user_id,
):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="📖 النظري",
                callback_data=(
                    f"files_section:theoretical:"
                    f"{subject_id}:{user_id}"
                )
            )
        ],
        [
            InlineKeyboardButton(
                text="🧪 العملي",
                callback_data=(
                    f"files_section:practical:"
                    f"{subject_id}:{user_id}"
                )
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ رجوع للمادة",
                callback_data=(
                    f"back_content:"
                    f"{subject_id}:{user_id}"
                )
            )
        ],
    ])
