from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters,
)

from bot.database.client import supabase
from bot.handlers.admin import is_admin
from bot.utils.config import STUDENT_GROUP_ID


BROADCAST_DESCRIPTION = 1
ROLE_USER_ID = 10


ROLE_NAMES = {
    "owner": "👑 Owner",
    "admin": "🛡️ Admin",
    "moderator": "🔧 Moderator",
}


async def get_admin(user_id):
    response = (
        supabase
        .table("admins")
        .select(
            "id, telegram_id, role, is_active"
        )
        .eq("telegram_id", user_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    rows = response.data or []

    return rows[0] if rows else None


async def is_owner(user_id):
    admin = await get_admin(user_id)

    return (
        admin is not None
        and admin.get("role") == "owner"
    )


def tools_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📤 إرسال جميع الملفات",
                callback_data="bulk_files",
            )
        ],
        [
            InlineKeyboardButton(
                "📤 إرسال جميع الملخصات",
                callback_data="bulk_summaries",
            )
        ],
        [
            InlineKeyboardButton(
                "📤 إرسال جميع الرسومات",
                callback_data="bulk_drawings",
            )
        ],
        [
            InlineKeyboardButton(
                "📊 حالة البوت",
                callback_data="bot_status",
            )
        ],
        [
            InlineKeyboardButton(
                "👥 إدارة المشرفين",
                callback_data="admin_roles",
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ لوحة الإدارة",
                callback_data="admin_back",
            )
        ],
    ])


async def admin_tools(
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

    await query.edit_message_text(
        "🧰 أدوات الإدارة\n\n"
        "اختر العملية:",
        reply_markup=tools_keyboard(),
    )


async def start_bulk_send(
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

    if len(parts) != 1:
        content_type = parts[0]
    else:
        content_type = query.data

    if content_type == "bulk_files":
        table = "files"
        title = "الملفات"
    elif content_type == "bulk_summaries":
        table = "summaries"
        title = "الملخصات"
    elif content_type == "bulk_drawings":
        table = "drawings"
        title = "الرسومات"
    else:
        await query.answer(
            "❌ نوع الإرسال غير صالح.",
            show_alert=True,
        )
        return ConversationHandler.END

    context.user_data["bulk_table"] = table
    context.user_data["bulk_title"] = title

    await query.answer()

    await query.edit_message_text(
        f"📤 إرسال جميع {title}\n\n"
        "أرسل الآن الوصف أو النص الذي تريد "
        "إظهاره مع الإرسال.\n\n"
        "إذا ما تريد وصف، اكتب:\n"
        "بدون وصف"
    )

    return BROADCAST_DESCRIPTION


async def receive_bulk_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return BROADCAST_DESCRIPTION

    description = (
        update.message.text or ""
    ).strip()

    if description == "بدون وصف":
        description = ""

    table = context.user_data.get(
        "bulk_table"
    )

    title = context.user_data.get(
        "bulk_title",
        "المحتويات",
    )

    if not table:
        await update.message.reply_text(
            "❌ انتهت بيانات العملية."
        )
        return ConversationHandler.END

    if not STUDENT_GROUP_ID:
        await update.message.reply_text(
            "❌ STUDENT_GROUP_ID غير موجود "
            "في Environment Variables."
        )
        return ConversationHandler.END

    try:
        chat_id = int(STUDENT_GROUP_ID)
    except ValueError:
        await update.message.reply_text(
            "❌ قيمة STUDENT_GROUP_ID غير صحيحة."
        )
        return ConversationHandler.END

    try:
        response = (
            supabase
            .table(table)
            .select("*")
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .order("sort_order")
            .execute()
        )

        items = response.data or []

        if not items:
            await update.message.reply_text(
                f"⚠️ لا توجد {title} مضافة حالياً."
            )
            return ConversationHandler.END

        await update.message.reply_text(
            f"⏳ جارٍ إرسال جميع {title}...\n"
            f"العدد: {len(items)}"
        )

        sent = 0
        failed = 0

        if description:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=description,
                )
            except Exception as exc:
                print(
                    "BROADCAST DESCRIPTION ERROR:",
                    exc,
                )

        for item in items:
            file_id = item.get(
                "telegram_file_id"
            )

            if not file_id:
                failed += 1
                continue

            caption = (
                item.get("name")
                or title
            )

            item_description = (
                item.get("description")
                or ""
            ).strip()

            if item_description:
                caption += (
                    f"\n\n📝 {item_description}"
                )

            if len(caption) > 1024:
                caption = (
                    caption[:1021] + "..."
                )

            file_type = item.get(
                "file_type"
            )

            try:
                if file_type == "photo":
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=file_id,
                        caption=caption,
                    )

                elif file_type == "video":
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=file_id,
                        caption=caption,
                    )

                elif file_type == "audio":
                    await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=file_id,
                        caption=caption,
                    )

                else:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=file_id,
                        caption=caption,
                    )

                sent += 1

            except Exception as exc:
                failed += 1

                print(
                    "BROADCAST ITEM ERROR:",
                    type(exc).__name__,
                    exc,
                )

        await update.message.reply_text(
            "✅ اكتمل الإرسال.\n\n"
            f"📦 القسم: {title}\n"
            f"✅ تم الإرسال: {sent}\n"
            f"❌ فشل: {failed}"
        )

    except Exception as exc:
        print(
            "BROADCAST ERROR:",
            type(exc).__name__,
            exc,
        )

        await update.message.reply_text(
            "❌ حدث خطأ أثناء الإرسال.\n"
            "راجع Railway Logs."
        )

    context.user_data.pop(
        "bulk_table",
        None,
    )
    context.user_data.pop(
        "bulk_title",
        None,
    )

    return ConversationHandler.END


async def cancel_bulk(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.pop(
        "bulk_table",
        None,
    )
    context.user_data.pop(
        "bulk_title",
        None,
    )

    if update.message:
        await update.message.reply_text(
            "❌ تم إلغاء الإرسال."
        )

    return ConversationHandler.END


def bulk_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                start_bulk_send,
                pattern=(
                    r"^bulk_"
                    r"(files|summaries|drawings)$"
                ),
            )
        ],
        states={
            BROADCAST_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_bulk_description,
                )
            ]
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_bulk,
            )
        ],
        allow_reentry=True,
    )


async def bot_status(
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

    def count_rows(table, active_only=False):
        builder = (
            supabase
            .table(table)
            .select("id", count="exact")
        )

        if active_only:
            builder = builder.eq(
                "is_active",
                True,
            )

        try:
            result = builder.execute()
            return result.count or 0
        except Exception:
            return 0

    users = count_rows("users")
    admins = count_rows(
        "admins",
        active_only=True,
    )
    files = count_rows(
        "files",
        active_only=True,
    )
    summaries = count_rows(
        "summaries",
        active_only=True,
    )
    drawings = count_rows(
        "drawings",
        active_only=True,
    )
    schedules = count_rows(
        "schedules",
        active_only=True,
    )
    chats = count_rows(
        "bot_chats",
        active_only=True,
    )

    owner_count = 0
    admin_count = 0
    moderator_count = 0

    try:
        response = (
            supabase
            .table("admins")
            .select("role")
            .eq("is_active", True)
            .execute()
        )

        for row in response.data or []:
            role = row.get("role")

            if role == "owner":
                owner_count += 1
            elif role == "admin":
                admin_count += 1
            elif role == "moderator":
                moderator_count += 1

    except Exception:
        pass

    text = (
        "📊 حالة البوت\n\n"
        "🟢 الحالة: يعمل\n\n"
        "👥 الإحصائيات\n"
        f"• المستخدمون: {users}\n"
        f"• الكروبات/المحادثات المسجلة: {chats}\n\n"
        "🛡️ الإدارة\n"
        f"• 👑 Owners: {owner_count}\n"
        f"• 🛡️ Admins: {admin_count}\n"
        f"• 🔧 Moderators: {moderator_count}\n"
        f"• مجموع المشرفين: {admins}\n\n"
        "📚 المحتوى\n"
        f"• 📄 الملفات: {files}\n"
        f"• 📝 الملخصات: {summaries}\n"
        f"• 🎨 الرسومات: {drawings}\n"
        f"• 📅 الجداول: {schedules}"
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔄 تحديث",
                    callback_data="bot_status",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ أدوات الإدارة",
                    callback_data="admin_tools",
                )
            ],
        ]),
    )


async def admin_roles(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_owner(query.from_user.id):
        await query.answer(
            "⛔ هذا الخيار للـ Owner فقط.",
            show_alert=True,
        )
        return

    await query.answer()

    response = (
        supabase
        .table("admins")
        .select(
            "id, telegram_id, role, is_active"
        )
        .eq("is_active", True)
        .order("id")
        .execute()
    )

    admins = response.data or []

    keyboard = [
        [
            InlineKeyboardButton(
                "➕ إعطاء رتبة",
                callback_data="role_add",
            )
        ]
    ]

    for admin in admins:
        role = admin.get("role", "moderator")

        keyboard.append([
            InlineKeyboardButton(
                text=(
                    f"{ROLE_NAMES.get(role, role)} "
                    f"• {admin['telegram_id']}"
                ),
                callback_data=(
                    f"role_manage:{admin['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ أدوات الإدارة",
            callback_data="admin_tools",
        )
    ])

    await query.edit_message_text(
        "👥 إدارة المشرفين\n\n"
        "اختر المشرف:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def role_add_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    if not await is_owner(query.from_user.id):
        await query.answer(
            "⛔ هذا الخيار للـ Owner فقط.",
            show_alert=True,
        )
        return ConversationHandler.END

    await query.answer()

    await query.edit_message_text(
        "➕ إضافة مشرف\n\n"
        "أرسل Telegram ID للشخص الذي تريد إعطائه رتبة:"
    )

    return ROLE_USER_ID


async def role_receive_user_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ConversationHandler.END

    try:
        telegram_id = int(
            update.message.text.strip()
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Telegram ID غير صحيح.\n"
            "أرسله كرقم فقط:"
        )
        return ROLE_USER_ID

    context.user_data[
        "role_target_id"
    ] = telegram_id

    await update.message.reply_text(
        "اختر الرتبة:",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🛡️ Admin",
                    callback_data="set_role:admin",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔧 Moderator",
                    callback_data="set_role:moderator",
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data="cancel_role",
                )
            ],
        ]),
    )

    return ConversationHandler.END


async def set_role(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_owner(query.from_user.id):
        await query.answer(
            "⛔ هذا الخيار للـ Owner فقط.",
            show_alert=True,
        )
        return

    target_id = context.user_data.get(
        "role_target_id"
    )

    if not target_id:
        await query.answer(
            "❌ لم يتم تحديد المستخدم.",
            show_alert=True,
        )
        return

    role = query.data.split(":")[1]

    try:
        existing = (
            supabase
            .table("admins")
            .select("id")
            .eq(
                "telegram_id",
                target_id,
            )
            .limit(1)
            .execute()
        )

        rows = existing.data or []

        if rows:
            supabase.table("admins").update({
                "role": role,
                "is_active": True,
            }).eq(
                "id",
                rows[0]["id"],
            ).execute()

        else:
            supabase.table("admins").insert({
                "telegram_id": target_id,
                "role": role,
                "is_active": True,
            }).execute()

    except Exception as exc:
        print(
            "ROLE SAVE ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ تعذر حفظ الرتبة.",
            show_alert=True,
        )
        return

    context.user_data.pop(
        "role_target_id",
        None,
    )

    await query.answer(
        "✅ تم حفظ الرتبة.",
        show_alert=True,
    )

    await admin_roles(
        update,
        context,
    )


async def role_manage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_owner(query.from_user.id):
        await query.answer(
            "⛔ هذا الخيار للـ Owner فقط.",
            show_alert=True,
        )
        return

    admin_id = query.data.split(":")[1]

    response = (
        supabase
        .table("admins")
        .select(
            "id, telegram_id, role"
        )
        .eq("id", admin_id)
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        await query.answer(
            "❌ المشرف غير موجود.",
            show_alert=True,
        )
        return

    admin = rows[0]

    await query.answer()

    await query.edit_message_text(
        "👤 إدارة المشرف\n\n"
        f"🆔 ID: {admin['telegram_id']}\n"
        f"🏷️ الرتبة: "
        f"{ROLE_NAMES.get(admin['role'], admin['role'])}\n\n"
        "اختر العملية:",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🛡️ تحويل إلى Admin",
                    callback_data=(
                        f"change_role:"
                        f"{admin['id']}:admin"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "🔧 تحويل إلى Moderator",
                    callback_data=(
                        f"change_role:"
                        f"{admin['id']}:moderator"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ إزالة الرتبة",
                    callback_data=(
                        f"remove_role:"
                        f"{admin['id']}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="admin_roles",
                )
            ],
        ]),
    )


async def change_role(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_owner(query.from_user.id):
        await query.answer(
            "⛔ هذا الخيار للـ Owner فقط.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    admin_id = parts[1]
    role = parts[2]

    try:
        supabase.table("admins").update({
            "role": role,
            "is_active": True,
        }).eq(
            "id",
            admin_id,
        ).execute()

    except Exception as exc:
        print(
            "ROLE CHANGE ERROR:",
            exc,
        )

        await query.answer(
            "❌ تعذر تغيير الرتبة.",
            show_alert=True,
        )
        return

    await query.answer(
        "✅ تم تغيير الرتبة.",
        show_alert=True,
    )

    await admin_roles(
        update,
        context,
    )


async def remove_role(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_owner(query.from_user.id):
        await query.answer(
            "⛔ هذا الخيار للـ Owner فقط.",
            show_alert=True,
        )
        return

    admin_id = query.data.split(":")[1]

    try:
        supabase.table("admins").update({
            "is_active": False,
        }).eq(
            "id",
            admin_id,
        ).execute()

    except Exception as exc:
        print(
            "ROLE REMOVE ERROR:",
            exc,
        )

        await query.answer(
            "❌ تعذر إزالة الرتبة.",
            show_alert=True,
        )
        return

    await query.answer(
        "✅ تمت إزالة الرتبة.",
        show_alert=True,
    )

    await admin_roles(
        update,
        context,
    )


async def cancel_role(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.pop(
        "role_target_id",
        None,
    )

    if update.message:
        await update.message.reply_text(
            "❌ تم إلغاء العملية."
        )

    return ConversationHandler.END


def role_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                role_add_start,
                pattern=r"^role_add$",
            )
        ],
        states={
            ROLE_USER_ID: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    role_receive_user_id,
                )
            ]
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_role,
            )
        ],
        allow_reentry=True,
    )
