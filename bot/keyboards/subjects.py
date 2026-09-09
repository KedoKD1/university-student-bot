from telegram import InlineKeyboardButton, InlineKeyboardMarkup


PAGE_SIZE = 6


def subjects_keyboard(
    subjects,
    user_id,
    stage_id,
    page=0,
):
    total = len(subjects)

    total_pages = max(
        1,
        (total + PAGE_SIZE - 1) // PAGE_SIZE,
    )

    page = max(
        0,
        min(page, total_pages - 1),
    )

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE

    page_subjects = subjects[start:end]

    keyboard = []

    for subject in page_subjects:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📘 {subject['name']}",
                callback_data=(
                    f"subject:{subject['id']}:{user_id}"
                ),
            )
        ])

    navigation = []

    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️ السابق",
                callback_data=(
                    f"subjects_page:{stage_id}:{page - 1}:{user_id}"
                ),
            )
        )

    if page < total_pages - 1:
        navigation.append(
            InlineKeyboardButton(
                text="التالي ➡️",
                callback_data=(
                    f"subjects_page:{stage_id}:{page + 1}:{user_id}"
                ),
            )
        )

    if navigation:
        keyboard.append(navigation)

    if total_pages > 1:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📄 {page + 1} / {total_pages}",
                callback_data="noop",
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للمراحل",
            callback_data=f"back_stages:{user_id}",
        )
    ])

    return InlineKeyboardMarkup(keyboard)
