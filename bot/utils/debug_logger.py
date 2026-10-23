"""Opt-in update metadata and privacy-preserving application error reports."""
from bot.utils.logging_security import configure_logging, log_error, logger

configure_logging()

from bot.utils.logging_security import DEBUG_ENABLED
from telegram import Update
from telegram.ext import ContextTypes


async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DEBUG_ENABLED:
        return
    try:
        event_type = "OTHER"
        for field in ("callback_query", "message", "inline_query", "chat_member",
                      "my_chat_member", "channel_post", "edited_message", "edited_channel_post"):
            if getattr(update, field, None) is not None:
                event_type = field.upper()
                break
        # Do not inspect text, captions, callback data, names, user or chat IDs.
        logger.info("update_id=%s | update_type=%s", update.update_id, event_type)
    except Exception as exc:
        log_error("DEBUG LOGGER FAILED", exc)


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    # Operational errors remain visible when verbose update logging is disabled.
    log_error("UNHANDLED BOT ERROR", context.error)
