from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def content_keyboard(subject_id, user_id, stage_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📄 الملفات",
                callback_data=f"content:files:{subject_id}:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "📝 الملخصات",
                callback_data=f"content:summaries:{subject_id}:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "🎨 الرسومات",
                callback_data=f"content:drawings:{subject_id}:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ رجوع للمواد",
                callback_data=f"back_subjects:{stage_id}:{user_id}",
            )
        ],
    ])


def files_section_keyboard(subject_id, user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📖 النظري",
                callback_data=f"files_section:theoretical:{subject_id}:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "🧪 العملي",
                callback_data=f"files_section:practical:{subject_id}:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "📚 جميع الملفات",
                callback_data=f"content:files:all:{subject_id}:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ رجوع للمادة",
                callback_data=f"back_content:{subject_id}:{user_id}",
            )
        ],
    ])


def summaries_section_keyboard(subject_id, user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📖 النظري",
                callback_data=f"summaries_section:theoretical:{subject_id}:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "🧪 العملي",
                callback_data=f"summaries_section:practical:{subject_id}:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "📚 جميع الملخصات",
                callback_data=f"content:summaries:all:{subject_id}:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ رجوع للمادة",
                callback_data=f"back_content:{subject_id}:{user_id}",
            )
        ],
    ])


def drawings_section_keyboard(subject_id, user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📚 جميع الرسومات",
                callback_data=f"content:drawings:all:{subject_id}:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ رجوع للمادة",
                callback_data=f"back_content:{subject_id}:{user_id}",
            )
        ],
    ])
