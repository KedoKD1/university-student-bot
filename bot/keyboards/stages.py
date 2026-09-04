from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def stages_keyboard(stages):
    keyboard = []

    for stage in stages:
        stage_id = stage["id"]
        stage_number = stage["stage_number"]
        is_active = stage["is_active"]

        if is_active:
            text = f"📚 المرحلة {stage_number}"
            callback_data = f"stage:{stage_id}"
        else:
            text = f"🔒 المرحلة {stage_number}"
            callback_data = f"locked:{stage_id}"

        keyboard.append([
            InlineKeyboardButton(
                text=text,
                callback_data=callback_data
            )
        ])

    return InlineKeyboardMarkup(keyboard)
