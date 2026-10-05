from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.database.client import supabase
from bot.utils.permissions import (
    PERMISSION_MANAGE_SUBJECTS,
    has_permission,
)


# =========================
# Conversation States
# =========================

ADD_NAME, ADD_DESCRIPTION, ADD_ORDER = range(3)
EDIT_NAME, EDIT_DESCRIPTION, EDIT_ORDER = range(3, 6)


# =========================
# Keyboards
# =========================

def stages_admin_keyboard(stages):
    keyboard = []

    for stage in stages:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📚 المرحلة {stage['stage_number']}",
                callback_data=f"manage_stage:{stage['id']}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للوحة الإدارة",
            callback_data="admin_back",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def subjects_admin_keyboard(subjects, stage_id, owner_id):
    keyboard = []

    for subject in subjects:
        status = "🟢" if subject["is_active"] else "🔴"

        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {subject['name']}",
                callback_data=(
                    f"manage_subject:{subject['id']}:{stage_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="➕ إضافة مادة",
            callback_data=f"add_subject:{stage_id}:{owner_id}",
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للمراحل",
            callback_data="admin_subjects",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def subject_manage_keyboard(
    subject_id,
    stage_id,
    is_active,
    owner_id,
):
    if is_active:
        toggle_text = "🔴 تعطيل المادة"
        toggle_callback = (
            f"disable_subject:{subject_id}:{stage_id}"
        )
    else:
        toggle_text = "🟢 تفعيل المادة"
        toggle_callback = (
            f"enable_subject:{subject_id}:{stage_id}"
        )

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="✏️ تعديل المادة",
                callback_data=(
                    f"edit_subject:{subject_id}:{stage_id}:{owner_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text=toggle_text,
                callback_data=toggle_callback,
            )
        ],
        [
            InlineKeyboardButton(
                text="🗑️ حذف المادة",
                callback_data=(
                    f"admin_delete_subject:{subject_id}:{stage_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ رجوع للمواد",
                callback_data=(
                    f"admin_stage_subjects:{stage_id}"
                ),
            )
        ],
    ])


def delete_subject_confirm_keyboard(
    subject_id,
    stage_id,
):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="🗑️ نعم، احذف المادة",
                callback_data=(
                    f"admin_confirm_delete_subject:"
                    f"{subject_id}:{stage_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ إلغاء",
                callback_data=(
                    f"manage_subject:{subject_id}:{stage_id}"
                ),
            )
        ],
    ])


def after_save_keyboard(stage_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="⬅️ العودة إلى المواد",
                callback_data=(
                    f"admin_stage_subjects:{stage_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="🛠️ لوحة الإدارة",
                callback_data="admin_back",
            )
        ],
    ])


# =========================
# Helpers
# =========================

def clear_subject_conversation(context):
    keys = [
        "admin_subject_stage_id",
        "admin_subject_id",
        "admin_subject_name",
        "admin_subject_description",
        "admin_subject_owner_id",
    ]

    for key in keys:
        context.admin_data.pop(key, None)


def normalize_text(text):
    return " ".join(text.strip().split())


def normalize_description(text):
    text = text.strip()

    if text in {
        "-",
        "لا يوجد",
        "بدون وصف",
        "بدون",
    }:
        return None

    return text


def is_subject_session_owner(context, user_id):
    return context.admin_data.get("admin_subject_owner_id") == user_id


async def check_subject_message_access(update, context, state, required_keys):
    user = update.effective_user
    owner_id = context.admin_data.get("admin_subject_owner_id")

    if user is None:
        return state

    if owner_id is not None and owner_id != user.id:
        if update.message:
            await update.message.reply_text("⛔ هذه العملية ليست لك.")
        return state

    if not await has_permission(user.id, PERMISSION_MANAGE_SUBJECTS, refresh=True):
        clear_subject_conversation(context)
        if update.message:
            await update.message.reply_text("⛔ ليس لديك صلاحية.")
        return ConversationHandler.END

    if owner_id is None or any(
        key not in context.admin_data or (
            key != "admin_subject_description" and not context.admin_data.get(key)
        )
        for key in required_keys
    ):
        clear_subject_conversation(context)
        if update.message:
            await update.message.reply_text(
                "❌ انتهت بيانات العملية.\nابدأ من لوحة الإدارة مرة أخرى."
            )
        return ConversationHandler.END

    if update.message is None or update.message.text is None:
        return state

    return None


async def parse_subject_operation(query, context, expected_length):
    if query is None or query.from_user is None:
        return None

    if not await has_permission(query.from_user.id, PERMISSION_MANAGE_SUBJECTS, refresh=True):
        if is_subject_session_owner(context, query.from_user.id):
            clear_subject_conversation(context)
        await query.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return None

    parts = (query.data or "").split(":")
    if len(parts) != expected_length or not all(parts):
        await query.answer("❌ اختيار غير صالح.", show_alert=True)
        return None

    try:
        owner_id = int(parts[-1])
    except ValueError:
        await query.answer("❌ اختيار غير صالح.", show_alert=True)
        return None

    if owner_id != query.from_user.id or context.admin_data.get(
        "admin_subject_owner_id", owner_id
    ) != owner_id:
        await query.answer("⛔ هذه العملية ليست لك.", show_alert=True)
        return None

    return parts[:-1]


async def get_stage_subjects(stage_id):
    response = (
        supabase
        .table("subjects")
        .select(
            "id, name, description, sort_order, is_active"
        )
        .eq("stage_id", stage_id)
        .order("sort_order")
        .execute()
    )

    return response.data or []


async def send_subjects_list(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    stage_id,
    owner_id,
):
    subjects = await get_stage_subjects(stage_id)

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "📚 مواد المرحلة\n\n"
            "اختر المادة لإدارتها أو أضف مادة جديدة:"
        ),
        reply_markup=subjects_admin_keyboard(
            subjects,
            stage_id,
            owner_id,
        ),
    )


async def show_subject_details(
    query,
    subject_id,
    stage_id,
):
    response = (
        supabase
        .table("subjects")
        .select("*")
        .eq("id", subject_id)
        .eq("stage_id", stage_id)
        .limit(1)
        .execute()
    )

    subjects = response.data or []

    if not subjects:
        await query.edit_message_text(
            "❌ المادة غير موجودة."
        )
        return

    subject = subjects[0]

    status = (
        "🟢 مفعّلة"
        if subject["is_active"]
        else "🔴 معطّلة"
    )

    description = (
        subject.get("description")
        or "لا يوجد وصف."
    )

    await query.edit_message_text(
        f"📘 {subject['name']}\n\n"
        f"الوصف:\n{description}\n\n"
        f"الترتيب: {subject['sort_order']}\n"
        f"الحالة: {status}",
        reply_markup=subject_manage_keyboard(
            subject_id,
            stage_id,
            subject["is_active"],
            query.from_user.id,
        ),
    )


# =========================
# Main Admin Subjects
# =========================

async def admin_subjects(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await has_permission(
        query.from_user.id,
        PERMISSION_MANAGE_SUBJECTS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    await query.answer()

    response = (
        supabase
        .table("stages")
        .select("id, stage_number, is_active")
        .order("stage_number")
        .execute()
    )

    stages = response.data or []

    if not stages:
        await query.edit_message_text(
            "❌ لا توجد مراحل في قاعدة البيانات."
        )
        return

    await query.edit_message_text(
        "📚 إدارة المواد\n\n"
        "اختر المرحلة:",
        reply_markup=stages_admin_keyboard(stages),
    )


async def manage_stage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await has_permission(
        query.from_user.id,
        PERMISSION_MANAGE_SUBJECTS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = (query.data or "").split(":")

    if len(parts) != 2 or not all(parts):
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    stage_id = parts[1]

    await query.answer()

    await show_stage_subjects(
        query,
        stage_id,
    )


async def back_to_stage_subjects(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await has_permission(
        query.from_user.id,
        PERMISSION_MANAGE_SUBJECTS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = (query.data or "").split(":")

    if len(parts) != 2 or not all(parts):
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    stage_id = parts[1]

    await query.answer()

    await show_stage_subjects(
        query,
        stage_id,
    )


async def show_stage_subjects(
    query,
    stage_id,
):
    subjects = await get_stage_subjects(stage_id)

    await query.edit_message_text(
        "📚 مواد المرحلة\n\n"
        "اختر المادة لإدارتها أو أضف مادة جديدة:",
        reply_markup=subjects_admin_keyboard(
            subjects,
            stage_id,
            query.from_user.id,
        ),
    )


# =========================
# Manage Subject
# =========================

async def manage_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await has_permission(
        query.from_user.id,
        PERMISSION_MANAGE_SUBJECTS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = (query.data or "").split(":")

    if len(parts) != 3 or not all(parts):
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    subject_id = parts[1]
    stage_id = parts[2]

    await query.answer()

    await show_subject_details(
        query,
        subject_id,
        stage_id,
    )


# =========================
# Add Subject
# =========================

async def start_add_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    parts = await parse_subject_operation(query, context, 3)
    if parts is None:
        return None

    stage_id = parts[1]

    try:
        response = supabase.table("stages").select("id").eq("id", stage_id).limit(1).execute()
    except Exception as exc:
        print("SUBJECT STAGE ERROR:", type(exc).__name__, exc)
        clear_subject_conversation(context)
        await query.answer("❌ تعذر بدء العملية.", show_alert=True)
        return ConversationHandler.END
    if not response.data:
        clear_subject_conversation(context)
        await query.answer("❌ المرحلة غير موجودة.", show_alert=True)
        return ConversationHandler.END

    clear_subject_conversation(context)
    context.admin_data["admin_subject_owner_id"] = query.from_user.id

    context.admin_data["admin_subject_stage_id"] = stage_id

    await query.answer()

    await query.edit_message_text(
        "➕ إضافة مادة جديدة\n\n"
        "أرسل اسم المادة:\n\n"
        "للإلغاء استخدم /cancel"
    )

    return ADD_NAME


async def receive_add_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    access = await check_subject_message_access(
        update, context, ADD_NAME, ('admin_subject_stage_id',),
    )
    if access is not None:
        return access

    name = normalize_text(update.message.text)

    if not name:
        await update.message.reply_text(
            "❌ اسم المادة لا يمكن أن يكون فارغاً.\n\n"
            "أرسل اسم المادة مرة أخرى:"
        )
        return ADD_NAME

    stage_id = context.admin_data.get(
        "admin_subject_stage_id"
    )

    if not stage_id:
        await update.message.reply_text(
            "❌ انتهت عملية الإضافة.\n"
            "ابدأ من لوحة الإدارة مرة أخرى."
        )

        clear_subject_conversation(context)

        return ConversationHandler.END

    try:
        response = (
            supabase
            .table("subjects")
            .select("id")
            .eq("stage_id", stage_id)
            .eq("name", name)
            .limit(1)
            .execute()
        )

    except Exception as exc:
        print("SUBJECT NAME CHECK ERROR:", type(exc).__name__, exc)
        clear_subject_conversation(context)
        await update.message.reply_text("❌ تعذر التحقق من اسم المادة.")
        return ConversationHandler.END

    if response.data:
        await update.message.reply_text(
            "⚠️ توجد مادة بهذا الاسم في هذه المرحلة بالفعل.\n\n"
            "أرسل اسم مادة مختلف:"
        )

        return ADD_NAME

    context.admin_data["admin_subject_name"] = name

    await update.message.reply_text(
        "📝 أرسل وصف المادة.\n\n"
        "إذا ما تريد وصف، أرسل: -"
    )

    return ADD_DESCRIPTION


async def receive_add_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    access = await check_subject_message_access(
        update, context, ADD_DESCRIPTION, ('admin_subject_stage_id', 'admin_subject_name'),
    )
    if access is not None:
        return access

    description = normalize_description(
        update.message.text
    )

    context.admin_data["admin_subject_description"] = (
        description
    )

    await update.message.reply_text(
        "🔢 أرسل ترتيب المادة.\n\n"
        "مثال: 1"
    )

    return ADD_ORDER


async def receive_add_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    access = await check_subject_message_access(
        update, context, ADD_ORDER,
        ("admin_subject_stage_id", "admin_subject_name", "admin_subject_description"),
    )
    if access is not None:
        return access

    text = update.message.text.strip()

    try:
        sort_order = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ الترتيب يجب أن يكون رقماً صحيحاً.\n\n"
            "أرسل الترتيب مرة أخرى:"
        )

        return ADD_ORDER

    if sort_order < 1:
        await update.message.reply_text(
            "❌ الترتيب يجب أن يكون 1 أو أكبر.\n\n"
            "أرسل الترتيب مرة أخرى:"
        )

        return ADD_ORDER

    stage_id = context.admin_data.get(
        "admin_subject_stage_id"
    )

    name = context.admin_data.get(
        "admin_subject_name"
    )

    description = context.admin_data.get(
        "admin_subject_description"
    )

    if not stage_id or not name:
        await update.message.reply_text(
            "❌ انتهت عملية الإضافة.\n"
            "ابدأ من لوحة الإدارة مرة أخرى."
        )

        clear_subject_conversation(context)

        return ConversationHandler.END

    try:
        stage = supabase.table("stages").select("id").eq("id", stage_id).limit(1).execute()
        if not stage.data:
            raise ValueError("Stage no longer exists.")
        response = supabase.table("subjects").insert({
            "stage_id": stage_id,
            "name": name,
            "description": description,
            "sort_order": sort_order,
            "is_active": True,
        }).execute()

        if not response.data:
            raise ValueError("Supabase returned no saved subject.")

    except Exception as exc:
        print("SUBJECT SAVE ERROR:", type(exc).__name__, exc)
        clear_subject_conversation(context)
        await update.message.reply_text(
            "❌ حدث خطأ أثناء إضافة المادة.\n"
            "لم يتم حفظ المادة."
        )

        clear_subject_conversation(context)

        return ConversationHandler.END

    clear_subject_conversation(context)

    await update.message.reply_text(
        "✅ تمت إضافة المادة بنجاح.\n\n"
        f"📘 المادة: {name}\n"
        f"🔢 الترتيب: {sort_order}",
        reply_markup=after_save_keyboard(stage_id),
    )

    return ConversationHandler.END


# =========================
# Edit Subject
# =========================

async def start_edit_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    parts = await parse_subject_operation(query, context, 4)
    if parts is None:
        return None

    subject_id = parts[1]
    stage_id = parts[2]

    try:
        response = (
            supabase
            .table("subjects")
            .select("*")
            .eq("id", subject_id)
            .eq("stage_id", stage_id)
            .limit(1)
            .execute()
        )

    except Exception as exc:
        print("SUBJECT READ ERROR:", type(exc).__name__, exc)
        clear_subject_conversation(context)
        await query.answer("❌ تعذر بدء العملية.", show_alert=True)
        return ConversationHandler.END

    subjects = response.data or []

    if not subjects:
        clear_subject_conversation(context)
        await query.answer(
            "❌ المادة غير موجودة.",
            show_alert=True,
        )
        return ConversationHandler.END

    subject = subjects[0]

    clear_subject_conversation(context)
    context.admin_data["admin_subject_owner_id"] = query.from_user.id

    context.admin_data["admin_subject_stage_id"] = stage_id
    context.admin_data["admin_subject_id"] = subject_id

    await query.answer()

    await query.edit_message_text(
        "✏️ تعديل المادة\n\n"
        f"الاسم الحالي: {subject['name']}\n\n"
        "أرسل الاسم الجديد:\n\n"
        "للإلغاء استخدم /cancel"
    )

    return EDIT_NAME


async def receive_edit_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    access = await check_subject_message_access(
        update, context, EDIT_NAME, ('admin_subject_stage_id', 'admin_subject_id'),
    )
    if access is not None:
        return access

    name = normalize_text(update.message.text)

    if not name:
        await update.message.reply_text(
            "❌ اسم المادة لا يمكن أن يكون فارغاً.\n\n"
            "أرسل الاسم الجديد:"
        )

        return EDIT_NAME

    stage_id = context.admin_data.get(
        "admin_subject_stage_id"
    )

    subject_id = context.admin_data.get(
        "admin_subject_id"
    )

    if not stage_id or not subject_id:
        await update.message.reply_text(
            "❌ انتهت عملية التعديل.\n"
            "ابدأ من لوحة الإدارة مرة أخرى."
        )

        clear_subject_conversation(context)

        return ConversationHandler.END

    try:
        response = (
            supabase
            .table("subjects")
            .select("id")
            .eq("stage_id", stage_id)
            .eq("name", name)
            .neq("id", subject_id)
            .limit(1)
            .execute()
        )

    except Exception as exc:
        print("SUBJECT NAME CHECK ERROR:", type(exc).__name__, exc)
        clear_subject_conversation(context)
        await update.message.reply_text("❌ تعذر التحقق من اسم المادة.")
        return ConversationHandler.END

    if response.data:
        await update.message.reply_text(
            "⚠️ توجد مادة أخرى بهذا الاسم في نفس المرحلة.\n\n"
            "أرسل اسماً مختلفاً:"
        )

        return EDIT_NAME

    context.admin_data["admin_subject_name"] = name

    await update.message.reply_text(
        "📝 أرسل الوصف الجديد.\n\n"
        "إذا ما تريد وصف، أرسل: -"
    )

    return EDIT_DESCRIPTION


async def receive_edit_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    access = await check_subject_message_access(
        update, context, EDIT_DESCRIPTION, ('admin_subject_stage_id', 'admin_subject_id', 'admin_subject_name'),
    )
    if access is not None:
        return access

    description = normalize_description(
        update.message.text
    )

    context.admin_data["admin_subject_description"] = (
        description
    )

    await update.message.reply_text(
        "🔢 أرسل ترتيب المادة الجديد.\n\n"
        "مثال: 1"
    )

    return EDIT_ORDER


async def receive_edit_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    access = await check_subject_message_access(
        update, context, EDIT_ORDER,
        ("admin_subject_stage_id", "admin_subject_id", "admin_subject_name", "admin_subject_description"),
    )
    if access is not None:
        return access

    text = update.message.text.strip()

    try:
        sort_order = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ الترتيب يجب أن يكون رقماً صحيحاً.\n\n"
            "أرسل الترتيب مرة أخرى:"
        )

        return EDIT_ORDER

    if sort_order < 1:
        await update.message.reply_text(
            "❌ الترتيب يجب أن يكون 1 أو أكبر.\n\n"
            "أرسل الترتيب مرة أخرى:"
        )

        return EDIT_ORDER

    stage_id = context.admin_data.get(
        "admin_subject_stage_id"
    )

    subject_id = context.admin_data.get(
        "admin_subject_id"
    )

    name = context.admin_data.get(
        "admin_subject_name"
    )

    description = context.admin_data.get(
        "admin_subject_description"
    )

    if not stage_id or not subject_id or not name:
        await update.message.reply_text(
            "❌ انتهت عملية التعديل.\n"
            "ابدأ من لوحة الإدارة مرة أخرى."
        )

        clear_subject_conversation(context)

        return ConversationHandler.END

    try:
        response = supabase.table("subjects").update({
            "name": name,
            "description": description,
            "sort_order": sort_order,
        }).eq(
            "id",
            subject_id,
        ).eq(
            "stage_id",
            stage_id,
        ).execute()

        if not response.data:
            raise ValueError("Supabase returned no saved subject.")

    except Exception as exc:
        print("SUBJECT SAVE ERROR:", type(exc).__name__, exc)
        clear_subject_conversation(context)
        await update.message.reply_text(
            "❌ حدث خطأ أثناء تعديل المادة.\n"
            "لم يتم حفظ التعديلات."
        )

        clear_subject_conversation(context)

        return ConversationHandler.END

    clear_subject_conversation(context)

    await update.message.reply_text(
        "✅ تم تعديل المادة بنجاح.\n\n"
        f"📘 المادة: {name}\n"
        f"🔢 الترتيب: {sort_order}",
        reply_markup=after_save_keyboard(stage_id),
    )

    return ConversationHandler.END


# =========================
# Cancel
# =========================

async def cancel_subject_operation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    if user is None:
        return None
    if context.admin_data.get("admin_subject_owner_id") is None:
        clear_subject_conversation(context)
        return ConversationHandler.END
    if not is_subject_session_owner(context, user.id):
        if update.message:
            await update.message.reply_text("⛔ هذه العملية ليست لك.")
        return None

    allowed = await has_permission(user.id, PERMISSION_MANAGE_SUBJECTS, refresh=True)
    clear_subject_conversation(context)
    if update.message:
        await update.message.reply_text(
            "↩️ تم إلغاء العملية." if allowed else "⛔ ليس لديك صلاحية."
        )
    return ConversationHandler.END


# =========================
# Subject Conversation Handler
# =========================

async def back_from_subject_operation(update, context):
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return None
    if context.admin_data.get("admin_subject_owner_id") != user.id:
        await query.answer("⛔ هذه العملية ليست لك.", show_alert=True)
        return None
    prefix = (query.data or "").split(":", 1)[0]
    if not await has_permission(user.id, PERMISSION_MANAGE_SUBJECTS, refresh=True):
        clear_subject_conversation(context)
        await query.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return ConversationHandler.END

    from bot.handlers.admin import admin_back
    navigation = {
        "admin_subjects": admin_subjects,
        "admin_stage_subjects": back_to_stage_subjects,
        "manage_stage": manage_stage,
        "manage_subject": manage_subject,
        "admin_back": admin_back,
    }
    clear_subject_conversation(context)
    await navigation[prefix](update, context)
    return ConversationHandler.END


def subject_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                start_add_subject,
                pattern=r"^add_subject:",
            ),
            CallbackQueryHandler(
                start_edit_subject,
                pattern=r"^edit_subject:",
            ),
        ],
        states={
            ADD_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_add_name,
                )
            ],
            ADD_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_add_description,
                )
            ],
            ADD_ORDER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_add_order,
                )
            ],
            EDIT_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_edit_name,
                )
            ],
            EDIT_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_edit_description,
                )
            ],
            EDIT_ORDER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_edit_order,
                )
            ],
        },
        fallbacks=[
            CallbackQueryHandler(back_from_subject_operation, pattern='^(?:admin_subjects$|admin_stage_subjects:|manage_stage:|manage_subject:|admin_back$)'),
            CommandHandler(
                "cancel",
                cancel_subject_operation,
            )
        ],
        per_user=True,
        per_chat=True,
        allow_reentry=False,
    )


# =========================
# Enable / Disable Subject
# =========================

async def disable_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await set_subject_status(
        update,
        active=False,
    )


async def enable_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await set_subject_status(
        update,
        active=True,
    )


async def set_subject_status(
    update: Update,
    active: bool,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await has_permission(
        query.from_user.id,
        PERMISSION_MANAGE_SUBJECTS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    parts = (query.data or "").split(":")

    if len(parts) != 3 or not all(parts):
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return

    subject_id = parts[1]
    stage_id = parts[2]

    try:
        response = supabase.table("subjects").update({
            "is_active": active
        }).eq(
            "id",
            subject_id,
        ).eq(
            "stage_id",
            stage_id,
        ).execute()

        if not response.data:
            await query.answer("❌ المادة غير موجودة.", show_alert=True)
            return

    except Exception as exc:
        print("SUBJECT STATUS ERROR:", type(exc).__name__, exc)
        await query.answer(
            "❌ حدث خطأ أثناء تحديث حالة المادة.",
            show_alert=True,
        )
        return

    await query.answer(
        "✅ تم تفعيل المادة."
        if active
        else "✅ تم تعطيل المادة.",
        show_alert=True,
    )

    await show_subject_details(
        query,
        subject_id,
        stage_id,
    )
