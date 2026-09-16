from datetime import datetime, timezone

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from bot.database.client import supabase


# ============================================================
# Settings Helpers
# ============================================================

def _settings_keyboard(
    user_id: int,
    notifications_enabled: bool,
):
    notification_text = (
        "🔔 الإشعارات: مفعلة"
        if notifications_enabled
        else "🔕 الإشعارات: متوقفة"
    )

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="🎓 تغيير المرحلة",
                callback_data=f"main:settings:stage:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text=notification_text,
                callback_data=f"main:settings:notifications:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 إعادة ضبط الإعدادات",
                callback_data=f"main:settings:reset:{user_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🏠 القائمة الرئيسية",
                callback_data=f"back_main:{user_id}",
            )
        ],
    ])


def _stage_keyboard(
    stages,
    user_id: int,
):
    keyboard = []

    for stage in stages:
        stage_id = stage.get("id")
        stage_number = stage.get("stage_number")
        is_active = stage.get("is_active")

        if stage_id is None:
            continue

        if not is_active:
            continue

        keyboard.append([
            InlineKeyboardButton(
                text=f"📚 المرحلة {stage_number}",
                callback_data=(
                    f"main:settings:stage_select:"
                    f"{stage_id}:{user_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للإعدادات",
            callback_data=f"main:settings:back:{user_id}",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


async def _get_or_create_settings(
    user_id: int,
):
    try:
        response = (
            supabase
            .table("user_settings")
            .select(
                "id, telegram_id, "
                "notifications_enabled, "
                "selected_stage_id, "
                "updated_at"
            )
            .eq("telegram_id", user_id)
            .limit(1)
            .execute()
        )

        data = response.data or []

        if data:
            return data[0]

        response = (
            supabase
            .table("user_settings")
            .insert({
                "telegram_id": user_id,
                "notifications_enabled": True,
                "selected_stage_id": None,
            })
            .execute()
        )

        created = response.data or []

        if created:
            return created[0]

    except Exception as exc:
        print(
            "GET USER SETTINGS ERROR:",
            type(exc).__name__,
            exc,
        )

    return {
        "telegram_id": user_id,
        "notifications_enabled": True,
        "selected_stage_id": None,
    }


async def _update_settings(
    user_id: int,
    values: dict,
):
    values = dict(values)

    values["updated_at"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    try:
        response = (
            supabase
            .table("user_settings")
            .upsert(
                {
                    "telegram_id": user_id,
                    **values,
                },
                on_conflict="telegram_id",
            )
            .execute()
        )

        data = response.data or []

        if data:
            return data[0]

        return True

    except Exception as exc:
        print(
            "UPDATE USER SETTINGS ERROR:",
            type(exc).__name__,
            exc,
        )

        return None


# ============================================================
# Show Settings
# ============================================================

async def show_student_settings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return

    user_id = query.from_user.id

    settings = await _get_or_create_settings(
        user_id
    )

    notifications_enabled = bool(
        settings.get(
            "notifications_enabled",
            True,
        )
    )

    selected_stage_id = settings.get(
        "selected_stage_id"
    )

    stage_text = "غير محددة"

    if selected_stage_id is not None:
        try:
            response = (
                supabase
                .table("stages")
                .select(
                    "stage_number"
                )
                .eq(
                    "id",
                    selected_stage_id,
                )
                .limit(1)
                .execute()
            )

            stages = response.data or []

            if stages:
                stage_text = (
                    f"المرحلة "
                    f"{stages[0].get('stage_number')}"
                )

        except Exception as exc:
            print(
                "GET SELECTED STAGE ERROR:",
                type(exc).__name__,
                exc,
            )

    await query.answer()

    await query.edit_message_text(
        "⚙️ إعدادات الطالب\n\n"
        f"🎓 المرحلة الحالية: {stage_text}\n"
        f"{'🔔 الإشعارات: مفعلة' if notifications_enabled else '🔕 الإشعارات: متوقفة'}\n\n"
        "اختر الإعداد الذي تريد تغييره:",
        reply_markup=_settings_keyboard(
            user_id,
            notifications_enabled,
        ),
    )


# ============================================================
# Show Stage Selection
# ============================================================

async def show_settings_stages(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
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
            "GET SETTINGS STAGES ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ تعذر تحميل المراحل حالياً.",
            show_alert=True,
        )
        return

    if not stages:
        await query.answer(
            "❌ لا توجد مراحل متاحة حالياً.",
            show_alert=True,
        )
        return

    await query.answer()

    await query.edit_message_text(
        "🎓 تغيير المرحلة\n\n"
        "اختر مرحلتك الدراسية:",
        reply_markup=_stage_keyboard(
            stages,
            user_id,
        ),
    )


# ============================================================
# Select Stage
# ============================================================

async def select_settings_stage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
        or not query.data
    ):
        return

    parts = query.data.split(":")

    if len(parts) != 5:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    stage_id = parts[3]
    owner_id = parts[4]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.\n"
            "استخدم /start حتى تحصل على قائمتك الخاصة.",
            show_alert=True,
        )
        return

    try:
        stage_id_int = int(stage_id)

    except (TypeError, ValueError):
        await query.answer(
            "❌ المرحلة غير صالحة.",
            show_alert=True,
        )
        return

    try:
        response = (
            supabase
            .table("stages")
            .select(
                "id, stage_number, is_active"
            )
            .eq(
                "id",
                stage_id_int,
            )
            .limit(1)
            .execute()
        )

        stages = response.data or []

    except Exception as exc:
        print(
            "CHECK SETTINGS STAGE ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ حدث خطأ أثناء اختيار المرحلة.",
            show_alert=True,
        )
        return

    if not stages:
        await query.answer(
            "❌ المرحلة غير موجودة.",
            show_alert=True,
        )
        return

    stage = stages[0]

    if not stage.get("is_active"):
        await query.answer(
            "🔒 هذه المرحلة غير متاحة حالياً.",
            show_alert=True,
        )
        return

    result = await _update_settings(
        query.from_user.id,
        {
            "selected_stage_id": stage_id_int,
        },
    )

    if result is None:
        await query.answer(
            "❌ تعذر حفظ المرحلة.",
            show_alert=True,
        )
        return

    await query.answer(
        "✅ تم حفظ مرحلتك الدراسية."
    )

    await show_student_settings(
        update,
        context,
    )


# ============================================================
# Toggle Notifications
# ============================================================

async def toggle_student_notifications(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return

    user_id = query.from_user.id

    settings = await _get_or_create_settings(
        user_id
    )

    current_value = bool(
        settings.get(
            "notifications_enabled",
            True,
        )
    )

    new_value = not current_value

    result = await _update_settings(
        user_id,
        {
            "notifications_enabled": new_value,
        },
    )

    if result is None:
        await query.answer(
            "❌ تعذر تحديث الإشعارات.",
            show_alert=True,
        )
        return

    await query.answer(
        "🔔 تم تفعيل الإشعارات."
        if new_value
        else
        "🔕 تم إيقاف الإشعارات."
    )

    await show_student_settings(
        update,
        context,
    )


# ============================================================
# Reset Settings
# ============================================================

async def reset_student_settings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return

    user_id = query.from_user.id

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="✅ نعم، إعادة الضبط",
                callback_data=(
                    f"main:settings:reset_confirm:"
                    f"{user_id}"
                ),
            ),
        ],
        [
            InlineKeyboardButton(
                text="❌ إلغاء",
                callback_data=(
                    f"main:settings:back:"
                    f"{user_id}"
                ),
            ),
        ],
    ])

    await query.answer()

    await query.edit_message_text(
        "⚠️ إعادة ضبط الإعدادات\n\n"
        "سيتم إرجاع:\n"
        "• المرحلة الدراسية → غير محددة\n"
        "• الإشعارات → مفعلة\n\n"
        "هل أنت متأكد؟",
        reply_markup=keyboard,
    )


async def confirm_reset_student_settings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
    ):
        return

    user_id = query.from_user.id

    result = await _update_settings(
        user_id,
        {
            "notifications_enabled": True,
            "selected_stage_id": None,
        },
    )

    if result is None:
        await query.answer(
            "❌ تعذر إعادة ضبط الإعدادات.",
            show_alert=True,
        )
        return

    await query.answer(
        "✅ تم إعادة ضبط إعداداتك."
    )

    await show_student_settings(
        update,
        context,
    )


# ============================================================
# Back To Settings
# ============================================================

async def back_to_student_settings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await show_student_settings(
        update,
        context,
    )


# ============================================================
# Main Settings Callback Router
# ============================================================

async def student_settings_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if (
        query is None
        or query.from_user is None
        or not query.data
    ):
        return

    parts = query.data.split(":")

    if len(parts) < 4:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    if parts[0] != "main" or parts[1] != "settings":
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    owner_id = parts[-1]

    try:
        owner_id_int = int(owner_id)

    except (TypeError, ValueError):
        await query.answer(
            "❌ المستخدم غير صالح.",
            show_alert=True,
        )
        return

    if query.from_user.id != owner_id_int:
        await query.answer(
            "⛔ هذا الاختيار مو إلك.\n"
            "استخدم /start حتى تحصل على قائمتك الخاصة.",
            show_alert=True,
        )
        return

    action = parts[2]

    if action == "stage" and len(parts) == 4:
        await show_settings_stages(
            update,
            context,
        )
        return

    if action == "stage_select" and len(parts) == 5:
        await select_settings_stage(
            update,
            context,
        )
        return

    if action == "notifications" and len(parts) == 4:
        await toggle_student_notifications(
            update,
            context,
        )
        return

    if action == "reset" and len(parts) == 4:
        await reset_student_settings(
            update,
            context,
        )
        return

    if action == "reset_confirm" and len(parts) == 4:
        await confirm_reset_student_settings(
            update,
            context,
        )
        return

    if action == "back" and len(parts) == 4:
        await back_to_student_settings(
            update,
            context,
        )
        return

    await query.answer(
        "❌ اختيار غير صالح.",
        show_alert=True,
    )
