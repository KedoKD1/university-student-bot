"""Offline Telegram/Supabase fixtures; no credentials or network calls."""
import copy
import importlib
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, sentinel

from telegram import CallbackQuery, Chat, Message, MessageEntity, Update, User
from telegram.ext import ContextTypes

from bot.utils import config

with patch.multiple(config, SUPABASE_URL=sentinel.url, SUPABASE_KEY=sentinel.key), patch(
    "supabase.create_client", return_value=MagicMock()
):
    import bot.database.client

from bot.utils import permissions

HANDLERS = (
    "admin", "admin_subjects", "admin_files", "admin_summaries", "admin_drawings",
    "admin_schedules", "admin_grades", "admin_exam_dates", "admin_tools",
    "admin_notifications", "admin_settings", "bundle_descriptions",
)
MODULES = {name: importlib.import_module(f"bot.handlers.{name}") for name in HANDLERS}
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("labbase_entrypoint", ROOT / "bot.py")
entrypoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrypoint)


class Database:
    def __init__(self):
        self.rows = {
            "admins": [
                {"id": 1, "telegram_id": 101, "role": "owner", "is_active": True},
                {"id": 2, "telegram_id": 102, "role": "admin", "is_active": True},
                {"id": 3, "telegram_id": 103, "role": "moderator", "is_active": True},
                {"id": 4, "telegram_id": 104, "role": "admin", "is_active": True},
            ],
            "role_permissions": [],
            "stages": [{"id": 7, "stage_number": 1, "is_active": True}],
            "subjects": [{"id": 17, "stage_id": 7, "name": "رياضيات", "description": None,
                          "sort_order": 1, "is_active": True}],
        }
        self.writes = []
        self.reads = []
        self.failure = None

    def grant(self, role, *names):
        self.rows["role_permissions"] = [
            row for row in self.rows["role_permissions"] if row["role"] != role
        ] + [{"role": role, "permissions": {"name": name}} for name in names]

    def table(self, name):
        return Query(self, name)


class Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.filters, self.action, self.payload = [], "select", None
        self.maximum = None
        self.negate = False

    def select(self, *args, **kwargs):
        return self

    def eq(self, key, value):
        self.filters.append(lambda row: str(row.get(key)) == str(value))
        return self

    def neq(self, key, value):
        self.filters.append(lambda row: str(row.get(key)) != str(value))
        return self

    def is_(self, key, value):
        predicate = lambda row: row.get(key) is None if value == "null" else row.get(key) == value
        self.filters.append((lambda row: not predicate(row)) if self.negate else predicate)
        self.negate = False
        return self

    def ilike(self, key, value):
        value = value.replace(r"\_", "_")
        self.filters.append(lambda row: str(row.get(key, "")).lower() == value.lower())
        return self

    def in_(self, key, values):
        self.filters.append(lambda row: row.get(key) in values)
        return self

    @property
    def not_(self):
        self.negate = True
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, value):
        self.maximum = value
        return self

    def insert(self, payload):
        self.action, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.action, self.payload = "update", payload
        return self

    def upsert(self, payload, **kwargs):
        self.action, self.payload = "upsert", payload
        return self

    def execute(self):
        if self.db.failure == (self.table, self.action):
            raise RuntimeError("internal database detail")
        rows = self.db.rows.setdefault(self.table, [])
        matched = [row for row in rows if all(test(row) for test in self.filters)]
        if self.action in ("insert", "upsert"):
            row = copy.deepcopy(self.payload)
            row.setdefault("id", max([r.get("id", 0) for r in rows] + [0]) + 1)
            rows.append(row)
            matched = [row]
        elif self.action == "update":
            for row in matched:
                row.update(self.payload)
        if self.action == "select":
            self.db.reads.append(self.table)
        else:
            self.db.writes.append((self.table, self.action, copy.deepcopy(self.payload)))
        if self.maximum is not None:
            matched = matched[:self.maximum]
        return SimpleNamespace(data=copy.deepcopy(matched), count=len(matched))


def context(data=None):
    bot = SimpleNamespace(
        id=0, username="offline_test_bot",
        send_message=AsyncMock(), edit_message_text=AsyncMock(),
        answer_callback_query=AsyncMock(),
    )
    return SimpleNamespace(user_data={}, admin_data=data if data is not None else {}, bot=bot)


def update(user_id, ctx, *, text=None, data=None, chat_id=700, message_id=1, **attachments):
    user = User(user_id, "Administrator", False)
    sender = user if data is None else User(0, "Bot", True)
    entities = [MessageEntity(MessageEntity.BOT_COMMAND, 0, len(text.split()[0]))] if text and text.startswith("/") else None
    message = Message(message_id, datetime.now(timezone.utc), Chat(chat_id, "group"),
                      from_user=sender, text=text or "Admin menu", entities=entities, **attachments)
    message.set_bot(ctx.bot)
    if data is None:
        return Update(message_id, message=message)
    query = CallbackQuery(str(message_id), user, "offline", message=message, data=data)
    query.set_bot(ctx.bot)
    return Update(message_id, callback_query=query)


def registered_handlers(*, with_context_types=False):
    application = MagicMock()
    registrations = []
    application.add_handler.side_effect = lambda handler, group=0: registrations.append((group, handler))
    with patch.object(entrypoint, "Application") as factory, patch.object(
        entrypoint, "validate_config"
    ), patch.object(entrypoint, "BOT_TOKEN", sentinel.token), patch.object(
        entrypoint, "configure_logging"
    ), patch.object(entrypoint, "supabase", Database()), patch("builtins.print"):
        builder = factory.builder.return_value
        builder.token.return_value = builder
        builder.context_types.return_value = builder
        builder.build.return_value = application
        entrypoint.main()
        configured_context = (builder.context_types.call_args.args[0]
                              if builder.context_types.called else ContextTypes())
    return (registrations, configured_context) if with_context_types else registrations
