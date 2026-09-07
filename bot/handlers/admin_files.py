from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from bot.database.client import supabase
from bot.handlers.admin import is_admin
# =========================
# Conversation States
# =========================
ADD_FILE_NAME, ADD_FILE_DESCRIPTION, ADD_FILE_ORDER, ADD_FILE_UPLOAD = range(4)
EDIT_FILE_NAME, EDIT_FILE_DESCRIPTION, EDIT_FILE_ORDER = range(4, 7)
# =========================
# Constants
# =========================
FILE_TYPES = {
    "document": "📄 مستند",
    "photo": "🖼️ صورة",
    "video": "🎥 فيديو",
    "audio": "🎵 صوت",
}
# =========================
# Helpers
# =========================
def clear_file_conversation(context):
    keys = [
        "admin_file_stage_id",
        "admin_file_subject_id",
        "admin_file_section_type",
        "admin_file_id",
        "admin_file_name",
        "admin_file_description",
        "admin_file_order",
    ]
    for key in keys:
        context.user_data.pop(key, None)
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
def section_name(section_type):
    if section_type == "theory":
        return "📖 النظري"
    return "🧪 العملي"
def section_keyboard(
    stage_id,
    subject_id,
):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="📖 النظري",
                callback_data=(
                    f"admin_file_section:theory:"
                    f"{subject_id}:{stage_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="🧪 العملي",
                callback_data=(
                    f"admin_file_section:practical:"
                    f"{subject_id}:{stage_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ رجوع للمواد",
                callback_data=(
                    f"admin_file_subjects:{stage_id}"
                ),
            )
        ],
    ])
def file_list_keyboard(
    files,
    stage_id,
    subject_id,
    section_type,
):
    keyboard = []
    for file in files:
        status = "🟢" if file["is_active"] else "🔴"
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {file['name']}",
                callback_data=(
                    f"manage_file:{file['id']}:"
                    f"{subject_id}:{section_type}"
                ),
            )
        ])
    keyboard.append([
        InlineKeyboardButton(
            text="➕ إضافة ملف",
            callback_data=(
                f"add_file:{stage_id}:{subject_id}:"
                f"{section_type}"
            ),
        )
    ])
    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للأقسام",
            callback_data=(
                f"admin_file_sections:{stage_id}:{subject_id}"
            ),
        )
    ])
    return InlineKeyboardMarkup(keyboard)
def file_manage_keyboard(
    file_id,
    stage_id,
    subject_id,
    section_type,
    is_active,
):
    if is_active:
        toggle_text = "🔴 تعطيل الملف"
        toggle_callback = (
            f"disable_file:{file_id}:{stage_id}:"
            f"{subject_id}:{section_type}"
        )
    else:
        toggle_text = "🟢 تفعيل الملف"
        toggle_callback = (
            f"enable_file:{file_id}:{stage_id}:"
            f"{subject_id}:{section_type}"
        )
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="✏️ تعديل البيانات",
                callback_data=(
                    f"edit_file:{file_id}:{stage_id}:"
                    f"{subject_id}:{section_type}"
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
                text="🗑️ حذف الملف",
                callback_data=(
                    f"delete_file:{file_id}:{stage_id}:"
                    f"{subject_id}:{section_type}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ رجوع للملفات",
                callback_data=(
                    f"admin_file_list:{stage_id}:"
                    f"{subject_id}:{section_type}"
                ),
            )
        ],
    ])
def delete_confirm_keyboard(
    file_id,
    stage_id,
    subject_id,
    section_type,
):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="🗑️ نعم، احذف",
                callback_data=(
                    f"confirm_delete_file:{file_id}:"
                    f"{stage_id}:{subject_id}:{section_type}"
                ),
            ),
            InlineKeyboardButton(
                text="❌ إلغاء",
                callback_data=(
                    f"manage_file:{file_id}:"
                    f"{subject_id}:{section_type}"
                ),
            ),
        ],
    ])
def after_save_keyboard(
    stage_id,
    subject_id,
    section_type,
):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="⬅️ العودة إلى الملفات",
                callback_data=(
                    f"admin_file_list:{stage_id}:"
                    f"{subject_id}:{section_type}"
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
# Database Helpers
# =========================
async def get_subjects(stage_id):
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
async def get_files(
    subject_id,
    section_type,
    include_inactive=True,
):
    query = (
        supabase
        .table("files")
        .select("*")
        .eq("subject_id", subject_id)
        .eq("section_type", section_type)
        .is_("deleted_at", "null")
        .order("sort_order")
    )
    if not include_inactive:
        query = query.eq("is_active", True)
    response = query.execute()
    return response.data or []
async def get_file(
    file_id,
    subject_id=None,
):
    query = (
        supabase
        .table("files")
        .select("*")
        .eq("id", file_id)
        .is_("deleted_at", "null")
    )
    if subject_id is not None:
        query = query.eq(
            "subject_id",
            subject_id,
        )
    response = query.limit(1).execute()
    files = response.data or []
    if not files:
        return None
    return files[0]
# =========================
# Admin Files Main
# =========================
async def admin_files(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    if not await is_admin(query.from_user.id):
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
    keyboard = []
    for stage in stages:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📚 المرحلة {stage['stage_number']}",
                callback_data=(
                    f"admin_file_stage:{stage['id']}"
                ),
            )
        ])
    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للوحة الإدارة",
            callback_data="admin_back",
        )
    ])
    await query.edit_message_text(
        "📄 إدارة الملفات\n\n"
        "اختر المرحلة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
async def admin_file_stage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return
    parts = query.data.split(":")
    if len(parts) != 2:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return
    stage_id = parts[1]
    await query.answer()
    subjects = await get_subjects(stage_id)
    keyboard = []
    for subject in subjects:
        status = "🟢" if subject["is_active"] else "🔴"
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {subject['name']}",
                callback_data=(
                    f"admin_file_subject:"
                    f"{subject['id']}:{stage_id}"
                ),
            )
        ])
    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ رجوع للمراحل",
            callback_data="admin_files",
        )
    ])
    if not subjects:
        await query.edit_message_text(
            "📄 إدارة الملفات\n\n"
            "لا توجد مواد مضافة لهذه المرحلة.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return
    await query.edit_message_text(
        "📄 إدارة الملفات\n\n"
        "اختر المادة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
async def admin_file_subject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return
    subject_id = parts[1]
    stage_id = parts[2]
    await query.answer()
    response = (
        supabase
        .table("subjects")
        .select("id, name, is_active")
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
    await query.edit_message_text(
        f"📄 إدارة ملفات\n"
        f"📘 {subject['name']}\n\n"
        "اختر القسم:",
        reply_markup=section_keyboard(
            stage_id,
            subject_id,
        ),
    )
async def admin_file_sections(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return
    stage_id = parts[1]
    subject_id = parts[2]
    await query.answer()
    response = (
        supabase
        .table("subjects")
        .select("id, name")
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
    await query.edit_message_text(
        f"📄 إدارة ملفات\n"
        f"📘 {subjects[0]['name']}\n\n"
        "اختر القسم:",
        reply_markup=section_keyboard(
            stage_id,
            subject_id,
        ),
    )
async def admin_file_section(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return
    parts = query.data.split(":")
    if len(parts) != 4:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return
    section_type = parts[1]
    subject_id = parts[2]
    stage_id = parts[3]
    if section_type not in {"theory", "practical"}:
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True,
        )
        return
    await query.answer()
    await show_file_list(
        query,
        stage_id,
        subject_id,
        section_type,
    )
async def admin_file_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return
    parts = query.data.split(":")
    if len(parts) != 4:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return
    stage_id = parts[1]
    subject_id = parts[2]
    section_type = parts[3]
    if section_type not in {"theory", "practical"}:
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True,
        )
        return
    await query.answer()
    await show_file_list(
        query,
        stage_id,
        subject_id,
        section_type,
    )
async def show_file_list(
    query,
    stage_id,
    subject_id,
    section_type,
):
    files = await get_files(
        subject_id,
        section_type,
        include_inactive=True,
    )
    await query.edit_message_text(
        f"📄 إدارة الملفات\n"
        f"{section_name(section_type)}\n\n"
        "اختر الملف لإدارته أو أضف ملفاً جديداً:",
        reply_markup=file_list_keyboard(
            files,
            stage_id,
            subject_id,
            section_type,
        ),
    )
# =========================
# Manage File
# =========================
async def manage_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return
    parts = query.data.split(":")
    if len(parts) != 4:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return
    file_id = parts[1]
    subject_id = parts[2]
    section_type = parts[3]
    await query.answer()
    file = await get_file(
        file_id,
        subject_id,
    )
    if not file:
        await query.edit_message_text(
            "❌ الملف غير موجود."
        )
        return
    stage_response = (
        supabase
        .table("subjects")
        .select("stage_id")
        .eq("id", subject_id)
        .limit(1)
        .execute()
    )
    subjects = stage_response.data or []
    if not subjects:
        await query.edit_message_text(
            "❌ تعذر تحديد المرحلة."
        )
        return
    stage_id = subjects[0]["stage_id"]
    file_type = FILE_TYPES.get(
        file.get("file_type"),
        "📎 ملف",
    )
    description = (
        file.get("description")
        or "لا يوجد وصف."
    )
    status = (
        "🟢 مفعّل"
        if file["is_active"]
        else "🔴 معطّل"
    )
    await query.edit_message_text(
        f"📄 {file['name']}\n\n"
        f"القسم: {section_name(section_type)}\n"
        f"النوع: {file_type}\n"
        f"الوصف:\n{description}\n\n"
        f"الترتيب: {file['sort_order']}\n"
        f"الحالة: {status}",
        reply_markup=file_manage_keyboard(
            file_id,
            stage_id,
            subject_id,
            section_type,
            file["is_active"],
        ),
    )
# =========================
# Add File
# =========================
async def start_add_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if query is None or query.from_user is None:
        return ConversationHandler.END
    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END
    parts = query.data.split(":")
    if len(parts) != 4:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END
    stage_id = parts[1]
    subject_id = parts[2]
    section_type = parts[3]
    if section_type not in {"theory", "practical"}:
        await query.answer(
            "❌ نوع القسم غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END
    clear_file_conversation(context)
    context.user_data["admin_file_stage_id"] = stage_id
    context.user_data["admin_file_subject_id"] = subject_id
    context.user_data["admin_file_section_type"] = section_type
    await query.answer()
    await query.edit_message_text(
        "➕ إضافة ملف جديد\n\n"
        f"القسم: {section_name(section_type)}\n\n"
        "أرسل اسم الملف الذي سيظهر للطلاب:\n\n"
        "للإلغاء استخدم /cancel"
    )
    return ADD_FILE_NAME
async def receive_add_file_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END
    if not await is_admin(update.effective_user.id):
        clear_file_conversation(context)
        return ConversationHandler.END
    name = normalize_text(update.message.text)
    if not name:
        await update.message.reply_text(
            "❌ اسم الملف لا يمكن أن يكون فارغاً.\n\n"
            "أرسل اسم الملف مرة أخرى:"
        )
        return ADD_FILE_NAME
    subject_id = context.user_data.get(
        "admin_file_subject_id"
    )
    section_type = context.user_data.get(
        "admin_file_section_type"
    )
    if not subject_id or not section_type:
        await update.message.reply_text(
            "❌ انتهت عملية الإضافة.\n"
            "ابدأ من لوحة إدارة الملفات مرة أخرى."
        )
        clear_file_conversation(context)
        return ConversationHandler.END
    response = (
        supabase
        .table("files")
        .select("id")
        .eq("subject_id", subject_id)
        .eq("section_type", section_type)
        .eq("name", name)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )
    if response.data:
        await update.message.reply_text(
            "⚠️ يوجد ملف بهذا الاسم في نفس القسم.\n\n"
            "أرسل اسماً مختلفاً:"
        )
        return ADD_FILE_NAME
    context.user_data["admin_file_name"] = name
    await update.message.reply_text(
        "📝 أرسل وصف الملف.\n\n"
        "إذا ما تريد وصف، أرسل: -"
    )
    return ADD_FILE_DESCRIPTION
async def receive_add_file_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END
    if not await is_admin(update.effective_user.id):
        clear_file_conversation(context)
        return ConversationHandler.END
    description = normalize_description(
        update.message.text
    )
    context.user_data["admin_file_description"] = (
        description
    )
    await update.message.reply_text(
        "🔢 أرسل ترتيب الملف.\n\n"
        "مثال: 1"
    )
    return ADD_FILE_ORDER
async def receive_add_file_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END
    if not await is_admin(update.effective_user.id):
        clear_file_conversation(context)
        return ConversationHandler.END
    text = update.message.text.strip()
    try:
        sort_order = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ الترتيب يجب أن يكون رقماً صحيحاً.\n\n"
            "أرسل الترتيب مرة أخرى:"
        )
        return ADD_FILE_ORDER
    if sort_order < 1:
        await update.message.reply_text(
            "❌ الترتيب يجب أن يكون 1 أو أكبر.\n\n"
            "أرسل الترتيب مرة أخرى:"
        )
        return ADD_FILE_ORDER
    context.user_data["admin_file_order"] = sort_order
    await update.message.reply_text(
        "📤 الآن أرسل الملف نفسه.\n\n"
        "يمكنك إرسال:\n"
        "📄 PDF / Word / Document\n"
        "🖼️ صورة\n"
        "🎥 فيديو\n"
        "🎵 ملف صوتي\n\n"
        "للإلغاء استخدم /cancel"
    )
    return ADD_FILE_UPLOAD
async def receive_add_file_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END
    if not await is_admin(update.effective_user.id):
        clear_file_conversation(context)
        return ConversationHandler.END
    message = update.message
    telegram_file_id = None
    file_type = None
    file_size = None
    if message.document is not None:
        telegram_file_id = message.document.file_id
        file_type = "document"
        file_size = message.document.file_size
    elif message.photo:
        telegram_file_id = message.photo[-1].file_id
        file_type = "photo"
        file_size = message.photo[-1].file_size
    elif message.video is not None:
        telegram_file_id = message.video.file_id
        file_type = "video"
        file_size = message.video.file_size
    elif message.audio is not None:
        telegram_file_id = message.audio.file_id
        file_type = "audio"
        file_size = message.audio.file_size
    else:
        await message.reply_text(
            "❌ نوع الملف غير مدعوم.\n\n"
            "أرسل PDF أو Word أو صورة أو فيديو أو ملف صوتي."
        )
        return ADD_FILE_UPLOAD
    stage_id = context.user_data.get(
        "admin_file_stage_id"
    )
    subject_id = context.user_data.get(
        "admin_file_subject_id"
    )
    section_type = context.user_data.get(
        "admin_file_section_type"
    )
    name = context.user_data.get(
        "admin_file_name"
    )
    description = context.user_data.get(
        "admin_file_description"
    )
    sort_order = context.user_data.get(
        "admin_file_order"
    )
    if not all([
        stage_id,
        subject_id,
        section_type,
        name,
        sort_order,
    ]):
        await message.reply_text(
            "❌ انتهت عملية الإضافة.\n"
            "ابدأ من لوحة إدارة الملفات مرة أخرى."
        )
        clear_file_conversation(context)
        return ConversationHandler.END
    try:
        supabase.table("files").insert({
            "subject_id": subject_id,
            "section_type": section_type,
            "name": name,
            "description": description,
            "telegram_file_id": telegram_file_id,
            "file_type": file_type,
            "file_size": file_size,
            "sort_order": sort_order,
            "is_active": True,
        }).execute()
    except Exception:
        await message.reply_text(
            "❌ حدث خطأ أثناء حفظ الملف.\n"
            "لم يتم إنشاء سجل الملف."
        )
        clear_file_conversation(context)
        return ConversationHandler.END
    await message.reply_text(
        "✅ تمت إضافة الملف بنجاح.\n\n"
        f"📄 {name}\n"
        f"{section_name(section_type)}\n"
        f"🔢 الترتيب: {sort_order}",
        reply_markup=after_save_keyboard(
            stage_id,
            subject_id,
            section_type,
        ),
    )
    clear_file_conversation(context)
    return ConversationHandler.END
# =========================
# Edit File
# =========================
async def start_edit_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if query is None or query.from_user is None:
        return ConversationHandler.END
    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return ConversationHandler.END
    parts = query.data.split(":")
    if len(parts) != 5:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END
    file_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]
    section_type = parts[4]
    file = await get_file(
        file_id,
        subject_id,
    )
    if not file:
        await query.answer(
            "❌ الملف غير موجود.",
            show_alert=True,
        )
        return ConversationHandler.END
    clear_file_conversation(context)
    context.user_data["admin_file_stage_id"] = stage_id
    context.user_data["admin_file_subject_id"] = subject_id
    context.user_data["admin_file_section_type"] = section_type
    context.user_data["admin_file_id"] = file_id
    await query.answer()
    await query.edit_message_text(
        "✏️ تعديل الملف\n\n"
        f"الاسم الحالي:\n{file['name']}\n\n"
        "أرسل الاسم الجديد:\n\n"
        "للإلغاء استخدم /cancel"
    )
    return EDIT_FILE_NAME
async def receive_edit_file_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END
    if not await is_admin(update.effective_user.id):
        clear_file_conversation(context)
        return ConversationHandler.END
    name = normalize_text(update.message.text)
    if not name:
        await update.message.reply_text(
            "❌ اسم الملف لا يمكن أن يكون فارغاً.\n\n"
            "أرسل الاسم الجديد:"
        )
        return EDIT_FILE_NAME
    file_id = context.user_data.get(
        "admin_file_id"
    )
    subject_id = context.user_data.get(
        "admin_file_subject_id"
    )
    section_type = context.user_data.get(
        "admin_file_section_type"
    )
    response = (
        supabase
        .table("files")
        .select("id")
        .eq("subject_id", subject_id)
        .eq("section_type", section_type)
        .eq("name", name)
        .neq("id", file_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )
    if response.data:
        await update.message.reply_text(
            "⚠️ يوجد ملف آخر بهذا الاسم في نفس القسم.\n\n"
            "أرسل اسماً مختلفاً:"
        )
        return EDIT_FILE_NAME
    context.user_data["admin_file_name"] = name
    await update.message.reply_text(
        "📝 أرسل الوصف الجديد.\n\n"
        "إذا ما تريد وصف، أرسل: -"
    )
    return EDIT_FILE_DESCRIPTION
async def receive_edit_file_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END
    if not await is_admin(update.effective_user.id):
        clear_file_conversation(context)
        return ConversationHandler.END
    description = normalize_description(
        update.message.text
    )
    context.user_data["admin_file_description"] = (
        description
    )
    await update.message.reply_text(
        "🔢 أرسل الترتيب الجديد.\n\n"
        "مثال: 1"
    )
    return EDIT_FILE_ORDER
async def receive_edit_file_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END
    if not await is_admin(update.effective_user.id):
        clear_file_conversation(context)
        return ConversationHandler.END
    text = update.message.text.strip()
    try:
        sort_order = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ الترتيب يجب أن يكون رقماً صحيحاً.\n\n"
            "أرسل الترتيب مرة أخرى:"
        )
        return EDIT_FILE_ORDER
    if sort_order < 1:
        await update.message.reply_text(
            "❌ الترتيب يجب أن يكون 1 أو أكبر.\n\n"
            "أرسل الترتيب مرة أخرى:"
        )
        return EDIT_FILE_ORDER
    file_id = context.user_data.get(
        "admin_file_id"
    )
    subject_id = context.user_data.get(
        "admin_file_subject_id"
    )
    stage_id = context.user_data.get(
        "admin_file_stage_id"
    )
    section_type = context.user_data.get(
        "admin_file_section_type"
    )
    name = context.user_data.get(
        "admin_file_name"
    )
    description = context.user_data.get(
        "admin_file_description"
    )
    if not all([
        file_id,
        subject_id,
        stage_id,
        section_type,
        name,
    ]):
        await update.message.reply_text(
            "❌ انتهت عملية التعديل.\n"
            "ابدأ من لوحة إدارة الملفات مرة أخرى."
        )
        clear_file_conversation(context)
        return ConversationHandler.END
    try:
        supabase.table("files").update({
            "name": name,
            "description": description,
            "sort_order": sort_order,
        }).eq(
            "id",
            file_id,
        ).eq(
            "subject_id",
            subject_id,
        ).execute()
    except Exception:
        await update.message.reply_text(
            "❌ حدث خطأ أثناء تعديل الملف.\n"
            "لم يتم حفظ التعديلات."
        )
        clear_file_conversation(context)
        return ConversationHandler.END
    await update.message.reply_text(
        "✅ تم تعديل الملف بنجاح.\n\n"
        f"📄 {name}\n"
        f"🔢 الترتيب: {sort_order}",
        reply_markup=after_save_keyboard(
            stage_id,
            subject_id,
            section_type,
        ),
    )
    clear_file_conversation(context)
    return ConversationHandler.END
# =========================
# Enable / Disable
# =========================
async def disable_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await set_file_status(
        update,
        active=False,
    )
async def enable_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await set_file_status(
        update,
        active=True,
    )
async def set_file_status(
    update: Update,
    active: bool,
):
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return
    parts = query.data.split(":")
    if len(parts) != 5:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return
    file_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]
    section_type = parts[4]
    file = await get_file(
        file_id,
        subject_id,
    )
    if not file:
        await query.answer(
            "❌ الملف غير موجود.",
            show_alert=True,
        )
        return
    try:
        supabase.table("files").update({
            "is_active": active,
        }).eq(
            "id",
            file_id,
        ).eq(
            "subject_id",
            subject_id,
        ).execute()
    except Exception:
        await query.answer(
            "❌ حدث خطأ أثناء تحديث حالة الملف.",
            show_alert=True,
        )
        return
    await query.answer(
        "✅ تم تفعيل الملف."
        if active
        else "✅ تم تعطيل الملف.",
        show_alert=True,
    )
    await show_file_after_status(
        query,
        file_id,
        stage_id,
        subject_id,
        section_type,
    )
async def show_file_after_status(
    query,
    file_id,
    stage_id,
    subject_id,
    section_type,
):
    file = await get_file(
        file_id,
        subject_id,
    )
    if not file:
        await query.edit_message_text(
            "❌ الملف غير موجود."
        )
        return
    file_type = FILE_TYPES.get(
        file.get("file_type"),
        "📎 ملف",
    )
    description = (
        file.get("description")
        or "لا يوجد وصف."
    )
    status = (
        "🟢 مفعّل"
        if file["is_active"]
        else "🔴 معطّل"
    )
    await query.edit_message_text(
        f"📄 {file['name']}\n\n"
        f"القسم: {section_name(section_type)}\n"
        f"النوع: {file_type}\n"
        f"الوصف:\n{description}\n\n"
        f"الترتيب: {file['sort_order']}\n"
        f"الحالة: {status}",
        reply_markup=file_manage_keyboard(
            file_id,
            stage_id,
            subject_id,
            section_type,
            file["is_active"],
        ),
    )
# =========================
# Delete File
# =========================
async def delete_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return
    parts = query.data.split(":")
    if len(parts) != 5:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return
    file_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]
    section_type = parts[4]
    file = await get_file(
        file_id,
        subject_id,
    )
    if not file:
        await query.answer(
            "❌ الملف غير موجود.",
            show_alert=True,
        )
        return
    await query.answer()
    await query.edit_message_text(
        "⚠️ تأكيد حذف الملف\n\n"
        f"📄 {file['name']}\n\n"
        "سيتم إخفاء الملف عن الطلاب ولن يظهر ضمن القائمة.\n\n"
        "هل أنت متأكد من الحذف؟",
        reply_markup=delete_confirm_keyboard(
            file_id,
            stage_id,
            subject_id,
            section_type,
        ),
    )
async def confirm_delete_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return
    parts = query.data.split(":")
    if len(parts) != 5:
        await query.answer(
            "❌ اختيار غير صالح.",
            show_alert=True,
        )
        return
    file_id = parts[1]
    stage_id = parts[2]
    subject_id = parts[3]
    section_type = parts[4]
    file = await get_file(
        file_id,
        subject_id,
    )
    if not file:
        await query.answer(
            "❌ الملف غير موجود.",
            show_alert=True,
        )
        return
    try:
        supabase.table("files").update({
            "is_active": False,
            "deleted_at": "now()",
        }).eq(
            "id",
            file_id,
        ).eq(
            "subject_id",
            subject_id,
        ).execute()
    except Exception:
        await query.answer(
            "❌ حدث خطأ أثناء حذف الملف.",
            show_alert=True,
        )
        return
    await query.answer(
        "✅ تم حذف الملف.",
        show_alert=True,
    )
    await show_file_list(
        query,
        stage_id,
        subject_id,
        section_type,
    )
# =========================
# Cancel
# =========================
async def cancel_file_operation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    clear_file_conversation(context)
    if update.message is not None:
        await update.message.reply_text(
            "↩️ تم إلغاء العملية."
        )
    return ConversationHandler.END
# =========================
# Conversation Handler
# =========================
def file_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                start_add_file,
                pattern=r"^add_file:",
            ),
            CallbackQueryHandler(
                start_edit_file,
                pattern=r"^edit_file:",
            ),
        ],
        states={
            ADD_FILE_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_add_file_name,
                )
            ],
            ADD_FILE_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_add_file_description,
                )
            ],
            ADD_FILE_ORDER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_add_file_order,
                )
            ],
            ADD_FILE_UPLOAD: [
                MessageHandler(
                    (
                        filters.Document.ALL
                        | filters.PHOTO
                        | filters.VIDEO
                        | filters.AUDIO
                    ),
                    receive_add_file_upload,
                )
            ],
            EDIT_FILE_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_edit_file_name,
                )
            ],
            EDIT_FILE_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_edit_file_description,
                )
            ],
            EDIT_FILE_ORDER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_edit_file_order,
                )
            ],
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_file_operation,
            )
        ],
        allow_reentry=False,
    )
# =========================
# Navigation Helper
# =========================
async def back_to_admin_files(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return
    await query.answer()
    await admin_files(
        update,
        context,
    )
