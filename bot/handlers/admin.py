from telegram import &#40;
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
&#41;
from telegram\.ext import ContextTypes
from bot\.database\.client import supabase
from bot\.utils\.permissions import &#40;
    PERMISSION\_MANAGE\_SUBJECTS,
    PERMISSION\_MANAGE\_FILES,
    PERMISSION\_MANAGE\_SUMMARIES,
    PERMISSION\_MANAGE\_DRAWINGS,
    PERMISSION\_MANAGE\_SCHEDULES,
    PERMISSION\_MANAGE\_GRADES,
    PERMISSION\_MANAGE\_EXAMS,
    PERMISSION\_MANAGE\_DESCRIPTIONS,
    PERMISSION\_VIEW\_STATISTICS,
    PERMISSION\_MANAGE\_ADMINS,
    PERMISSION\_MANAGE\_ANNOUNCEMENTS,
    PERMISSION\_MANAGE\_SETTINGS,
    DEFAULT\_ROLE\_PERMISSIONS,
    get\_admin,
    get\_role\_permissions,
    is\_admin,
    has\_permission,
&#41;
\# ============================================================
\# Admin permission snapshot
\# ============================================================
async def get\_admin\_permissions&#40;
    user\_id: int,
&#41;:
    admin = await get\_admin&#40;
        user\_id
    &#41;
    if not admin:
        return None, set&#40;&#41;
    role = admin\.get&#40;"role"&#41;
    if role == "owner":
        return admin, \{
            PERMISSION\_MANAGE\_SUBJECTS,
            PERMISSION\_MANAGE\_FILES,
            PERMISSION\_MANAGE\_SUMMARIES,
            PERMISSION\_MANAGE\_DRAWINGS,
            PERMISSION\_MANAGE\_SCHEDULES,
            PERMISSION\_MANAGE\_GRADES,
            PERMISSION\_MANAGE\_EXAMS,
            PERMISSION\_MANAGE\_DESCRIPTIONS,
            PERMISSION\_VIEW\_STATISTICS,
            PERMISSION\_MANAGE\_ADMINS,
            PERMISSION\_MANAGE\_ANNOUNCEMENTS,
            PERMISSION\_MANAGE\_SETTINGS,
        \}
    permissions = set&#40;
        DEFAULT\_ROLE\_PERMISSIONS\.get&#40;
            role,
            set&#40;&#41;,
        &#41;
    &#41;
    database\_permissions = &#40;
        await get\_role\_permissions&#40;
            role
        &#41;
    &#41;
    if database\_permissions:
        permissions\.update&#40;
            database\_permissions
        &#41;
    return admin, permissions
\# ============================================================
\# Admin check
\# ============================================================
async def is\_admin\_user&#40;
    user\_id: int,
&#41; \-\> bool:
    return await is\_admin&#40;
        user\_id
    &#41;
\# ============================================================
\# Admin keyboard
\# ============================================================
async def admin\_keyboard&#40;
    user\_id: int,
&#41;:
    admin, permissions = &#40;
        await get\_admin\_permissions&#40;
            user\_id
        &#41;
    &#41;
    if admin is None:
        return InlineKeyboardMarkup&#40;&#91;&#93;&#41;
    return await admin\_keyboard\_from\_permissions&#40;
        permissions
    &#41;
\# ============================================================
\# Admin command
\# ============================================================
async def admin\_command&#40;
    update: Update,
    context: ContextTypes\.DEFAULT\_TYPE,
&#41;:
    if &#40;
        update\.message is None
        or update\.effective\_user is None
    &#41;:
        return
    user\_id = update\.effective\_user\.id
    admin, permissions = &#40;
        await get\_admin\_permissions&#40;
            user\_id
        &#41;
    &#41;
    if admin is None:
        await update\.message\.reply\_text&#40;
            "⛔ عذراً، ليس لديك صلاحية "
            "الوصول إلى لوحة الإدارة\."
        &#41;
        return
    keyboard = &#40;
        await admin\_keyboard\_from\_permissions&#40;
            permissions
        &#41;
    &#41;
    await update\.message\.reply\_text&#40;
        "🛠️ لوحة الإدارة\\n\\n"
        "أهلاً بك في لوحة إدارة LabBase\.\\n"
        "اختر القسم الذي تريد إدارته:",
        reply\_markup=keyboard,
    &#41;
\# ============================================================
\# Build keyboard
\# ============================================================
async def admin\_keyboard\_from\_permissions&#40;
    permissions,
&#41;:
    keyboard = &#91;&#93;
    if PERMISSION\_MANAGE\_SUBJECTS in permissions:
        keyboard\.append&#40;&#91;
            InlineKeyboardButton&#40;
                text="📚 إدارة المواد",
                callback\_data="admin\_subjects",
            &#41;
        &#93;&#41;
    if PERMISSION\_MANAGE\_FILES in permissions:
        keyboard\.append&#40;&#91;
            InlineKeyboardButton&#40;
                text="📄 إدارة الملفات",
                callback\_data="admin\_files",
            &#41;
        &#93;&#41;
    if PERMISSION\_MANAGE\_SUMMARIES in permissions:
        keyboard\.append&#40;&#91;
            InlineKeyboardButton&#40;
                text="📝 إدارة الملخصات",
                callback\_data="admin\_summaries",
            &#41;
        &#93;&#41;
    if PERMISSION\_MANAGE\_DRAWINGS in permissions:
        keyboard\.append&#40;&#91;
            InlineKeyboardButton&#40;
                text="🎨 إدارة الرسومات",
                callback\_data="admin\_drawings",
            &#41;
        &#93;&#41;
    if PERMISSION\_MANAGE\_SCHEDULES in permissions:
        keyboard\.append&#40;&#91;
            InlineKeyboardButton&#40;
                text="📅 إدارة الجداول",
                callback\_data="admin\_schedules",
            &#41;
        &#93;&#41;
    if PERMISSION\_MANAGE\_GRADES in permissions:
        keyboard\.append&#40;&#91;
            InlineKeyboardButton&#40;
                text="📝 إدارة الدرجات",
                callback\_data="admin\_grades",
            &#41;
        &#93;&#41;
    if PERMISSION\_MANAGE\_EXAMS in permissions:
        keyboard\.append&#40;&#91;
            InlineKeyboardButton&#40;
                text="📋 مواعيد الامتحانات",
                callback\_data="admin\_exams",
            &#41;
        &#93;&#41;
    has\_tools = &#40;
        PERMISSION\_VIEW\_STATISTICS in permissions
        or PERMISSION\_MANAGE\_ADMINS in permissions
        or PERMISSION\_MANAGE\_DESCRIPTIONS in permissions
    &#41;
    if has\_tools:
        keyboard\.append&#40;&#91;
            InlineKeyboardButton&#40;
                text="🧰 أدوات الإدارة",
                callback\_data="admin\_tools",
            &#41;
        &#93;&#41;
    if PERMISSION\_MANAGE\_ANNOUNCEMENTS in permissions:
        keyboard\.append&#40;&#91;
            InlineKeyboardButton&#40;
                text="📢 التبليغات",
                callback\_data="admin\_announcements",
            &#41;
        &#93;&#41;
    if PERMISSION\_MANAGE\_SETTINGS in permissions:
        keyboard\.append&#40;&#91;
            InlineKeyboardButton&#40;
                text="⚙️ الإعدادات",
                callback\_data="admin\_settings",
            &#41;
        &#93;&#41;
    return InlineKeyboardMarkup&#40;
        keyboard
    &#41;
\# ============================================================
\# Admin back
\# ============================================================
async def admin\_back&#40;
    update: Update,
    context: ContextTypes\.DEFAULT\_TYPE,
&#41;:
    query = update\.callback\_query
    if &#40;
        query is None
        or query\.from\_user is None
    &#41;:
        return
    user\_id = query\.from\_user\.id
    admin, permissions = &#40;
        await get\_admin\_permissions&#40;
            user\_id
        &#41;
    &#41;
    if admin is None:
        await query\.answer&#40;
            "⛔ ليس لديك صلاحية\.",
            show\_alert=True,
        &#41;
        return
    await query\.answer&#40;&#41;
    keyboard = &#40;
        await admin\_keyboard\_from\_permissions&#40;
            permissions
        &#41;
    &#41;
    await query\.edit\_message\_text&#40;
        "🛠️ لوحة الإدارة\\n\\n"
        "أهلاً بك في لوحة إدارة LabBase\.\\n"
        "اختر القسم الذي تريد إدارته:",
        reply\_markup=keyboard,
    &#41;
\# ============================================================
\# Delete subject
\# ============================================================
async def delete\_subject&#40;
    update: Update,
    context: ContextTypes\.DEFAULT\_TYPE,
&#41;:
    query = update\.callback\_query
    if &#40;
        query is None
        or query\.from\_user is None
    &#41;:
        return
    user\_id = query\.from\_user\.id
    if not await has\_permission&#40;
        user\_id,
        PERMISSION\_MANAGE\_SUBJECTS,
    &#41;:
        await query\.answer&#40;
            "⛔ ليس لديك صلاحية\.",
            show\_alert=True,
        &#41;
        return
    parts = query\.data\.split&#40;":"&#41;
    if len&#40;parts&#41; \!= 3:
        await query\.answer&#40;
            "❌ اختيار غير صالح\.",
            show\_alert=True,
        &#41;
        return
    subject\_id = parts&#91;1&#93;
    stage\_id = parts&#91;2&#93;
    response = &#40;
        supabase
        \.table&#40;"subjects"&#41;
        \.select&#40;"id, name"&#41;
        \.eq&#40;"id", subject\_id&#41;
        \.eq&#40;"stage\_id", stage\_id&#41;
        \.limit&#40;1&#41;
        \.execute&#40;&#41;
    &#41;
    subjects = response\.data or &#91;&#93;
    if not subjects:
        await query\.answer&#40;
            "❌ المادة غير موجودة\.",
            show\_alert=True,
        &#41;
        return
    subject = subjects&#91;0&#93;
    await query\.answer&#40;&#41;
    await query\.edit\_message\_text&#40;
        "⚠️ تأكيد تعطيل المادة\\n\\n"
        f"📘 المادة: \{subject&#91;'name'&#93;\}\\n\\n"
        "هل أنت متأكد من تعطيل هذه المادة؟\\n\\n"
        "ℹ️ سيتم إخفاؤها عن الطلاب بدون حذف "
        "بياناتها نهائياً\.",
        reply\_markup=InlineKeyboardMarkup&#40;&#91;
            &#91;
                InlineKeyboardButton&#40;
                    text="🔒 نعم، عطّل المادة",
                    callback\_data=&#40;
                        "admin\_confirm\_delete\_subject:"
                        f"\{subject\_id\}:\{stage\_id\}"
                    &#41;,
                &#41;
            &#93;,
            &#91;
                InlineKeyboardButton&#40;
                    text="❌ إلغاء",
                    callback\_data=&#40;
                        f"manage\_subject:"
                        f"\{subject\_id\}:\{stage\_id\}"
                    &#41;,
                &#41;
            &#93;,
        &#93;&#41;,
    &#41;
\# ============================================================
\# Confirm subject disable
\# ============================================================
async def confirm\_delete\_subject&#40;
    update: Update,
    context: ContextTypes\.DEFAULT\_TYPE,
&#41;:
    query = update\.callback\_query
    if &#40;
        query is None
        or query\.from\_user is None
    &#41;:
        return
    user\_id = query\.from\_user\.id
    if not await has\_permission&#40;
        user\_id,
        PERMISSION\_MANAGE\_SUBJECTS,
    &#41;:
        await query\.answer&#40;
            "⛔ ليس لديك صلاحية\.",
            show\_alert=True,
        &#41;
        return
    parts = query\.data\.split&#40;":"&#41;
    if len&#40;parts&#41; \!= 3:
        await query\.answer&#40;
            "❌ اختيار غير صالح\.",
            show\_alert=True,
        &#41;
        return
    subject\_id = parts&#91;1&#93;
    stage\_id = parts&#91;2&#93;
    response = &#40;
        supabase
        \.table&#40;"subjects"&#41;
        \.select&#40;
            "id, name, is\_active"
        &#41;
        \.eq&#40;"id", subject\_id&#41;
        \.eq&#40;"stage\_id", stage\_id&#41;
        \.limit&#40;1&#41;
        \.execute&#40;&#41;
    &#41;
    subjects = response\.data or &#91;&#93;
    if not subjects:
        await query\.answer&#40;
            "❌ المادة غير موجودة\.",
            show\_alert=True,
        &#41;
        return
    subject = subjects&#91;0&#93;
    await query\.answer&#40;
        "⏳ جارٍ تعطيل المادة\.\.\."
    &#41;
    try:
        &#40;
            supabase
            \.table&#40;"subjects"&#41;
            \.update&#40;\{
                "is\_active": False,
            \}&#41;
            \.eq&#40;"id", subject\_id&#41;
            \.eq&#40;"stage\_id", stage\_id&#41;
            \.execute&#40;&#41;
        &#41;
    except Exception as exc:
        print&#40;
            "DISABLE SUBJECT ERROR:",
            type&#40;exc&#41;\.\_\_name\_\_,
            exc,
        &#41;
        await query\.edit\_message\_text&#40;
            "❌ تعذر تعطيل المادة\.\\n\\n"
            "لم يتم إجراء أي تغيير\."
        &#41;
        return
    await query\.edit\_message\_text&#40;
        "✅ تم تعطيل المادة بنجاح\.\\n\\n"
        f"📘 المادة: \{subject&#91;'name'&#93;\}\\n\\n"
        "🔒 تم إخفاؤها عن الطلاب\.\\n"
        "📦 البيانات المرتبطة بالمادة لم تُحذف\.",
        reply\_markup=InlineKeyboardMarkup&#40;&#91;
            &#91;
                InlineKeyboardButton&#40;
                    text="⬅️ العودة إلى المواد",
                    callback\_data=&#40;
                        f"admin\_stage\_subjects:\{stage\_id\}"
                    &#41;,
                &#41;
            &#93;,
            &#91;
                InlineKeyboardButton&#40;
                    text="🛠️ لوحة الإدارة",
                    callback\_data="admin\_back",
                &#41;
            &#93;,
        &#93;&#41;,
    &#41;
\# ============================================================
\# Generic admin buttons
\# ============================================================
async def admin\_button&#40;
    update: Update,
    context: ContextTypes\.DEFAULT\_TYPE,
&#41;:
    query = update\.callback\_query
    if &#40;
        query is None
        or query\.from\_user is None
    &#41;:
        return
    user\_id = query\.from\_user\.id
    admin = await get\_admin&#40;
        user\_id
    &#41;
    if admin is None:
        await query\.answer&#40;
            "⛔ ليس لديك صلاحية للوصول "
            "إلى لوحة الإدارة\.",
            show\_alert=True,
        &#41;
        return
    if query\.data\.startswith&#40;
        "admin\_delete\_subject:"
    &#41;:
        await delete\_subject&#40;
            update,
            context,
        &#41;
        return
    if query\.data\.startswith&#40;
        "admin\_confirm\_delete\_subject:"
    &#41;:
        await confirm\_delete\_subject&#40;
            update,
            context,
        &#41;
        return
    await query\.answer&#40;&#41;
    if query\.data == "admin\_announcements":
        from bot\.handlers\.admin\_notifications import &#40;
            admin\_notifications,
        &#41;
        await admin\_notifications&#40;
            update,
            context,
        &#41;
        return
    if query\.data == "admin\_settings":
        from bot\.handlers\.admin\_settings import &#40;
            admin\_settings,
        &#41;
        await admin\_settings&#40;
            update,
            context,
        &#41;
        return
