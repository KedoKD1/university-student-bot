"""Student navigation regressions using native PTB dispatch, without live services."""
import copy
import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.ext import Application, CallbackQueryHandler
from telegram.warnings import PTBUserWarning

from tests.admin_support import Database, MODULES, context, permissions, registered_handlers, update
from bot.handlers import (
    content, exam_dates, grades, main_menu, schedules, search, stages,
    student_settings, subjects, user_tracking,
)
from bot.keyboards import content as content_keyboards
from bot.keyboards.main_menu import main_menu_keyboard
from bot.keyboards.subjects import PAGE_SIZE, subjects_keyboard
from bot.utils import chat_access, subscription


STUDENT_MODULES = (
    content, exam_dates, grades, main_menu, schedules, search, stages,
    student_settings, subjects,
)


class StudentUIUXTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database()
        self.db.rows['settings'] = [{'key': 'required_channel_id', 'value': '-1001'}]
        permissions.clear_permission_cache()
        self.addCleanup(permissions.clear_permission_cache)
        for module in (*STUDENT_MODULES, user_tracking, permissions, chat_access,
                       subscription, *MODULES.values()):
            if hasattr(module, 'supabase'):
                replacement = patch.object(module, 'supabase', self.db)
                replacement.start()
                self.addCleanup(replacement.stop)
        self.ctx = context()
        self.channel = SimpleNamespace(id=-1001, type='channel', username='labbase', invite_link=None)
        self.member = SimpleNamespace(status='member')
        own = SimpleNamespace(status='administrator')
        self.ctx.bot.get_chat = AsyncMock(return_value=self.channel)
        self.ctx.bot.get_chat_member = AsyncMock(
            side_effect=lambda chat, user: own if user == 0 else self.member
        )
        for name in ('send_document', 'send_photo', 'send_video', 'send_audio', 'send_media_group'):
            setattr(self.ctx.bot, name, AsyncMock())
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', PTBUserWarning)
            registrations, types = registered_handlers(with_context_types=True)
            self.app = Application.builder().context_types(types).bot(self.ctx.bot).updater(None).build()
        for group, handler in registrations:
            if group in (-5, -4, -2, 0):
                self.app.add_handler(handler, group)
        self.app._initialized = True
        self.errors = []

        async def collect_error(incoming, ctx):
            self.errors.append(ctx.error)

        self.app.add_error_handler(collect_error)

    async def dispatch(self, data=None, *, user_id=105, text=None):
        await self.app.process_update(update(user_id, self.ctx, data=data, text=text))
        self.assertEqual(self.errors, [])

    def rendered(self):
        return self.ctx.bot.edit_message_text.await_args.kwargs

    def buttons(self, rendered=None):
        return [button for row in (rendered or self.rendered())['reply_markup'].inline_keyboard
                for button in row]

    def callbacks(self, rendered=None):
        return [button.callback_data for button in self.buttons(rendered)]

    def assert_recovery(self, callback):
        self.assertIn(callback, self.callbacks())
        self.assertFalse(self.db.writes and any(
            name in {'subjects', 'files', 'summaries', 'drawings'} for name, _, _ in self.db.writes
        ))

    def add_subjects(self, total):
        self.db.rows['subjects'] = [dict(id=17 + index, stage_id=7, name=f'مادة {index + 1}',
                                        is_active=True, sort_order=index, description=None)
                                    for index in range(total)]

    def add_content(self, table, total=1):
        self.db.rows[table] = [dict(id=index + 1, subject_id=17, name=f'{table} {index + 1}',
                                   section_type='theoretical', is_active=True, deleted_at=None,
                                   sort_order=index, telegram_file_id=f'media_{index}', file_type='document')
                               for index in range(total)]

    def test_main_menu_layout_preserves_every_callback(self):
        keyboard = main_menu_keyboard(105).inline_keyboard
        self.assertEqual([[button.callback_data for button in row] for row in keyboard], [
            ['main:stages:105'], ['main:exams:105'],
            ['main:schedule:105', 'main:search:105'],
            ['main:grades:105', 'main:settings:105'],
        ])
        self.assertEqual([len(row) for row in keyboard], [1, 1, 2, 2])
        self.assertIn('LabBase', main_menu.main_menu_text())
        self.assertIn('المختبرات الطبية', main_menu.main_menu_text())

    async def test_main_menu_sections_remain_reachable(self):
        await self.dispatch(text='/start')
        self.assertEqual(len(self.ctx.bot.send_message.await_args.kwargs['reply_markup'].inline_keyboard), 4)
        for action, title in [('stages', 'المراحل الدراسية'), ('exams', 'مواعيد الامتحانات'),
                              ('schedule', 'الجداول الدراسية'), ('search', 'البحث'),
                              ('grades', 'الدرجات'), ('settings', 'إعدادات الطالب')]:
            with self.subTest(action=action):
                await self.dispatch(f'main:{action}:105')
                self.assertIn(title, self.rendered()['text'])

    async def test_empty_subjects_have_working_back_and_main_buttons(self):
        self.db.rows['subjects'] = []
        await self.dispatch('stage:7:105')
        self.assertIn('مواد المرحلة 1', self.rendered()['text'])
        self.assertIn('لا توجد مواد', self.rendered()['text'])
        self.assert_recovery('back_stages:105')
        self.assertIn('back_main:105', self.callbacks())
        await self.dispatch('back_stages:105')
        self.assertIn('stage:7:105', self.callbacks())
        await self.dispatch('back_main:105')
        self.assertIn('main:stages:105', self.callbacks())
        self.ctx.bot.send_message.assert_not_awaited()

    async def test_subject_pagination_preserves_order_and_context(self):
        self.add_subjects(13)
        for page, ids in [(0, range(17, 23)), (1, range(23, 29)), (2, range(29, 30))]:
            await self.dispatch(f'subjects_page:7:{page}:105')
            self.assertEqual([data for data in self.callbacks() if data.startswith('subject:')],
                             [f'subject:{value}:105' for value in ids])
            self.assertIn(f'الصفحة {page + 1} من 3', self.rendered()['text'])
            self.assertIn('مواد المرحلة 1', self.rendered()['text'])
            self.assertIn('back_stages:105', self.callbacks())
            self.assertNotIn('noop', self.callbacks())
            if page > 0:
                self.assertIn(f'subjects_page:7:{page - 1}:105', self.callbacks())
            if page < 2:
                self.assertIn(f'subjects_page:7:{page + 1}:105', self.callbacks())
        self.ctx.bot.send_message.assert_not_awaited()

    async def test_pagination_clamps_negative_outdated_and_empty_pages(self):
        self.add_subjects(7)
        for page, expected in [(-4, 'الصفحة 1 من 2'), (999, 'الصفحة 2 من 2')]:
            await self.dispatch(f'subjects_page:7:{page}:105')
            self.assertIn(expected, self.rendered()['text'])
        self.add_subjects(1)
        await self.dispatch('subjects_page:7:999:105')
        self.assertIn('subject:17:105', self.callbacks())
        self.db.rows['subjects'] = []
        await self.dispatch('subjects_page:7:999:105')
        self.assert_recovery('back_stages:105')

    async def test_pagination_filters_inactive_subjects_and_other_stages(self):
        self.add_subjects(PAGE_SIZE)
        self.db.rows['subjects'].extend([
            dict(id=40, stage_id=7, name='غير متاحة', is_active=False),
            dict(id=41, stage_id=8, name='مرحلة أخرى', is_active=True),
        ])
        await self.dispatch('stage:7:105')
        self.assertEqual(sum(data.startswith('subject:') for data in self.callbacks()), PAGE_SIZE)
        self.assertFalse(any(data.startswith('subjects_page:') for data in self.callbacks()))

    async def test_empty_and_failed_stage_lists_offer_main_menu(self):
        self.db.rows['stages'] = []
        for callback in ('main:stages:105', 'back_stages:105'):
            await self.dispatch(callback)
            self.assertIn('لا توجد مراحل', self.rendered()['text'])
            self.assert_recovery('back_main:105')
        self.db.failure = ('stages', 'select')
        await self.dispatch('main:stages:105')
        self.assertIn('تعذر تحميل', self.rendered()['text'])
        self.assert_recovery('back_main:105')

    async def test_missing_or_disabled_stage_recovers_from_old_buttons(self):
        for active in (False, None):
            self.db.rows['stages'] = [] if active is None else [dict(id=7, stage_number=1, is_active=active)]
            for callback in ('stage:7:105', 'subjects_page:7:0:105', 'back_subjects:7:105'):
                await self.dispatch(callback)
                self.assert_recovery('back_stages:105')
                self.assertNotIn('subject:17:105', self.callbacks())

    async def test_subject_unavailable_or_orphaned_never_leaves_a_dead_end(self):
        for rows in ([], [dict(id=17, is_active=False, stage_id=7)],
                     [dict(id=17, is_active=True, stage_id=None)]):
            self.db.rows['subjects'] = rows
            for callback in ('subject:17:105', 'back_content:17:105', 'content:files:17:105'):
                await self.dispatch(callback)
                self.assert_recovery('back_stages:105')

    async def test_subject_and_content_read_errors_offer_recovery_without_details(self):
        for table, callbacks in [
            ('stages', ['stage:7:105', 'subjects_page:7:0:105']),
            ('subjects', ['stage:7:105', 'subject:17:105', 'back_content:17:105', 'content:files:17:105']),
            ('files', ['content:files:all:17:105', 'files_section:theoretical:17:105', 'file:1:105']),
            ('summaries', ['content:summaries:all:17:105', 'summaries_section:practical:17:105',
                           'study_item:summaries:1:17:105']),
            ('drawings', ['content:drawings:all:17:105', 'study_item:drawings:1:17:105']),
        ]:
            for callback in callbacks:
                with self.subTest(table=table, callback=callback):
                    self.db.failure = (table, 'select')
                    await self.dispatch(callback)
                    self.assertIn('تعذر تحميل', self.rendered()['text'])
                    self.assertTrue(self.buttons())
                    self.assertNotIn('internal database detail', self.rendered()['text'])
        self.db.failure = None

    async def test_subject_content_headings_and_back_navigation_match(self):
        await self.dispatch('subject:17:105')
        subject_page = copy.deepcopy(self.rendered())
        self.assertIn('المادة: رياضيات', subject_page['text'])
        for kind, label in [('files', '📄 الملفات'), ('summaries', '📝 الملخصات'), ('drawings', '🎨 الرسومات')]:
            await self.dispatch(f'content:{kind}:17:105')
            self.assertIn(label, self.rendered()['text'])
            self.assertIn('المادة: رياضيات', self.rendered()['text'])
            self.assert_recovery('back_content:17:105')
            await self.dispatch('back_content:17:105')
            self.assertEqual(self.rendered()['text'], subject_page['text'])
        await self.dispatch('back_subjects:7:105')
        self.assertIn('subject:17:105', self.callbacks())

    async def test_empty_theoretical_and_practical_lists_have_working_back(self):
        for kind, prefix, title in [('files', 'files_section', 'الملفات'),
                                    ('summaries', 'summaries_section', 'الملخصات')]:
            for section, name in [('theoretical', 'النظري'), ('practical', 'العملي')]:
                await self.dispatch(f'{prefix}:{section}:17:105')
                self.assertIn(f'{title} — {name}', self.rendered()['text'])
                self.assertIn('المادة: رياضيات', self.rendered()['text'])
                self.assertIn('لا توجد', self.rendered()['text'])
                self.assert_recovery(f'content:{kind}:17:105')
                await self.dispatch(f'content:{kind}:17:105')
                self.assertIn('back_content:17:105', self.callbacks())
        self.ctx.bot.send_message.assert_not_awaited()

    async def test_empty_collections_offer_subject_and_main_recovery(self):
        for kind in ('files', 'summaries', 'drawings'):
            await self.dispatch(f'content:{kind}:all:17:105')
            self.assertIn('لا توجد', self.rendered()['text'])
            self.assertIn('المادة: رياضيات', self.rendered()['text'])
            self.assert_recovery('back_content:17:105')
            self.assertIn('back_main:105', self.callbacks())
        self.ctx.bot.send_media_group.assert_not_awaited()

    async def test_populated_sections_keep_filtering_and_item_callbacks(self):
        for kind, prefix, item_callback in [('files', 'files_section', 'file:1:105'),
                                            ('summaries', 'summaries_section', 'study_item:summaries:1:17:105')]:
            self.add_content(kind)
            self.db.rows[kind].extend([
                dict(self.db.rows[kind][0], id=2, section_type='practical'),
                dict(self.db.rows[kind][0], id=3, is_active=False),
                dict(self.db.rows[kind][0], id=4, deleted_at='2026-01-01'),
                dict(self.db.rows[kind][0], id=5, subject_id=18),
            ])
            await self.dispatch(f'{prefix}:theoretical:17:105')
            items = [data for data in self.callbacks() if data.startswith(('file:', 'study_item:'))]
            self.assertEqual(items, [item_callback])

    async def test_collection_delivery_keeps_media_description_counts_and_edits_navigation(self):
        for kind in ('files', 'summaries', 'drawings'):
            self.add_content(kind, 12)
            self.db.rows[kind].append(dict(self.db.rows[kind][0], id=20, telegram_file_id=None))
            self.db.rows['content_bundle_descriptions'] = [dict(subject_id=17, content_type=kind, description='وصف الحزمة')]
            self.ctx.bot.send_message.reset_mock()
            self.ctx.bot.send_media_group.reset_mock()
            await self.dispatch(f'content:{kind}:all:17:105')
            self.assertEqual([len(call.kwargs['media']) for call in self.ctx.bot.send_media_group.await_args_list], [10, 2])
            self.assertIn('تم إرسال: 12', self.rendered()['text'])
            self.assertIn('تعذر إرسال: 1', self.rendered()['text'])
            self.assert_recovery('back_content:17:105')
            messages = self.ctx.bot.send_message.await_args_list
            self.assertEqual([call.kwargs['text'] for call in messages], [] if kind == 'drawings' else ['وصف الحزمة'])

    async def test_failed_album_preserves_individual_delivery_fallback(self):
        self.add_content('files', 2)
        self.ctx.bot.send_media_group.side_effect = RuntimeError('offline album failure')
        await self.dispatch('content:files:all:17:105')
        self.assertEqual(self.ctx.bot.send_document.await_count, 2)
        self.assertIn('تم إرسال: 2', self.rendered()['text'])
        self.assertNotIn('offline album failure', self.rendered()['text'])

    async def test_individual_content_delivery_preserves_media_types_and_captions(self):
        for kind, callback in [('files', 'file:1:105'), ('summaries', 'study_item:summaries:1:17:105'),
                               ('drawings', 'study_item:drawings:1:17:105')]:
            self.add_content(kind)
            for media, method, parameter in [('document', 'send_document', 'document'), ('photo', 'send_photo', 'photo'),
                                              ('video', 'send_video', 'video'), ('audio', 'send_audio', 'audio')]:
                self.db.rows[kind][0].update(file_type=media, description='وصف المحتوى')
                await self.dispatch(callback)
                call = getattr(self.ctx.bot, method).await_args.kwargs
                self.assertEqual(call[parameter], 'media_0')
                self.assertIn('وصف المحتوى', call['caption'])

    async def test_deleted_or_missing_media_and_send_errors_have_back_navigation(self):
        for kind, callback in [('files', 'file:1:105'), ('summaries', 'study_item:summaries:1:17:105'),
                               ('drawings', 'study_item:drawings:1:17:105')]:
            for state in ('deleted', 'missing_media', 'send_error'):
                self.add_content(kind)
                row = self.db.rows[kind][0]
                row.update(deleted_at='2026-01-01' if state == 'deleted' else None,
                           telegram_file_id=None if state == 'missing_media' else 'media_0')
                self.ctx.bot.send_document.side_effect = RuntimeError('sensitive detail') if state == 'send_error' else None
                await self.dispatch(callback)
                self.assertTrue(self.buttons())
                self.assertNotIn('sensitive detail', self.rendered()['text'])
                self.assertNotIn('Telegram', self.rendered()['text'])
                self.assertIn('back_main:105', self.callbacks())

    async def test_search_cancel_uses_existing_main_route_and_clears_search_state(self):
        await self.dispatch('main:search:105')
        self.assertEqual([(b.text, b.callback_data) for b in self.buttons()], [('❌ إلغاء', 'back_main:105')])
        self.assertTrue(self.app.user_data[105]['search_mode'])
        self.assertIsNotNone(self.ctx.bot.send_message.await_args.kwargs['reply_markup'])
        await self.dispatch('back_main:105')
        self.assertNotIn('search_mode', self.app.user_data[105])
        self.assertNotIn('search_owner_id', self.app.user_data[105])
        self.assertIn('main:search:105', self.callbacks())

    async def test_foreign_callbacks_cannot_read_or_edit_student_navigation(self):
        callbacks = [
            (main_menu.main_menu_button, 'main:stages:105'), (main_menu.back_main, 'back_main:105'),
            (stages.stage_button, 'stage:7:105'), (stages.locked_stage_button, 'locked:7:105'),
            (subjects.subject_button, 'subject:17:105'), (subjects.subjects_page_button, 'subjects_page:7:1:105'),
            (subjects.back_to_subjects, 'back_subjects:7:105'), (subjects.back_to_stages, 'back_stages:105'),
            (content.show_files, 'content:files:17:105'), (content.show_file_section, 'files_section:theoretical:17:105'),
            (content.show_summaries_or_drawings, 'content:summaries:17:105'),
            (content.show_summary_section, 'summaries_section:practical:17:105'),
            (content.show_all_summaries, 'content:summaries:all:17:105'),
            (content.show_all_drawings, 'content:drawings:all:17:105'), (content.file_button, 'file:1:105'),
            (content.study_item_button, 'study_item:drawings:1:17:105'), (content.back_to_content, 'back_content:17:105'),
            (grades.grades_callback, 'main:grades:105'), (schedules.show_schedules, 'main:schedule:105'),
            (exam_dates.exam_stage, 'exam_stage:7:105'), (student_settings.student_settings_callback, 'main:settings:105'),
            (search.start_search, 'main:search:105'),
        ]
        for handler, data in callbacks:
            with self.subTest(data=data):
                before = list(self.db.reads)
                await handler(update(106, self.ctx, data=data), self.ctx)
                self.assertEqual(self.db.reads, before)
                self.assertTrue(self.ctx.bot.answer_callback_query.await_args.kwargs['show_alert'])
        self.ctx.bot.edit_message_text.assert_not_awaited()
        self.ctx.bot.send_message.assert_not_awaited()

    async def test_direct_search_route_rejects_a_foreign_menu_owner(self):
        await self.dispatch('main:search:105', user_id=106)
        self.assertNotIn('search_mode', self.app.user_data[106])
        self.ctx.bot.edit_message_text.assert_not_awaited()
        self.ctx.bot.send_message.assert_not_awaited()
        self.assertTrue(self.ctx.bot.answer_callback_query.await_args.kwargs['show_alert'])

    async def test_unsubscribed_student_is_still_blocked_before_ui_reads(self):
        self.member.status = 'left'
        for callback in ('stage:7:105', 'subjects_page:7:1:105', 'back_stages:105', 'back_content:17:105',
                         'content:files:all:17:105', 'file:1:105', 'main:settings:105'):
            await self.dispatch(callback)
        self.assertFalse(set(self.db.reads) & {'subjects', 'files', 'summaries', 'drawings', 'user_settings'})
        self.ctx.bot.edit_message_text.assert_not_awaited()
        self.assertIn('verify_subscription:105', self.callbacks(self.ctx.bot.send_message.await_args.kwargs))

    async def test_student_ui_navigation_does_not_touch_active_admin_state(self):
        self.db.grant('admin', permissions.PERMISSION_MANAGE_SUBJECTS)
        await self.dispatch('add_subject:7:102', user_id=102)
        ctx = self.app.context_types.context.from_update(update(102, self.ctx, text='state'), self.app)
        pending = copy.deepcopy(ctx.admin_data)
        for callback in ('main:stages:102', 'stage:7:102', 'subject:17:102',
                         'content:summaries:17:102', 'back_main:102'):
            await self.dispatch(callback, user_id=102)
            self.assertEqual(ctx.admin_data, pending)
        self.db.grant('admin')
        await self.dispatch(user_id=102, text='مادة غير مصرح بها')
        self.assertFalse(any(name == 'subjects' for name, _, _ in self.db.writes))

    def test_student_keyboards_use_reachable_callbacks_and_consistent_navigation_labels(self):
        registrations = registered_handlers()
        routes = [handler for group, handler in registrations if group == 0 and isinstance(handler, CallbackQueryHandler)]
        keyboards = [main_menu_keyboard(105), subjects_keyboard([], 105, 7),
                     subjects_keyboard([dict(id=i, name=str(i)) for i in range(13)], 105, 7, 1),
                     grades.grades_empty_keyboard(105), schedules.schedule_back_keyboard(105),
                     schedules.schedule_stages_keyboard([], 105), exam_dates.exam_types_keyboard(7, 105),
                     exam_dates.exam_results_keyboard(7, 105), student_settings._stage_keyboard([], 105),
                     content_keyboards.content_keyboard(17, 105, 7),
                     content_keyboards.files_section_keyboard(17, 105),
                     content_keyboards.summaries_section_keyboard(17, 105),
                     content_keyboards.drawings_section_keyboard(17, 105)]
        for keyboard in keyboards:
            for row in keyboard.inline_keyboard:
                for button in row:
                    with self.subTest(data=button.callback_data):
                        self.assertTrue(any(handler.pattern.match(button.callback_data) for handler in routes))
                        if button.callback_data == 'back_main:105':
                            self.assertEqual(button.text, '🏠 القائمة الرئيسية')
                        elif 'رجوع' in button.text:
                            self.assertTrue(button.text.startswith('⬅️ رجوع إلى '))
                        self.assertLessEqual(len(button.callback_data.encode()), 64)


if __name__ == '__main__':
    unittest.main()
