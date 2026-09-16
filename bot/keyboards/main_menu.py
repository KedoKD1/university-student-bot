from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)


# ============================================================
# Main Menu Keyboard
# ============================================================

def main_menu_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="📚 المراحل الدراسية",
                callback_data=(
                    f"main:stages:{user_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 مواعيد الامتحانات",
                callback_data=(
                    f"main:exams:{user_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="📅 الجداول",
                callback_data=(
                    f"main:schedule:{user_id}"
                ),
            ),
            InlineKeyboardButton(
                text="🔎 البحث",
                callback_data=(
                    f"main:search:{user_id}"
                ),
            ),
        ],
        [
            InlineKeyboardButton(
                text="📝 الدرجات",
                callback_data=(
                    f"main:grades:{user_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="⚙️ الإعدادات",
                callback_data=(
                    f"main:settings:{user_id}"
                ),
            )
        ],
    ])


# ============================================================
# Back To Main Menu Keyboard
# ============================================================

def back_main_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="🏠 القائمة الرئيسية",
                callback_data=(
                    f"back_main:{user_id}"
                ),
            )
        ]
    ])
