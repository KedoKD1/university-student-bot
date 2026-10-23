"""Parent availability checks through existing student callbacks, offline."""
import unittest
from unittest.mock import AsyncMock, patch

from tests.admin_support import Database, Query, context, update
from bot.handlers import content, grades, search, subjects


class SearchQuery(Query):
    def or_(self, expression):
        # These tests exercise parent filtering, not PostgREST grammar.
        self.filters.append(lambda row: 'synthetic' in (row.get('name') or '').lower())
        return self


class SearchDatabase(Database):
    def table(self, name):
        return SearchQuery(self, name)


class ParentAvailabilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = SearchDatabase()
        self.db.rows['subjects'][0]['name'] = 'Synthetic subject'
        self.ctx = context()
        for name in ('send_document', 'send_photo', 'send_video', 'send_audio', 'send_media_group'):
            setattr(self.ctx.bot, name, AsyncMock())
        for module in (content, grades, search, subjects):
            replacement = patch.object(module, 'supabase', self.db)
            replacement.start()
            self.addCleanup(replacement.stop)
        for table in ('files', 'summaries', 'drawings', 'grade_files'):
            self.add_content(table)

    def add_content(self, table, total=1):
        self.db.rows[table] = [dict(id=index + 1, subject_id=17, stage_id=7,
                                   name=f'Synthetic {table} {index}', description=None,
                                   section_type='theoretical', telegram_file_id=f'offline_{index}',
                                   file_type='document', is_active=True, deleted_at=None, sort_order=index)
                               for index in range(total)]

    def callbacks(self):
        return [
            (content.file_button, 'file:1:105'),
            (content.study_item_button, 'study_item:summaries:1:17:105'),
            (content.study_item_button, 'study_item:drawings:1:17:105'),
            (content.show_files, 'content:files:all:17:105'),
            (content.show_all_summaries, 'content:summaries:all:17:105'),
            (content.show_all_drawings, 'content:drawings:all:17:105'),
            (content.show_files, 'content:files:17:105'),
            (content.show_file_section, 'files_section:theoretical:17:105'),
            (content.show_summaries_or_drawings, 'content:summaries:17:105'),
            (content.show_summaries_or_drawings, 'content:drawings:17:105'),
            (content.show_summary_section, 'summaries_section:theoretical:17:105'),
            (content.show_drawings, 'content:drawings:17:105'),
            (content.back_to_content, 'back_content:17:105'),
            (subjects.subject_button, 'subject:17:105'),
        ]

    def assert_no_media(self):
        for name in ('send_document', 'send_photo', 'send_video', 'send_audio', 'send_media_group'):
            getattr(self.ctx.bot, name).assert_not_awaited()

    async def assert_blocked(self, callbacks=None):
        for handler, callback in callbacks or self.callbacks():
            with self.subTest(callback=callback):
                self.ctx.bot.edit_message_text.reset_mock()
                await handler(update(105, self.ctx, data=callback), self.ctx)
                self.assert_no_media()
                text = self.ctx.bot.edit_message_text.await_args.kwargs['text']
                self.assertNotIn('Synthetic', text)
                self.assertNotIn('internal database detail', text)
                self.assertTrue(self.ctx.bot.edit_message_text.await_args.kwargs['reply_markup'])

    async def test_old_callbacks_with_disabled_subject_fail_closed(self):
        self.db.rows['subjects'][0]['is_active'] = False
        await self.assert_blocked()

    async def test_old_callbacks_with_disabled_stage_fail_closed(self):
        self.db.rows['stages'][0]['is_active'] = False
        await self.assert_blocked()

    async def test_missing_subject_or_stage_fails_closed(self):
        for table in ('subjects', 'stages'):
            with self.subTest(missing=table):
                original = self.db.rows[table]
                self.db.rows[table] = []
                await self.assert_blocked()
                self.db.rows[table] = original

    async def test_parent_database_errors_fail_closed_without_sensitive_details(self):
        for table in ('subjects', 'stages'):
            with self.subTest(failing=table):
                self.db.failure = (table, 'select')
                await self.assert_blocked()

    async def test_active_content_still_delivers_all_individual_and_bulk_types(self):
        for handler, callback in self.callbacks()[:6]:
            await handler(update(105, self.ctx, data=callback), self.ctx)
        self.assertEqual(self.ctx.bot.send_document.await_count, 3)
        self.assertEqual(self.ctx.bot.send_media_group.await_count, 3)

    async def test_inactive_deleted_or_orphaned_children_are_still_rejected(self):
        for field, value in (('is_active', False), ('deleted_at', 'synthetic-deletion'), ('subject_id', None)):
            for table, callback in [('files', 'file:1:105'),
                                    ('summaries', 'study_item:summaries:1:17:105'),
                                    ('drawings', 'study_item:drawings:1:17:105')]:
                self.add_content(table)
                self.db.rows[table][0][field] = value
                handler = content.file_button if table == 'files' else content.study_item_button
                await handler(update(105, self.ctx, data=callback), self.ctx)
                self.assert_no_media()

    async def test_foreign_callbacks_do_not_read_parents_or_children(self):
        for handler, callback in self.callbacks():
            await handler(update(106, self.ctx, data=callback), self.ctx)
        self.assertEqual(self.db.reads, [])
        self.assert_no_media()

    async def test_grade_individual_bulk_and_list_reject_disabled_missing_or_failed_stage(self):
        for condition in ('disabled', 'missing', 'error'):
            self.db.rows['stages'] = [dict(id=7, stage_number=1, is_active=condition != 'disabled')]
            if condition == 'missing':
                self.db.rows['stages'] = []
            self.db.failure = ('stages', 'select') if condition == 'error' else None
            for callback in ('main:grade_file:1:7:105', 'main:grades_all:7:105', 'main:grades_stage:7:105'):
                with self.subTest(condition=condition, callback=callback):
                    await grades.grades_callback(update(105, self.ctx, data=callback), self.ctx)
                    self.assert_no_media()

    async def test_active_grade_individual_and_bulk_keep_child_filters(self):
        self.add_content('grade_files', 3)
        self.db.rows['grade_files'][1]['is_active'] = False
        self.db.rows['grade_files'][2]['deleted_at'] = 'synthetic-deletion'
        for callback in ('main:grade_file:1:7:105', 'main:grades_all:7:105'):
            await grades.grades_callback(update(105, self.ctx, data=callback), self.ctx)
        self.assertEqual(self.ctx.bot.send_document.await_count, 2)

    async def search_results(self):
        self.ctx.user_data.update(search_mode=True, search_owner_id=105)
        await search.handle_search_text(update(105, self.ctx, text='Synthetic'), self.ctx)
        rendered = self.ctx.bot.send_message.await_args.kwargs
        return [b.callback_data for row in rendered['reply_markup'].inline_keyboard for b in row]

    async def test_search_hides_results_with_disabled_subject(self):
        self.db.rows['subjects'][0]['is_active'] = False
        buttons = await self.search_results()
        self.assertFalse(any(b.startswith(('file:', 'study_item:', 'subject:')) for b in buttons))

    async def test_search_hides_subject_and_children_with_disabled_or_missing_stage(self):
        for rows in ([], [dict(id=7, is_active=False)]):
            self.db.rows['stages'] = rows
            buttons = await self.search_results()
            self.assertFalse(any(b.startswith(('file:', 'study_item:', 'subject:')) for b in buttons))

    async def test_search_fails_closed_if_parent_lookup_fails(self):
        self.db.failure = ('stages', 'select')
        buttons = await self.search_results()
        self.assertFalse(any(b.startswith(('file:', 'study_item:', 'subject:')) for b in buttons))

    async def test_search_active_results_keep_original_callbacks_with_batched_parent_reads(self):
        buttons = await self.search_results()
        self.assertIn('subject:17:105', buttons)
        self.assertIn('file:1:105', buttons)
        self.assertIn('study_item:summaries:1:17:105', buttons)
        self.assertIn('study_item:drawings:1:17:105', buttons)
        self.assertLessEqual(self.db.reads.count('subjects'), 2)
        self.assertEqual(self.db.reads.count('stages'), 1)

    async def test_bulk_parent_checks_do_not_grow_per_content_item(self):
        self.add_content('files', 25)
        await content.show_files(update(105, self.ctx, data='content:files:all:17:105'), self.ctx)
        self.assertEqual(self.ctx.bot.send_media_group.await_count, 3)
        self.assertLessEqual(self.db.reads.count('subjects'), 4)
        self.assertLessEqual(self.db.reads.count('stages'), 4)

    async def test_bulk_stops_new_albums_when_parent_is_disabled_during_delivery(self):
        self.add_content('files', 25)

        async def disable_after_first_album(**kwargs):
            self.db.rows['subjects'][0]['is_active'] = False

        self.ctx.bot.send_media_group.side_effect = disable_after_first_album
        await content.show_files(update(105, self.ctx, data='content:files:all:17:105'), self.ctx)
        self.assertEqual(self.ctx.bot.send_media_group.await_count, 1)

    async def test_search_mixed_parent_availability_keeps_only_legitimate_results(self):
        self.db.rows['stages'].append(dict(id=8, stage_number=2, is_active=False))
        self.db.rows['subjects'].extend([
            dict(id=18, stage_id=7, name='Synthetic disabled subject', is_active=False),
            dict(id=19, stage_id=8, name='Synthetic hidden stage', is_active=True),
        ])
        self.db.rows['files'].extend([
            dict(self.db.rows['files'][0], id=2, subject_id=18),
            dict(self.db.rows['files'][0], id=3, subject_id=19),
        ])
        buttons = await self.search_results()
        self.assertIn('file:1:105', buttons)
        self.assertNotIn('file:2:105', buttons)
        self.assertNotIn('file:3:105', buttons)
        self.assertNotIn('subject:19:105', buttons)
        self.assertEqual(self.db.reads.count('stages'), 1)

    async def test_album_failure_after_parent_disable_does_not_send_fallback_items(self):
        self.add_content('files', 3)

        async def failed_album(**kwargs):
            self.db.rows['subjects'][0]['is_active'] = False
            raise RuntimeError('Synthetic transport failure')

        self.ctx.bot.send_media_group.side_effect = failed_album
        await content.show_files(update(105, self.ctx, data='content:files:all:17:105'), self.ctx)
        self.ctx.bot.send_document.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
