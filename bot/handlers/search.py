from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ForceReply,
)
from telegram.ext import ContextTypes

from bot.database.client import supabase


MAX_RESULTS_PER_TYPE = 5
MAX_TOTAL_RESULTS = 20


def search_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔎 بحث جديد",
                callback_data=f"main:search:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 القائمة الرئيسية",
                callback_data=f"back_main:{user_id}",
            )
        ],
    ])


def result_keyboard(results, user_id):
    keyboard = []

    for result in results:
        result_type = result["type"]
        item_id = result["id"]
        subject_id = result.get("subject_id")

        if result_type == "subject":
            keyboard.append([
                InlineKeyboardButton(
                    text=f"📘 {result['name']}",
                    callback_data=(
                        f"subject:{item_id}:{user_id}"
                    ),
                )
            ])

        elif result_type == "file":
            keyboard.append([
                InlineKeyboardButton(
                    text=f"📄 {result['name']}",
                    callback_data=(
                        f"file:{item_id}:{user_id}"
                    ),
                )
            ])

        elif result_type == "summary":
            keyboard.append([
                InlineKeyboardButton(
                    text=f"📝 {result['name']}",
                    callback_data=(
                        f"study_item:summaries:"
                        f"{item_id}:{subject_id}:{user_id}"
                    ),
                )
            ])

        elif result_type == "drawing":
            keyboard.append([
                InlineKeyboardButton(
                    text=f"🎨 {result['name']}",
                    callback_data=(
                        f"study_item:drawings:"
                        f"{item_id}:{subject_id}:{user_id}"
                    ),
                )
            ])

    keyboard.extend(
        search_keyboard(user_id).inline_keyboard
    )

    return InlineKeyboardMarkup(keyboard)


def _escape_search_text(text):
    return (
        text
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
        .replace(",", "\\,")
    )


async def start_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    user_id = query.from_user.id

    context.user_data["search_mode"] = True
    context.user_data["search_owner_id"] = user_id

    await query.answer()

    await query.edit_message_text(
        "🔎 البحث في LabBase\n\n"
        "أرسل الآن اسم المادة أو الملف أو الملخص أو الرسم "
        "الذي تريد البحث عنه.\n\n"
        "مثال:\n"
        "• Anatomy\n"
        "• Cell\n"
        "• Lecture 1\n\n"
        "للخروج من البحث استخدم /start."
    )

    await query.message.reply_text(
        "✏️ اكتب كلمة البحث هنا:",
        reply_markup=ForceReply(
            selective=True
        ),
    )


async def handle_search_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return False

    if update.effective_user is None:
        return False

    if not context.user_data.get("search_mode"):
        return False

    user_id = update.effective_user.id

    owner_id = context.user_data.get(
        "search_owner_id"
    )

    if owner_id is not None:
        try:
            owner_id = int(owner_id)
        except (TypeError, ValueError):
            owner_id = None

    if owner_id is not None and owner_id != user_id:
        return False

    text = (
        update.message.text
        or ""
    ).strip()

    if not text:
        await update.message.reply_text(
            "🔎 اكتب كلمة أو اسم حتى أبحث عنه."
        )
        return True

    if text.startswith("/"):
        return False

    if len(text) < 2:
        await update.message.reply_text(
            "⚠️ اكتب حرفين على الأقل للبحث."
        )
        return True

    if len(text) > 100:
        await update.message.reply_text(
            "⚠️ كلمة البحث طويلة جداً.\n"
            "حاول استخدام كلمة أو اسم أقصر."
        )
        return True

    context.user_data["search_mode"] = False
    context.user_data.pop(
        "search_owner_id",
        None,
    )

    search_text = _escape_search_text(text)

    results = []

    # ========================================================
    # Subjects
    # ========================================================

    try:
        response = (
            supabase
            .table("subjects")
            .select(
                "id,stage_id,name,description"
            )
            .eq("is_active", True)
            .or_(
                f"name.ilike.%{search_text}%,"
                f"description.ilike.%{search_text}%"
            )
            .limit(MAX_RESULTS_PER_TYPE)
            .execute()
        )

        for item in response.data or []:
            results.append({
                "type": "subject",
                "id": item["id"],
                "name": item.get("name") or "مادة",
                "description": item.get(
                    "description"
                ),
            })

    except Exception as exc:
        print(
            "SEARCH SUBJECTS ERROR:",
            type(exc).__name__,
            exc,
        )

    # ========================================================
    # Files
    # ========================================================

    try:
        response = (
            supabase
            .table("files")
            .select(
                "id,subject_id,name,description"
            )
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .or_(
                f"name.ilike.%{search_text}%,"
                f"description.ilike.%{search_text}%"
            )
            .limit(MAX_RESULTS_PER_TYPE)
            .execute()
        )

        for item in response.data or []:
            results.append({
                "type": "file",
                "id": item["id"],
                "subject_id": item.get(
                    "subject_id"
                ),
                "name": item.get("name") or "ملف",
                "description": item.get(
                    "description"
                ),
            })

    except Exception as exc:
        print(
            "SEARCH FILES ERROR:",
            type(exc).__name__,
            exc,
        )

    # ========================================================
    # Summaries
    # ========================================================

    try:
        response = (
            supabase
            .table("summaries")
            .select(
                "id,subject_id,name,description"
            )
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .or_(
                f"name.ilike.%{search_text}%,"
                f"description.ilike.%{search_text}%"
            )
            .limit(MAX_RESULTS_PER_TYPE)
            .execute()
        )

        for item in response.data or []:
            results.append({
                "type": "summary",
                "id": item["id"],
                "subject_id": item.get(
                    "subject_id"
                ),
                "name": item.get("name") or "ملخص",
                "description": item.get(
                    "description"
                ),
            })

    except Exception as exc:
        print(
            "SEARCH SUMMARIES ERROR:",
            type(exc).__name__,
            exc,
        )

    # ========================================================
    # Drawings
    # ========================================================

    try:
        response = (
            supabase
            .table("drawings")
            .select(
                "id,subject_id,name,description"
            )
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .or_(
                f"name.ilike.%{search_text}%,"
                f"description.ilike.%{search_text}%"
            )
            .limit(MAX_RESULTS_PER_TYPE)
            .execute()
        )

        for item in response.data or []:
            results.append({
                "type": "drawing",
                "id": item["id"],
                "subject_id": item.get(
                    "subject_id"
                ),
                "name": item.get("name") or "رسم",
                "description": item.get(
                    "description"
                ),
            })

    except Exception as exc:
        print(
            "SEARCH DRAWINGS ERROR:",
            type(exc).__name__,
            exc,
        )

    results = results[:MAX_TOTAL_RESULTS]

    # ========================================================
    # No Results
    # ========================================================

    if not results:
        await update.message.reply_text(
            f"🔎 نتائج البحث عن: {text}\n\n"
            "❌ ما لكيت أي نتيجة مطابقة.\n\n"
            "جرب كلمة ثانية أو اسم المادة بشكل مختلف.",
            reply_markup=search_keyboard(user_id),
        )
        return True

    # ========================================================
    # Count Results
    # ========================================================

    counts = {
        "subject": 0,
        "file": 0,
        "summary": 0,
        "drawing": 0,
    }

    for result in results:
        counts[result["type"]] += 1

    text_parts = [
        f"🔎 نتائج البحث عن: {text}",
        "",
    ]

    if counts["subject"]:
        text_parts.append(
            f"📘 المواد: {counts['subject']}"
        )

    if counts["file"]:
        text_parts.append(
            f"📄 الملفات: {counts['file']}"
        )

    if counts["summary"]:
        text_parts.append(
            f"📝 الملخصات: {counts['summary']}"
        )

    if counts["drawing"]:
        text_parts.append(
            f"🎨 الرسومات: {counts['drawing']}"
        )

    text_parts.extend([
        "",
        "اختر النتيجة التي تريد فتحها:",
    ])

    await update.message.reply_text(
        "\n".join(text_parts),
        reply_markup=result_keyboard(
            results,
            user_id,
        ),
    )

    return True
