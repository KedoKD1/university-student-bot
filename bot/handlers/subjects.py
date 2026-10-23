from bot.utils.logging_security import log_error

from telegram import Update
from telegram.ext import ContextTypes

from bot.database.client import supabase
from bot.utils.content_access import active_subject

from bot.keyboards.subjects import PAGE_SIZE, back_stages_keyboard, subjects_keyboard
from bot.keyboards.content import content_keyboard


async def _get_active_subjects(stage_id):
    response = (
        supabase
        .table("subjects")
        .select("*")
        .eq("stage_id", stage_id)
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )

    return response.data or []


async def show_subjects(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    stage_id: str,
    page: int = 0,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    user_id = query.from_user.id

    await query.answer()

    try:
        stages = supabase.table("stages").select("stage_number, is_active").eq(
            "id", stage_id
        ).limit(1).execute().data or []
        if not stages or not stages[0].get("is_active"):
            await query.edit_message_text(
                "❌ هذه المرحلة غير متاحة حاليًا. اختر مرحلة أخرى.",
                reply_markup=back_stages_keyboard(user_id),
            )
            return
        subjects = await _get_active_subjects(stage_id)
    except Exception as exc:
        log_error('STUDENT SUBJECTS ERROR:', exc)
        await query.edit_message_text(
            "❌ تعذر تحميل المواد حاليًا. يمكنك العودة والمحاولة لاحقًا.",
            reply_markup=back_stages_keyboard(user_id),
        )
        return

    total_pages = max(1, (len(subjects) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    text = f"📘 مواد المرحلة {stages[0]['stage_number']}\n\n"
    text += "اختر المادة لعرض محتواها." if subjects else (
        "لا توجد مواد متاحة لهذه المرحلة حاليًا. يمكنك الرجوع واختيار مرحلة أخرى."
    )
    if total_pages > 1:
        text += f"\n\n📄 الصفحة {page + 1} من {total_pages}"

    await query.edit_message_text(
        text,
        reply_markup=subjects_keyboard(
            subjects,
            user_id,
            stage_id,
            page,
        ),
    )


async def subjects_page_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    if len(parts) != 4:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    stage_id = parts[1]
    page_text = parts[2]
    owner_id = parts[3]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار ليس لك.\n"
            "استخدم /start لفتح قائمتك الخاصة.",
            show_alert=True,
        )
        return

    try:
        page = int(page_text)
    except ValueError:
        await query.answer(
            "❌ صفحة غير صالحة.",
            show_alert=True,
        )
        return

    if page < 0:
        page = 0

    await show_subjects(
        update,
        context,
        stage_id,
        page,
    )


async def subject_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    subject_id = parts[1]
    owner_id = parts[2]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار ليس لك.\n"
            "استخدم /start لفتح قائمتك الخاصة.",
            show_alert=True,
        )
        return

    await query.answer()

    try:
        subject = active_subject(supabase, subject_id)
    except Exception as exc:
        log_error('STUDENT SUBJECT ERROR:', exc)
        await query.edit_message_text(
            "❌ تعذر تحميل المادة حاليًا. يمكنك العودة والمحاولة لاحقًا.",
            reply_markup=back_stages_keyboard(query.from_user.id),
        )
        return

    if subject is None:
        await query.edit_message_text(
            "❌ هذه المادة غير متاحة حاليًا. اختر مادة أخرى.",
            reply_markup=back_stages_keyboard(query.from_user.id),
        )
        return

    description = (
        subject.get("description")
        or "لا يوجد وصف للمادة حاليًا."
    )

    stage_id = subject.get("stage_id")

    if stage_id is None:
        await query.edit_message_text(
            "❌ هذه المادة غير متاحة حاليًا. اختر مادة أخرى.",
            reply_markup=back_stages_keyboard(query.from_user.id),
        )
        return

    await query.edit_message_text(
        f"📘 المادة: {subject['name']}\n\n"
        f"{description}\n\n"
        "اختر نوع المحتوى:",
        reply_markup=content_keyboard(
            subject_id,
            query.from_user.id,
            stage_id,
        ),
    )


async def back_to_subjects(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    stage_id = parts[1]
    owner_id = parts[2]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار ليس لك.",
            show_alert=True,
        )
        return

    await show_subjects(
        update,
        context,
        stage_id,
        0,
    )


async def back_to_stages(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    parts = query.data.split(":")

    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    owner_id = parts[1]

    if str(query.from_user.id) != owner_id:
        await query.answer(
            "⛔ هذا الاختيار ليس لك.",
            show_alert=True,
        )
        return

    await query.answer()

    from bot.handlers.stages import show_stages
    await show_stages(update, context, edit_message=True)
