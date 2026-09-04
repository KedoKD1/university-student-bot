from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def content_keyboard(subject_id, user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="📖 النظري",
                callback_data=f"content:theory:{subject_id}:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🧪 العملي",
                callback_data=f"content:practical:{subject_id}:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ رجوع للمواد",
                callback_data=f"back_subjects:{user_id}"
            )
        ],
    ])
