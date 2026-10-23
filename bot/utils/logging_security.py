"""Protect standard logging, not arbitrary writes to process output streams.

Call configure_logging before SDK imports and after hosting-handler changes.
The factory protects core fields of late handlers; handler filters also protect
extra fields (which logging attaches *after* calling the record factory).
"""
import copy
import logging
from logging.handlers import MemoryHandler, QueueHandler
import os
import re
import threading
import traceback
from urllib.parse import quote, quote_plus, urlsplit

DEBUG_ENABLED = os.getenv("LABBASE_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
REDACTED = "[REDACTED]"
logger = logging.getLogger("labbase")
_CONFIGURATION_LOCK = threading.RLock()
_TOKEN_PATTERN = re.compile(r"(?<!\d)\d{5,}(?::|%3a)[A-Za-z0-9_-]{20,}", re.IGNORECASE)
_KEY_PATTERN = re.compile(r"\bsb_(?:secret|publishable)_[A-Za-z0-9_-]{12,}")
_QUIET_LOGGERS = ("httpx", "httpcore", "telegram")
_PRIVATE_FIELDS = {
    "text", "message", "studentmessage", "usermessage", "messagetext", "caption",
    "callback", "callbackdata", "callbackpayload",
    "payload", "body", "request", "response", "update", "headers",
    "authorization", "password", "userdata", "chatdata",
    "error", "exception", "errormessage", "exceptionmessage", "exceptiontext",
    "traceback", "stacktrace",
}
# Loading dotenv must happen after the logging boundary is installed. During
# that bootstrap, redact only the three named environment settings in memory.
config = None


class _DiagnosticText(str):
    """Only internally generated, message-free exception diagnostics."""


def redact(value):
    """Match configured secrets in memory; never persist a credential registry."""
    # Calling str(value) can execute subclass/application code, even when
    # value looks like a primitive. Use the builtin implementation explicitly.
    if isinstance(value, str):
        text = str.__str__(value)
    elif value is None or type(value) is bool:
        text = str(value)
    elif isinstance(value, int):
        text = str(int.__int__(value))
    elif isinstance(value, float):
        text = str(float.__float__(value))
    else:
        text = f"<{type(value).__name__}>"
    values = []
    for name in ("BOT_TOKEN", "SUPABASE_URL", "SUPABASE_KEY"):
        values.extend((getattr(config, name, None), os.getenv(name)))
    for url in (getattr(config, "SUPABASE_URL", None), os.getenv("SUPABASE_URL")):
        if isinstance(url, str):
            try:
                values.append(urlsplit(url).hostname)
            except ValueError:
                pass
    variants = set()
    for secret in values:
        if not isinstance(secret, str) or not secret:
            continue
        variants.update((secret, secret.replace("/", r"\/"), quote(secret, safe=""), quote_plus(secret)))
        variants.add(quote(quote(secret, safe=""), safe=""))
    if variants:
        pattern = "|".join(re.escape(item) for item in sorted(variants, key=len, reverse=True))
        text = re.sub(pattern, lambda match: REDACTED, text, flags=re.IGNORECASE)
    text = _TOKEN_PATTERN.sub(REDACTED, text)
    return _KEY_PATTERN.sub(REDACTED, text)


def _private_field(key):
    return isinstance(key, str) and re.sub(r"[^a-z0-9]", "", key.lower()) in _PRIVATE_FIELDS


def _exception_diagnostics(error):
    """Never call str(exception), format_exception, or inspect source/locals."""
    lines = ["Traceback (locations only; exception messages withheld):"]
    pending, seen = [error], set()
    while pending and len(seen) < 16:
        current = pending.pop()
        if not isinstance(current, BaseException) or id(current) in seen:
            continue
        seen.add(id(current))
        lines.append(f"error_type={type(current).__name__}")
        for index, (frame, line) in enumerate(traceback.walk_tb(current.__traceback__)):
            if index >= 20:
                lines.append("Additional traceback locations withheld")
                break
            lines.append(f"{os.path.basename(frame.f_code.co_filename)}:{line} in {frame.f_code.co_name}")
        cause = current.__cause__
        if cause is None and not current.__suppress_context__:
            cause = current.__context__
        if cause is not None:
            pending.append(cause)
        # Compatible with Python versions predating ExceptionGroup.
        children = getattr(current, "exceptions", ())
        if isinstance(children, tuple):
            pending.extend(children[:16])
    return _DiagnosticText(redact("\n".join(lines)))


def _safe_key(value):
    return redact(value) if isinstance(value, (str, int, float, bool)) else f"<{type(value).__name__}>"


def _safe_value(value, depth=0):
    if isinstance(value, str):
        return redact(value)
    if value is None or type(value) is bool:
        return value
    if isinstance(value, int):
        return int.__int__(value)
    if isinstance(value, float):
        return float.__float__(value)
    if depth >= 8:
        return REDACTED
    if isinstance(value, dict):
        return {_safe_key(key): REDACTED if _private_field(key) else _safe_value(item, depth + 1)
                for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        values = [_safe_value(item, depth + 1) for item in value]
        return tuple(values) if isinstance(value, tuple) else values
    if isinstance(value, bytes):
        return redact(value.decode("utf-8", errors="replace"))
    if isinstance(value, BaseException):
        return _exception_diagnostics(value)
    return redact(f"<{type(value).__name__}>")


def _sanitize_core(record):
    # pypdf warnings can interpolate original document bytes or preformatted
    # parser exceptions. Keep severity, source module and record location.
    if record.name == "pypdf" or record.name.startswith("pypdf."):
        record.msg = "Document parser diagnostic withheld (content may be private)"
        record.args = ()
    # Preserve dictionary messages and lazy %-formatting for host formatters.
    # Do not rewrite host-factory metadata before its logger filters run.
    record.msg = _safe_value(record.msg)
    record.args = _safe_value(record.args)
    # The host formatter owns message interpolation. Eager getMessage() breaks
    # structured formatters which interpret msg/args without %-formatting.
    if record.exc_info:
        record.exc_text = _exception_diagnostics(record.exc_info[1])
        # Formatters must never receive an exception containing private text.
        record.exc_info = None
    elif record.exc_text and not isinstance(record.exc_text, _DiagnosticText):
        record.exc_text = _DiagnosticText("Cached exception details withheld")
    if record.stack_info:
        record.stack_info = "Stack source withheld"
    return record


def _sanitize_record(record):
    _sanitize_core(record)
    safe = {}
    for key, value in list(record.__dict__.items()):
        if key == "exc_text":
            safe[key] = value
        elif key == "message":
            # A previous formatter may have cached arbitrary text here.
            safe[key] = redact(record.getMessage())
        else:
            safe[_safe_key(key)] = REDACTED if _private_field(key) else _safe_value(value)
    record.__dict__.clear()
    record.__dict__.update(safe)
    return record


class _RedactionFilter(logging.Filter):
    _labbase_redaction_filter = True

    def filter(self, record):
        if record.levelno < logging.WARNING and any(
            record.name == name or record.name.startswith(name + ".") for name in _QUIET_LOGGERS
        ):
            return False
        try:
            _sanitize_record(record)
        except Exception:
            return False
        return True


class _RedactingFormatter(logging.Formatter):
    _labbase_redacting_formatter = True

    def __init__(self, formatter):
        super().__init__()
        self.formatter = formatter or logging.Formatter()

    def format(self, record):
        try:
            # A host formatter must not contaminate records for other handlers.
            safe = _sanitize_record(copy.copy(record))
            rendered = self.formatter.format(safe)
            if isinstance(rendered, str):
                return redact(rendered)
        except Exception:
            pass
        # Non-string results are invalid formatters; never stringify them.
        return "ERROR | labbase | Log entry withheld: formatting failed"


def configure_logging():
    """Protect root and non-propagating handlers, even with Debug disabled."""
    global config, DEBUG_ENABLED
    with _CONFIGURATION_LOCK:
        # Handler.handleError otherwise prints its raw I/O exception directly
        # to stderr, bypassing both filters and formatters (also in Debug mode).
        logging.raiseExceptions = False
        previous_factory = logging.getLogRecordFactory()
        if not getattr(previous_factory, "_labbase_redaction_factory", False):
            def record_factory(*args, **kwargs):
                try:
                    record = previous_factory(*args, **kwargs)
                    return _sanitize_core(record)
                except Exception:
                    return logging.LogRecord(
                        "labbase", logging.ERROR, __file__, 0,
                        "Log entry withheld: redaction failed", (), None,
                    )

            record_factory._labbase_redaction_factory = True
            logging.setLogRecordFactory(record_factory)

        root = logging.getLogger()
        if not root.handlers:
            logging.basicConfig(
                level=logging.WARNING,
                format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            )
        logger.setLevel(logging.INFO if DEBUG_ENABLED else logging.WARNING)
        for name in _QUIET_LOGGERS:
            logging.getLogger(name).setLevel(logging.WARNING)

        loggers = [root, *[item for item in logging.Logger.manager.loggerDict.values()
                          if isinstance(item, logging.Logger)]]
        handlers = {handler for item in loggers for handler in item.handlers}
        if logging.lastResort is not None:
            handlers.add(logging.lastResort)
        pending = list(handlers)
        while pending:
            handler = pending.pop()
            targets = []
            if isinstance(handler, MemoryHandler) and handler.target is not None:
                targets.append(handler.target)
            if isinstance(handler, QueueHandler):
                targets.extend(getattr(getattr(handler, "listener", None), "handlers", ()))
            for target in targets:
                if target not in handlers:
                    handlers.add(target)
                    pending.append(target)
        for handler in handlers:
            existing = [item for item in handler.filters if getattr(item, "_labbase_redaction_filter", False)]
            for item in existing:
                handler.removeFilter(item)
            # Hosting filters may add fields. Redaction must always run last.
            handler.addFilter(existing[0] if existing else _RedactionFilter())
            if not getattr(handler.formatter, "_labbase_redacting_formatter", False):
                handler.setFormatter(_RedactingFormatter(handler.formatter))
        if config is None:
            from bot.utils import config as application_config
            config = application_config
            # dotenv may supply the opt-in; read it only after the safe load.
            DEBUG_ENABLED = os.getenv("LABBASE_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
            logger.setLevel(logging.INFO if DEBUG_ENABLED else logging.WARNING)


def log_error(event, error=None):
    """Report type and traceback locations without exception text, locals or source."""
    details = []
    if isinstance(error, BaseException):
        details.append(f"error_type={type(error).__name__}")
        for frame, line in traceback.walk_tb(error.__traceback__):
            details.append(f"{os.path.basename(frame.f_code.co_filename)}:{line} in {frame.f_code.co_name}")
    logger.error("%s", redact(" | ".join([event, *details])))
