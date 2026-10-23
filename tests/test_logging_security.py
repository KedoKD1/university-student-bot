"""Assert emitted log output using synthetic credentials and offline APIs only."""
import asyncio
import ast
import builtins
import contextlib
import importlib.util
import io
import json
import logging
import logging.handlers
import os
from pathlib import Path
import queue
import runpy
import subprocess
import sys
import tempfile
import traceback
import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import quote, unquote_plus

import httpx
from telegram.ext import Application, ApplicationHandlerStop
from telegram.warnings import PTBUserWarning

from tests.admin_support import ROOT, Database, MODULES, context, registered_handlers, update
from bot.utils import config, debug_logger, logging_security as security
from bot.utils import permission_guard as guard


TOKEN = '123456789:AA_SYNTHETIC_TOKEN_FOR_LOG_TESTS_1234567'
URL = 'https://synthetic-log-project.supabase.co'
KEY = 'sb_secret_SYNTHETIC_LOG_TEST_KEY_123456789'
PRIVATE_TEXT = 'PRIVATE_STUDENT_MESSAGE_DO_NOT_LOG'
PRIVATE_CALLBACK = 'PRIVATE_CALLBACK_DATA_DO_NOT_LOG'


class LoggingSecurityTests(unittest.TestCase):
    def setUp(self):
        self.factory = logging.getLogRecordFactory()
        self.raise_exceptions = logging.raiseExceptions
        self.snapshots = {}
        self.handler_snapshots = {}
        self.initial_names = set(logging.Logger.manager.loggerDict)
        loggers = [logging.getLogger(), *[item for item in logging.Logger.manager.loggerDict.values()
                                        if isinstance(item, logging.Logger)]]
        for item in loggers:
            self.snapshots[item] = (item.level, item.disabled, item.propagate, list(item.handlers), list(item.filters))
            for handler in item.handlers:
                self.handler_snapshots[handler] = (handler.formatter, list(handler.filters))
        if logging.lastResort is not None:
            self.handler_snapshots[logging.lastResort] = (logging.lastResort.formatter, list(logging.lastResort.filters))
        self.root = logging.getLogger()
        self.root.handlers = []
        self.root.setLevel(logging.DEBUG)
        self.output = io.StringIO()
        self.handler = logging.StreamHandler(self.output)
        self.handler.setFormatter(logging.Formatter('HOST %(levelname)s %(name)s %(message)s'))
        self.root.addHandler(self.handler)
        self.synthetic = patch.multiple(config, BOT_TOKEN=TOKEN, SUPABASE_URL=URL, SUPABASE_KEY=KEY)
        self.synthetic.start()
        self.addCleanup(self.synthetic.stop)
        self.configure(False)

    def tearDown(self):
        logging.setLogRecordFactory(self.factory)
        logging.raiseExceptions = self.raise_exceptions
        for logger, (level, disabled, propagate, handlers, filters) in self.snapshots.items():
            logger.setLevel(level)
            logger.disabled, logger.propagate = disabled, propagate
            logger.handlers, logger.filters = handlers, filters
        for handler, (formatter, filters) in self.handler_snapshots.items():
            handler.setFormatter(formatter)
            handler.filters = filters
        for name in set(logging.Logger.manager.loggerDict) - self.initial_names:
            item = logging.Logger.manager.loggerDict[name]
            if isinstance(item, logging.Logger):
                item.handlers = []
                item.filters = []
                item.setLevel(logging.NOTSET)
                item.propagate = True
        self.handler.close()

    def configure(self, debug):
        with patch.object(security, 'DEBUG_ENABLED', debug):
            security.configure_logging()

    def assert_safe(self, output=None):
        output = self.output.getvalue() if output is None else output
        for value in (TOKEN, URL, KEY, 'synthetic-log-project.supabase.co', quote(TOKEN, safe=''),
                      quote(URL, safe=''), quote(KEY, safe='')):
            self.assertNotIn(value, output)
        self.assertNotIn('--- Logging error ---', output)

    def test_existing_root_handler_redacts_formatted_messages_in_both_modes(self):
        for debug in (False, True):
            self.configure(debug)
            security.logger.error('operation failed token=%s url=%s key=%r', TOKEN, URL, KEY)
            security.logger.error('mapped=%(secret)s', {'secret': KEY})
        self.assert_safe()
        self.assertIn('HOST ERROR labbase operation failed', self.output.getvalue())
        self.assertIn('[REDACTED]', self.output.getvalue())

    def test_url_paths_query_strings_json_escapes_and_encoding_are_redacted(self):
        security.logger.error('https://api.telegram.org/bot%s/sendMessage?key=%s', TOKEN, KEY)
        security.logger.error('%s/rest/v1/subjects?apikey=%s', URL, KEY)
        security.logger.error('%s %s %s', quote(TOKEN, safe=''), quote(URL, safe='').lower(), quote(quote(TOKEN, safe=''), safe=''))
        security.logger.error('%s', URL.replace('/', r'\/'))
        self.assert_safe()
        self.assertNotIn(quote(quote(TOKEN, safe=''), safe=''), self.output.getvalue())
        self.assertNotIn(URL.replace('/', r'\/'), self.output.getvalue())

    def test_unconfigured_but_recognizable_telegram_tokens_are_redacted(self):
        other = '987654321:AA_OTHER_SYNTHETIC_TOKEN_123456789012345'
        security.logger.error('https://api.telegram.org/bot%s/getMe', other)
        self.assertNotIn(other, self.output.getvalue())
        self.assertIn('[REDACTED]', self.output.getvalue())

    def test_configured_legacy_supabase_key_is_redacted(self):
        legacy = 'eyJ_SYNTHETIC_HEADER.eyJ_SYNTHETIC_PAYLOAD.SYNTHETIC_SIGNATURE'
        with patch.object(config, 'SUPABASE_KEY', legacy):
            security.logger.error('Authorization: Bearer %s', legacy)
        self.assertNotIn(legacy, self.output.getvalue())

    def test_exception_traceback_and_chained_cause_are_redacted(self):
        try:
            try:
                raise ValueError(f'GET {URL}/rest/v1?apikey={KEY}')
            except ValueError as cause:
                raise RuntimeError(f'https://api.telegram.org/bot{TOKEN}/sendMessage') from cause
        except RuntimeError:
            security.logger.exception('request failure')
        self.assert_safe()
        text = self.output.getvalue()
        self.assertIn('Traceback', text)
        self.assertIn('ValueError', text)
        self.assertIn('RuntimeError', text)
        self.assertIn('test_exception_traceback_and_chained_cause_are_redacted', text)

    @unittest.skipUnless(hasattr(builtins, 'ExceptionGroup'), 'ExceptionGroup requires Python 3.11')
    def test_exception_group_is_redacted(self):
        try:
            raise ExceptionGroup('operations', [RuntimeError(TOKEN), ValueError(KEY)])
        except ExceptionGroup:
            security.logger.exception('group failure')
        self.assert_safe()
        self.assertIn('ExceptionGroup', self.output.getvalue())

    def test_cached_traceback_stack_info_and_nested_extra_are_redacted(self):
        class StructuredFormatter(logging.Formatter):
            def format(self, record):
                return json.dumps(record.__dict__, default=str)

        self.handler.setFormatter(StructuredFormatter())
        self.configure(False)
        record = logging.LogRecord('labbase', logging.ERROR, URL, 7, TOKEN, (), None)
        record.exc_text = KEY
        record.stack_info = URL + TOKEN
        record.payload = {'authorization': [KEY, {'request': URL}], 'bytes': TOKEN.encode()}
        self.handler.handle(record)
        self.assert_safe()

    def test_cyclic_extras_do_not_crash_or_leak(self):
        payload = {'secret': KEY}
        payload['cycle'] = payload
        self.handler.setFormatter(logging.Formatter('%(message)s %(details)s'))
        self.configure(False)
        security.logger.error('cyclic payload', extra={'details': payload})
        self.assert_safe()
        self.assertIn('cyclic payload', self.output.getvalue())

    def test_redaction_occurs_after_existing_formatter_and_filter(self):
        class InjectingFilter(logging.Filter):
            def filter(self, record):
                record.injected = KEY
                return True

        self.handler.addFilter(InjectingFilter())
        self.handler.setFormatter(logging.Formatter('PREFIX ' + TOKEN + ' %(message)s %(injected)s'))
        self.configure(False)
        security.logger.error('formatted safely')
        self.assert_safe()
        self.assertIn('PREFIX [REDACTED]', self.output.getvalue())

    def test_non_propagating_logger_and_multiple_existing_handlers_are_protected(self):
        second = io.StringIO()
        handler = logging.StreamHandler(second)
        child = logging.getLogger('security_tests.private')
        child.propagate = False
        child.addHandler(handler)
        self.root.addHandler(handler)
        self.configure(False)
        child.error('%s %s %s', TOKEN, URL, KEY)
        self.assert_safe(second.getvalue())
        self.assertIn('[REDACTED]', second.getvalue())
        handler.close()

    def test_third_party_http_and_telegram_debug_logging_is_suppressed(self):
        for debug in (False, True):
            self.configure(debug)
            for name in ('httpx', 'httpcore.connection', 'telegram.ext.Application'):
                third_party = logging.getLogger(name)
                third_party.setLevel(logging.DEBUG)
                third_party.debug('HTTP_BODY_MARKER %s', PRIVATE_TEXT)
                third_party.info('HTTP_URL_MARKER https://api.telegram.org/bot%s/getMe', TOKEN)
                third_party.warning('HTTP_FAILURE_MARKER %s %s %s', TOKEN, URL, KEY)
        self.assert_safe()
        self.assertNotIn('HTTP_BODY_MARKER', self.output.getvalue())
        self.assertNotIn('HTTP_URL_MARKER', self.output.getvalue())
        self.assertNotIn(PRIVATE_TEXT, self.output.getvalue())
        self.assertIn('HTTP_FAILURE_MARKER', self.output.getvalue())

    def test_repeated_configuration_does_not_duplicate_handlers_filters_or_factory(self):
        handlers = list(self.root.handlers)
        factory = logging.getLogRecordFactory()
        formatter = self.handler.formatter
        for _ in range(5):
            self.configure(False)
        self.assertEqual(self.root.handlers, handlers)
        self.assertIs(logging.getLogRecordFactory(), factory)
        self.assertIs(self.handler.formatter, formatter)
        self.assertEqual(sum(getattr(item, '_labbase_redaction_filter', False) for item in self.handler.filters), 1)
        security.logger.error('ONCE_MARKER %s', TOKEN)
        self.assertEqual(self.output.getvalue().count('ONCE_MARKER'), 1)

    def test_empty_root_gets_one_handler_even_when_debug_is_disabled(self):
        self.root.handlers = []
        with contextlib.redirect_stderr(self.output):
            self.configure(False)
            created = self.root.handlers[0]
            self.configure(False)
            self.assertEqual(self.root.handlers, [created])
            security.logger.error('root initialized %s', KEY)
            created.close()
        self.assert_safe()
        self.assertIn('root initialized', self.output.getvalue())

    def test_existing_record_factory_is_chained_and_late_standard_handler_is_safe(self):
        calls = []

        def host_factory(*args, **kwargs):
            calls.append(True)
            return logging.LogRecord(*args, **kwargs)

        logging.setLogRecordFactory(host_factory)
        self.configure(False)
        late = io.StringIO()
        handler = logging.StreamHandler(late)
        child = logging.getLogger('security_tests.late_standard')
        child.propagate = False
        child.addHandler(handler)
        child.error('%s %s', TOKEN, KEY)
        self.assertEqual(calls, [True])
        self.assert_safe(late.getvalue())
        self.assertIn('[REDACTED]', late.getvalue())
        handler.close()

    def test_formatter_failure_does_not_leak_through_logging_handle_error(self):
        class BrokenFormatter(logging.Formatter):
            def format(self, record):
                raise ValueError(TOKEN + KEY)

        self.handler.setFormatter(BrokenFormatter())
        self.configure(False)
        with contextlib.redirect_stderr(self.output):
            security.logger.error('failure %s', TOKEN)
        self.assert_safe()
        self.assertIn('formatting failed', self.output.getvalue())

    def test_unformattable_message_fails_closed_without_breaking_the_caller(self):
        for message, arguments in (
            ('bad number %d', (TOKEN,)),
            ('trailing %', (KEY,)),
            ('%(missing)s', ({'provided': TOKEN},)),
            ('%s %s', (KEY,)),
        ):
            security.logger.error(message, *arguments)
        self.assert_safe()
        self.assertEqual(self.output.getvalue().count('formatting failed'), 4)

    def test_primitive_subclasses_never_run_custom_string_or_repr_methods(self):
        calls = []
        for fails in (False, True):
            def unsafe(value):
                calls.append(type(value).__name__)
                if fails:
                    raise RuntimeError(KEY)
                return TOKEN

            class HostText(str):
                __str__ = __repr__ = unsafe

            class HostNumber(int):
                __str__ = __repr__ = unsafe

            class HostFloat(float):
                __str__ = __repr__ = unsafe

            for value in (HostText('credential=' + KEY), HostNumber(7), HostFloat(1.25)):
                with self.subTest(fails=fails, kind=type(value).__name__):
                    security.logger.error('VALUE %s', value)
                    security.logger.error('REPRESENTATION %r', value)
                    security.logger.error('DETAILS', extra={'details': {value: value}})
                    self.assertEqual(calls, [])
            security.logger.error('number=%03d float=%.2f', HostNumber(7), HostFloat(1.25))
        self.assertEqual(calls, [])
        self.assert_safe()
        self.assertIn('number=007 float=1.25', self.output.getvalue())
        self.assertIn('credential=[REDACTED]', self.output.getvalue())

    def test_host_formatter_string_subclass_is_normalized_without_custom_str(self):
        calls = []

        class HostText(str):
            def __str__(self):
                calls.append('__str__')
                raise RuntimeError(KEY)

        class HostFormatter(logging.Formatter):
            def format(self, record):
                return HostText('HOST_RESULT ' + record.getMessage() + ' ' + TOKEN)

        self.handler.setFormatter(HostFormatter())
        self.configure(False)
        security.logger.error('FORMATTER_EVENT')
        self.assertEqual(calls, [])
        self.assert_safe()
        self.assertIn('HOST_RESULT FORMATTER_EVENT [REDACTED]', self.output.getvalue())

    def test_host_formatter_non_string_result_is_rejected_without_custom_str(self):
        calls = []
        for fails in (False, True):
            class HostResult:
                def __str__(self):
                    calls.append('__str__')
                    if fails:
                        raise RuntimeError(KEY)
                    return TOKEN

            class HostFormatter(logging.Formatter):
                def format(self, record):
                    return HostResult()

            self.handler.setFormatter(HostFormatter())
            self.configure(False)
            security.logger.error('FORMATTER_EVENT')
        self.assertEqual(calls, [])
        self.assert_safe()
        self.assertEqual(self.output.getvalue().count('formatting failed'), 2)

    def test_host_formatter_can_interpret_structured_arguments_without_percent_formatting(self):
        class HostFormatter(logging.Formatter):
            def format(self, record):
                return record.msg['event'] + ':' + ':'.join(record.args)

        self.handler.setFormatter(HostFormatter())
        self.configure(False)
        security.logger.error({'event': 'HOST_STRUCTURED_EVENT'}, 'SAFE_TAG', TOKEN)
        self.assert_safe()
        self.assertIn('HOST_STRUCTURED_EVENT:SAFE_TAG:[REDACTED]', self.output.getvalue())

    def test_log_error_omits_exception_text_but_preserves_type_and_location(self):
        try:
            raise RuntimeError(PRIVATE_TEXT + TOKEN + KEY)
        except RuntimeError as error:
            security.log_error('DATABASE_OPERATION_FAILED', error)
        self.assert_safe()
        self.assertNotIn(PRIVATE_TEXT, self.output.getvalue())
        self.assertIn('error_type=RuntimeError', self.output.getvalue())
        self.assertIn('test_log_error_omits_exception_text_but_preserves_type_and_location', self.output.getvalue())

    def test_update_logging_records_only_metadata_when_opted_in(self):
        ctx = context()
        for enabled in (False, True):
            self.configure(enabled)
            with patch.object(debug_logger, 'DEBUG_ENABLED', enabled):
                asyncio.run(debug_logger.log_update(update(105, ctx, text=PRIVATE_TEXT), ctx))
                asyncio.run(debug_logger.log_update(update(105, ctx, data=PRIVATE_CALLBACK), ctx))
        text = self.output.getvalue()
        self.assertIn('update_type=MESSAGE', text)
        self.assertIn('update_type=CALLBACK_QUERY', text)
        for private in (PRIVATE_TEXT, PRIVATE_CALLBACK, 'Administrator', 'user_id=', 'chat_id=', 'username='):
            self.assertNotIn(private, text)

    def test_update_logging_is_silent_when_debug_is_disabled(self):
        self.handler.addFilter(logging.Filter('labbase'))
        with patch.object(debug_logger, 'DEBUG_ENABLED', False):
            asyncio.run(debug_logger.log_update(update(105, context(), text=PRIVATE_TEXT), context()))
        self.assertEqual(self.output.getvalue(), '')

    def test_actual_httpx_request_uses_only_mock_transport_and_emits_no_url(self):
        self.configure(True)
        logging.getLogger('httpx').setLevel(logging.DEBUG)
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'ok': True}))
        with httpx.Client(transport=transport) as client:
            result = client.get(f'https://api.telegram.org/bot{TOKEN}/getMe')
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('HTTP Request:', self.output.getvalue())
        self.assert_safe()

    def test_standard_file_handler_emits_only_redacted_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic-test.log'
            handler = logging.FileHandler(path)
            self.root.addHandler(handler)
            self.configure(False)
            security.logger.error('file credentials %s %s %s', TOKEN, URL, KEY)
            handler.close()
            rendered = path.read_text()
            self.assert_safe(rendered)
            self.assertIn('file credentials [REDACTED]', rendered)

    def test_application_error_path_omits_sensitive_exception_details(self):
        query = SimpleNamespace(execute=lambda: None)
        query.select = lambda *args, **kwargs: query

        def fail():
            raise RuntimeError(PRIVATE_TEXT + TOKEN + KEY)

        query.execute = fail
        with patch.object(MODULES['admin_tools'].supabase, 'table', return_value=query):
            self.assertEqual(MODULES['admin_tools'].count_rows('summaries'), 0)
        self.assert_safe()
        self.assertNotIn(PRIVATE_TEXT, self.output.getvalue())
        self.assertIn('COUNT ERROR', self.output.getvalue())

    def test_no_application_print_calls_or_interpolated_exception_events_remain(self):
        for path in [ROOT / 'bot.py', *(ROOT / 'bot').rglob('*.py')]:
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotEqual(node.func.id, 'print', path)
                    if node.func.id == 'log_error' and node.args and isinstance(node.args[0], ast.JoinedStr):
                        names = {value.id for value in ast.walk(node.args[0]) if isinstance(value, ast.Name)}
                        self.assertFalse(names & {'exc', 'error', 'item_exc', 'update_exc'}, path)

    def test_failing_previous_record_factory_does_not_expose_its_exception(self):
        def fail(*args, **kwargs):
            raise RuntimeError(TOKEN + KEY)

        logging.setLogRecordFactory(fail)
        self.configure(False)
        security.logger.error('safe request')
        self.assert_safe()
        self.assertIn('redaction failed', self.output.getvalue())

    def test_global_error_reporting_is_safe_and_visible_in_both_modes(self):
        for enabled in (False, True):
            self.configure(enabled)
            with patch.object(debug_logger, 'DEBUG_ENABLED', enabled):
                try:
                    raise RuntimeError(PRIVATE_TEXT + TOKEN)
                except RuntimeError as error:
                    asyncio.run(debug_logger.global_error_handler(
                        update(105, context(), text=PRIVATE_TEXT), SimpleNamespace(error=error)))
        self.assert_safe()
        self.assertIn('UNHANDLED BOT ERROR', self.output.getvalue())
        self.assertNotIn(PRIVATE_TEXT, self.output.getvalue())
        asyncio.run(debug_logger.global_error_handler(None, SimpleNamespace(error=None)))

    def test_permission_guard_logging_omits_raw_callback_and_user_data(self):
        async def check():
            with patch.object(guard, 'DEBUG_ENABLED', True), patch.object(guard, 'has_permission', new=AsyncMock(return_value=False)):
                with self.assertRaises(ApplicationHandlerStop):
                    await guard.permission_guard(update(105, context(), data='admin_roles:' + PRIVATE_CALLBACK), context())
        self.configure(True)
        asyncio.run(check())
        self.assertNotIn(PRIVATE_CALLBACK, self.output.getvalue())
        self.assertNotIn('user_id=', self.output.getvalue())
        self.assertIn('manage_admins', self.output.getvalue())

    def test_database_initialization_failure_does_not_expose_sdk_exception(self):
        spec = importlib.util.spec_from_file_location('logging_test_client', ROOT / 'bot/database/client.py')
        module = importlib.util.module_from_spec(spec)
        with patch('supabase.create_client', side_effect=RuntimeError(TOKEN + URL + KEY)):
            with self.assertRaises(RuntimeError) as caught:
                spec.loader.exec_module(module)
        rendered = ''.join(traceback.format_exception(caught.exception))
        self.assert_safe(rendered)
        self.assert_safe()
        self.assertIn('Unable to initialize', rendered)

    def test_main_startup_failure_exits_nonzero_without_printing_raw_exception(self):
        import bot.database.client as client
        db = Database()
        db.failure = ('stages', 'select')
        with patch.object(client, 'supabase', db), contextlib.redirect_stderr(self.output):
            with self.assertRaises(SystemExit) as caught:
                runpy.run_path(str(ROOT / 'bot.py'), run_name='__main__')
        self.assertEqual(caught.exception.code, 1)
        self.assertIn('BOT STARTUP ERROR', self.output.getvalue())
        self.assertNotIn('internal database detail', self.output.getvalue())

    def test_native_ptb_dispatch_accepts_async_logging_in_both_modes(self):
        async def dispatch():
            for enabled in (False, True):
                self.configure(enabled)
                ctx = context()
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', PTBUserWarning)
                    registrations, types = registered_handlers(with_context_types=True)
                    app = Application.builder().context_types(types).bot(ctx.bot).updater(None).build()
                errors = []

                async def collect_error(incoming, current):
                    errors.append(current.error)

                app.add_error_handler(collect_error)
                for group, handler in registrations:
                    if group in (-6, 0):
                        app.add_handler(handler, group)
                app._initialized = True
                with patch.object(debug_logger, 'DEBUG_ENABLED', enabled):
                    await app.process_update(update(105, ctx, text='/start'))
                self.assertEqual(errors, [])
                self.assertIn('LabBase', ctx.bot.send_message.await_args.kwargs['text'])
        asyncio.run(dispatch())

    def test_default_debug_and_environment_opt_in_in_fresh_processes(self):
        script = '''
import asyncio
import io
import logging
import sys
from unittest.mock import patch
with patch('dotenv.load_dotenv'):
    from bot.utils import logging_security as security
    from bot.utils import debug_logger
assert security.DEBUG_ENABLED == (sys.argv[1] == 'true')
stream = io.StringIO()
logging.getLogger().addHandler(logging.StreamHandler(stream))
security.configure_logging()
security.logger.error('token=%s', security.config.BOT_TOKEN)
assert security.config.BOT_TOKEN not in stream.getvalue()
assert '[REDACTED]' in stream.getvalue()
'''
        for mode in (None, 'false', 'true', '1', 'YES', 'invalid'):
            env = {'PATH': os.defpath, 'BOT_TOKEN': TOKEN, 'SUPABASE_URL': URL, 'SUPABASE_KEY': KEY}
            if mode is not None:
                env['LABBASE_DEBUG'] = mode
            expected = 'true' if mode in ('true', '1', 'YES') else 'false'
            result = subprocess.run([sys.executable, '-c', script, expected], cwd=ROOT, env=env,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_exception_messages_notes_and_source_are_not_logged(self):
        try:
            try:
                raise ValueError(PRIVATE_TEXT + TOKEN)
            except ValueError as cause:
                error = RuntimeError(PRIVATE_CALLBACK + KEY)
                if hasattr(error, 'add_note'):
                    error.add_note(PRIVATE_TEXT)
                raise error from cause
        except RuntimeError:
            security.logger.exception('OPERATION_FAILED')
        text = self.output.getvalue()
        self.assert_safe(text)
        self.assertNotIn(PRIVATE_TEXT, text)
        self.assertNotIn(PRIVATE_CALLBACK, text)
        self.assertNotIn('raise ValueError(', text)
        self.assertIn('ValueError', text)
        self.assertIn('RuntimeError', text)
        self.assertIn('test_exception_messages_notes_and_source_are_not_logged', text)

    def test_exception_string_conversion_is_never_needed(self):
        class PrivateError(Exception):
            def __str__(self):
                raise AssertionError('exception text must not be inspected')

        try:
            raise PrivateError(PRIVATE_TEXT)
        except PrivateError:
            security.logger.exception('OPAQUE_EXCEPTION')
        self.assertIn('PrivateError', self.output.getvalue())
        self.assertNotIn(PRIVATE_TEXT, self.output.getvalue())

    def test_exception_objects_in_format_arguments_and_explicit_exc_info_are_safe(self):
        error = ValueError(PRIVATE_TEXT + PRIVATE_CALLBACK + TOKEN)
        security.logger.error('ARGUMENT_FAILURE %s', error)
        security.logger.error('REPRESENTATION_FAILURE %r', error)
        security.logger.error('EXPLICIT_EXCEPTION', exc_info=error)
        rendered = self.output.getvalue()
        self.assert_safe(rendered)
        self.assertNotIn(PRIVATE_TEXT, rendered)
        self.assertNotIn(PRIVATE_CALLBACK, rendered)
        self.assertIn('ValueError', rendered)

    def test_structured_exception_strings_and_objects_do_not_expose_messages(self):
        class StructuredFormatter(logging.Formatter):
            def format(self, record):
                return json.dumps(record.__dict__, default=str)

        self.handler.setFormatter(StructuredFormatter())
        self.configure(False)
        security.logger.error(
            {'event': 'STRUCTURED_ERROR', 'exception_message': PRIVATE_TEXT},
            extra={'error': PRIVATE_CALLBACK, 'details': {'exception': PRIVATE_TEXT},
                   'failure': ValueError(PRIVATE_TEXT + TOKEN)},
        )
        rendered = self.output.getvalue()
        self.assert_safe(rendered)
        self.assertNotIn(PRIVATE_TEXT, rendered)
        self.assertNotIn(PRIVATE_CALLBACK, rendered)
        self.assertIn('ValueError', rendered)

    @unittest.skipUnless(hasattr(builtins, 'ExceptionGroup'), 'ExceptionGroup requires Python 3.11')
    def test_exception_group_messages_and_notes_are_not_logged(self):
        try:
            error = ValueError(PRIVATE_TEXT)
            error.add_note(PRIVATE_CALLBACK)
            raise ExceptionGroup(PRIVATE_CALLBACK, [error, RuntimeError(KEY)])
        except ExceptionGroup:
            security.logger.exception('GROUP_FAILURE')
        rendered = self.output.getvalue()
        self.assert_safe(rendered)
        self.assertNotIn(PRIVATE_TEXT, rendered)
        self.assertNotIn(PRIVATE_CALLBACK, rendered)
        for name in ('ExceptionGroup', 'ValueError', 'RuntimeError'):
            self.assertIn(name, rendered)

    def test_cached_exception_and_stack_source_are_withheld(self):
        record = logging.LogRecord('labbase', logging.ERROR, __file__, 7, 'CACHED_FAILURE', (), None)
        record.exc_text = PRIVATE_TEXT + TOKEN
        record.stack_info = PRIVATE_CALLBACK + KEY
        self.handler.handle(record)
        text = self.output.getvalue()
        self.assert_safe(text)
        self.assertNotIn(PRIVATE_TEXT, text)
        self.assertNotIn(PRIVATE_CALLBACK, text)
        self.assertIn('CACHED_FAILURE', text)

    def test_structured_message_and_custom_attributes_hide_private_payload_fields(self):
        self.handler.setFormatter(logging.Formatter('%(message)s %(details)s %(callback_data)s %(text)s'))
        self.configure(False)
        security.logger.error(
            {'event': 'UPLOAD_FAILED', 'student_message': PRIVATE_TEXT, 'callback_data': PRIVATE_CALLBACK},
            extra={'details': {'text': PRIVATE_TEXT, 'event': 'SAFE_EVENT', 'key': KEY},
                   'callback_data': PRIVATE_CALLBACK, 'text': PRIVATE_TEXT},
        )
        self.assert_safe()
        self.assertNotIn(PRIVATE_TEXT, self.output.getvalue())
        self.assertNotIn(PRIVATE_CALLBACK, self.output.getvalue())
        self.assertIn('UPLOAD_FAILED', self.output.getvalue())
        self.assertIn('SAFE_EVENT', self.output.getvalue())

    def test_custom_attribute_names_are_redacted_for_json_formatters(self):
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                return json.dumps(record.__dict__, default=str)

        self.handler.setFormatter(JSONFormatter())
        self.configure(False)
        security.logger.error('STRUCTURED_EVENT', extra={TOKEN: KEY, URL: {'callback_data': PRIVATE_CALLBACK}})
        self.assert_safe()
        self.assertNotIn(PRIVATE_CALLBACK, self.output.getvalue())
        self.assertIn('STRUCTURED_EVENT', self.output.getvalue())

    def test_factory_preserves_host_record_type_metadata_and_lazy_format_arguments(self):
        marker = object()

        class HostRecord(logging.LogRecord):
            pass

        def host_factory(*args, **kwargs):
            record = HostRecord(*args, **kwargs)
            record.counter = 17
            record.host_state = marker
            return record

        observed = []

        class ObserveBeforeHandlers(logging.Filter):
            def filter(self, record):
                observed.append((type(record), record.counter, record.host_state, record.msg, record.args))
                return True

        logging.setLogRecordFactory(host_factory)
        observer = ObserveBeforeHandlers()
        security.logger.addFilter(observer)
        self.handler.setFormatter(logging.Formatter('%(counter)03d %(message)s'))
        self.configure(False)
        security.logger.error('retry=%d credential=%s', 3, TOKEN)
        self.assertEqual(len(observed), 1)
        record_type, count, state, message, args = observed[0]
        self.assertIs(record_type, HostRecord)
        self.assertIs(state, marker)
        self.assertEqual((count, message, args), (17, 'retry=%d credential=%s', (3, '[REDACTED]')))
        self.assertIn('017 retry=3', self.output.getvalue())
        self.assert_safe()

    def test_structured_formatter_can_still_read_message_as_dictionary(self):
        class EventFormatter(logging.Formatter):
            def format(self, record):
                return record.msg['event'] + ':' + record.msg['secret']

        self.handler.setFormatter(EventFormatter())
        self.configure(False)
        security.logger.error({'event': 'STRUCTURED_UPLOAD', 'secret': KEY})
        self.assertIn('STRUCTURED_UPLOAD:[REDACTED]', self.output.getvalue())
        self.assert_safe()

    def test_reinitialization_places_redaction_after_host_filters_for_raw_handlers(self):
        class RawHandler(logging.Handler):
            def emit(self, record):
                self_output.write(json.dumps(record.__dict__, default=str))

        class HostFilter(logging.Filter):
            def filter(self, record):
                record.payload = PRIVATE_TEXT
                record.__dict__[TOKEN] = KEY
                return True

        self_output = self.output
        handler = RawHandler()
        self.root.addHandler(handler)
        self.configure(False)
        handler.addFilter(HostFilter())
        self.configure(False)
        security.logger.error('RAW_HANDLER_EVENT')
        self.assert_safe()
        self.assertNotIn(PRIVATE_TEXT, self.output.getvalue())
        self.assertIn('RAW_HANDLER_EVENT', self.output.getvalue())
        self.assertEqual(sum(getattr(item, '_labbase_redaction_filter', False) for item in handler.filters), 1)
        handler.close()

    def test_formatter_cannot_mutate_records_seen_by_subsequent_handlers(self):
        class MutatingFormatter(logging.Formatter):
            def format(self, record):
                record.text = PRIVATE_TEXT
                record.__dict__[TOKEN] = KEY
                return 'CUSTOM_FORMATTER ' + record.getMessage()

        observed = []

        class Observer(logging.Handler):
            def emit(self, record):
                observed.append(dict(record.__dict__))

        self.handler.setFormatter(MutatingFormatter())
        observer = Observer()
        self.root.addHandler(observer)
        self.configure(False)
        security.logger.error('ISOLATED_FORMATTING')
        rendered = json.dumps(observed, default=str)
        self.assert_safe(rendered)
        self.assertNotIn(PRIVATE_TEXT, rendered)
        self.assertNotIn('text', observed[0])
        observer.close()

    def test_late_handler_structured_fields_are_protected_after_reinitialization(self):
        late = io.StringIO()
        handler = logging.StreamHandler(late)
        handler.setFormatter(logging.Formatter('%(message)s %(details)s %(callback_data)s'))
        self.root.addHandler(handler)
        self.configure(False)
        security.logger.error('LATE_EVENT', extra={'details': {'secret': KEY}, 'callback_data': PRIVATE_CALLBACK})
        self.assert_safe(late.getvalue())
        self.assertNotIn(PRIVATE_CALLBACK, late.getvalue())
        self.assertIn('LATE_EVENT', late.getvalue())
        handler.close()

    def test_reinitialization_preserves_host_handler_levels_and_filter_order(self):
        first, second = logging.Filter(), logging.Filter()
        self.handler.filters = [first, second]
        self.handler.setLevel(logging.ERROR)
        self.configure(True)
        self.configure(False)
        self.assertEqual(self.handler.filters[:2], [first, second])
        self.assertEqual(len(self.handler.filters), 3)
        self.assertEqual(self.handler.level, logging.ERROR)
        self.assertEqual(self.root.level, logging.DEBUG)

    def test_late_non_propagating_handler_gets_safe_exception_core(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        child = logging.getLogger('security_tests.late_exception')
        child.propagate = False
        child.addHandler(handler)
        try:
            raise ValueError(PRIVATE_TEXT + TOKEN)
        except ValueError:
            child.exception('LATE_EXCEPTION')
        self.assert_safe(stream.getvalue())
        self.assertNotIn(PRIVATE_TEXT, stream.getvalue())
        self.assertIn('ValueError', stream.getvalue())
        handler.close()

    def test_queue_handler_enqueues_redacted_structured_record_without_exception_text(self):
        pending = queue.Queue()
        handler = logging.handlers.QueueHandler(pending)
        self.root.addHandler(handler)
        self.configure(False)
        try:
            raise ValueError(PRIVATE_TEXT + KEY)
        except ValueError:
            security.logger.exception('QUEUED_EVENT', extra={'callback_data': PRIVATE_CALLBACK, 'details': {TOKEN: URL}})
        record = pending.get_nowait()
        rendered = json.dumps(record.__dict__, default=str)
        self.assert_safe(rendered)
        self.assertNotIn(PRIVATE_TEXT, rendered)
        self.assertNotIn(PRIVATE_CALLBACK, rendered)
        self.assertIn('ValueError', rendered)
        handler.close()

    def test_memory_handler_target_with_custom_formatter_is_protected(self):
        stream = io.StringIO()
        target = logging.StreamHandler(stream)
        target.setFormatter(logging.Formatter('MEMORY_TARGET ' + TOKEN + ' %(message)s'))
        handler = logging.handlers.MemoryHandler(1, target=target)
        self.root.addHandler(handler)
        self.configure(False)
        self.configure(False)
        security.logger.error('BUFFERED_EVENT')
        self.assert_safe(stream.getvalue())
        self.assertIn('MEMORY_TARGET [REDACTED]', stream.getvalue())
        self.assertEqual(sum(getattr(item, '_labbase_redaction_filter', False) for item in target.filters), 1)
        handler.close()
        target.close()

    def test_queue_listener_targets_are_protected_when_attached_to_queue_handler(self):
        pending, stream = queue.Queue(), io.StringIO()
        target = logging.StreamHandler(stream)
        target.setFormatter(logging.Formatter('LISTENER_TARGET ' + KEY + ' %(message)s'))
        handler = logging.handlers.QueueHandler(pending)
        handler.listener = logging.handlers.QueueListener(pending, target)
        self.root.addHandler(handler)
        self.configure(False)
        security.logger.error('LISTENER_EVENT')
        handler.listener.handle(pending.get_nowait())
        self.assert_safe(stream.getvalue())
        self.assertIn('LISTENER_TARGET [REDACTED]', stream.getvalue())
        handler.close()
        target.close()

    def test_http_handler_which_does_not_use_a_formatter_sends_safe_fields(self):
        connection = SimpleNamespace(putrequest=lambda *a: None, putheader=lambda *a: None,
                                     endheaders=lambda: None, getresponse=lambda: None)
        sent = []
        connection.send = sent.append
        handler = logging.handlers.HTTPHandler('offline.invalid', '/logging-test', method='POST')
        self.root.addHandler(handler)
        self.configure(False)
        with patch.object(handler, 'getConnection', return_value=connection):
            security.logger.error('HTTP_HANDLER_EVENT', extra={'callback_data': PRIVATE_CALLBACK, TOKEN: KEY})
        rendered = unquote_plus(sent[0].decode())
        self.assert_safe(rendered)
        self.assertNotIn(PRIVATE_CALLBACK, rendered)
        self.assertIn('HTTP_HANDLER_EVENT', rendered)
        handler.close()

    def test_handler_io_failure_does_not_dump_raw_exception_to_stderr(self):
        handler = logging.handlers.HTTPHandler('offline.invalid', '/logging-test', method='POST')
        self.root.addHandler(handler)
        logging.raiseExceptions = True
        self.configure(False)
        stderr = io.StringIO()
        with patch.object(handler, 'getConnection', side_effect=OSError(PRIVATE_TEXT + TOKEN + KEY)):
            with contextlib.redirect_stderr(stderr):
                security.logger.error('HANDLER_IO_FAILURE')
        self.assertEqual(stderr.getvalue(), '')
        self.assertIn('HANDLER_IO_FAILURE', self.output.getvalue())
        handler.close()

    def test_pdf_parser_warning_keeps_location_without_document_content(self):
        from pypdf.generic import NumberObject

        self.handler.setFormatter(logging.Formatter('%(levelname)s %(name)s %(filename)s:%(lineno)d %(message)s'))
        self.configure(False)
        self.assertEqual(NumberObject(PRIVATE_TEXT), 0)
        rendered = self.output.getvalue()
        self.assertNotIn(PRIVATE_TEXT, rendered)
        self.assertIn('WARNING pypdf', rendered)
        self.assertRegex(rendered, r'\w+\.py:\d+ ')
        self.assertIn('Document parser diagnostic', rendered)

    def test_application_has_no_direct_output_or_subprocess_sinks(self):
        forbidden_modules = {'subprocess'}
        forbidden_names = {'print'}
        forbidden_suffixes = ('.stdout.write', '.stderr.write', '.stdout.writelines', '.stderr.writelines',
                              '.__stdout__.write', '.__stderr__.write', '.print_exc', '.print_exception',
                              '.print_stack', '.system', '.popen')
        for path in [ROOT / 'bot.py', *(ROOT / 'bot').rglob('*.py')]:
            tree = ast.parse(path.read_text())
            aliases = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    aliases.update((item.asname or item.name, item.name) for item in node.names)
                if isinstance(node, ast.ImportFrom):
                    aliases.update((item.asname or item.name, (node.module or '') + '.' + item.name) for item in node.names)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                parts, func = [], node.func
                while isinstance(func, ast.Attribute):
                    parts.insert(0, func.attr)
                    func = func.value
                if isinstance(func, ast.Name):
                    parts.insert(0, aliases.get(func.id, func.id))
                name = '.'.join(parts)
                self.assertFalse(name in forbidden_names or name == 'builtins.print'
                                 or name.split('.')[0] in forbidden_modules
                                 or name.endswith(forbidden_suffixes)
                                 or name in {'os.write', 'os.writev'}, f'{path}:{node.lineno}: {name}')

    def test_security_precedes_dotenv_and_telegram_import_logging(self):
        script = '''
import builtins
import io
import logging
import os
from unittest.mock import patch
stream = io.StringIO()
logging.getLogger().addHandler(logging.StreamHandler(stream))
logging.getLogger().setLevel(logging.DEBUG)
original_import = builtins.__import__
def observed_import(name, *args, **kwargs):
    if name == 'telegram':
        logging.getLogger('import_probe').warning('TELEGRAM_IMPORT %s', os.environ['BOT_TOKEN'])
    return original_import(name, *args, **kwargs)
def load_dotenv():
    logging.getLogger('dotenv').warning('DOTENV_LOAD %s', os.environ['SUPABASE_KEY'])
with patch('dotenv.load_dotenv', side_effect=load_dotenv), patch('builtins.__import__', side_effect=observed_import):
    from bot.utils import debug_logger
for key in ('BOT_TOKEN', 'SUPABASE_URL', 'SUPABASE_KEY'):
    assert os.environ[key] not in stream.getvalue(), key
assert 'TELEGRAM_IMPORT' in stream.getvalue()
assert 'DOTENV_LOAD' in stream.getvalue()
'''
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                                env={'PATH': os.defpath, 'BOT_TOKEN': TOKEN, 'SUPABASE_URL': URL, 'SUPABASE_KEY': KEY},
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_debug_opt_in_from_dotenv_still_works_after_safe_bootstrap(self):
        script = '''
import os
from unittest.mock import patch
def load_dotenv():
    os.environ['LABBASE_DEBUG'] = 'true'
with patch('dotenv.load_dotenv', side_effect=load_dotenv):
    from bot.utils import debug_logger, logging_security
assert debug_logger.DEBUG_ENABLED is True
assert logging_security.DEBUG_ENABLED is True
'''
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                                env={'PATH': os.defpath, 'BOT_TOKEN': TOKEN, 'SUPABASE_URL': URL, 'SUPABASE_KEY': KEY},
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
