from telegram import Update
from telegram.ext import ContextTypes

from bot.database.client import supabase
from bot.keyboards.stages import stages_keyboard


async def show_stages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return

    response = (
        supabase
        .table("stages")
        .select("*")
        .order("stage_number")
        .execute()
    )

    stages = response.data

    await update.message.reply_text(
        "🎓 أهلاً بك في بوت الطالب الجامعي\n\n"
        "اختر المرحلة الدراسية:",
        reply_markup=stages_keyboard(stages)
    )
