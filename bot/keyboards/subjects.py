from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def subjects_keyboard(subjects, user_id):
    keyboard = []

    for subject in subjects:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📘 {subject['name']}",
                callback_data=f"subject:{subject['id']}:{user_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للمراحل",
            callback_data=f"back_stages:{user_id}"
        )
    ])

    return InlineKeyboardMarkup(keyboard)
