import ast
import inspect
import itertools
import unittest
import warnings

from telegram.ext import CallbackQueryHandler, ConversationHandler
from telegram.warnings import PTBUserWarning

from tests.admin_support import MODULES, ROOT, permissions, registered_handlers


def callback_examples(value):
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return [value.value]
    if not isinstance(value, ast.JoinedStr):
        return []
    alternatives = []
    for part in value.values:
        if isinstance(part, ast.Constant):
            alternatives.append([part.value])
        else:
            expression = ast.unparse(part.value)
            if expression == "prefix":
                alternatives.append(["add_exam_type", "edit_exam_type"])
            elif expression == "audience_type":
                alternatives.append(["group", "channel"])
            elif expression == "section_type":
                alternatives.append(["theoretical", "practical"])
            elif expression.startswith("SETTING_"):
                alternatives.append([getattr(MODULES["admin_settings"], expression)])
            else:
                alternatives.append(["101"])
    return ["".join(parts) for parts in itertools.product(*alternatives)]


def produced_callbacks():
    for name in MODULES:
        tree = ast.parse((ROOT / "bot" / "handlers" / f"{name}.py").read_text())
        assigned = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned.setdefault(target.id, []).extend(callback_examples(node.value))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "callback_data":
                examples = assigned.get(node.value.id, []) if isinstance(node.value, ast.Name) else callback_examples(node.value)
                for example in examples:
                    yield name, example


class AdminRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", PTBUserWarning)
            cls.registrations = registered_handlers()
        cls.global_callbacks = []
        cls.all_callbacks = []
        cls.conversations = []
        for group, handler in cls.registrations:
            if group != 0:
                continue
            if isinstance(handler, CallbackQueryHandler):
                cls.global_callbacks.append(handler)
                cls.all_callbacks.append(handler)
            elif isinstance(handler, ConversationHandler):
                cls.conversations.append(handler)
                cls.all_callbacks.extend(
                    entry for entry in handler.entry_points + handler.fallbacks
                    if isinstance(entry, CallbackQueryHandler)
                )
                for handlers in handler.states.values():
                    cls.all_callbacks.extend(entry for entry in handlers if isinstance(entry, CallbackQueryHandler))

    def test_all_admin_keyboard_callbacks_have_a_registered_route(self):
        examples = list(produced_callbacks())
        self.assertGreater(len(examples), 180)
        for module, data in examples:
            with self.subTest(module=module, callback=data):
                self.assertTrue(any(handler.pattern.match(data) for handler in self.all_callbacks), data)

    def test_every_admin_button_is_mapped_to_an_existing_permission(self):
        valid = {value for key, value in vars(permissions).items() if key.startswith("PERMISSION_")}
        for module, data in produced_callbacks():
            with self.subTest(module=module, callback=data):
                self.assertIn(permissions.permission_for_callback(data), valid)

    def test_registered_callbacks_accept_the_actual_telegram_signature(self):
        for handler in self.all_callbacks:
            with self.subTest(callback=handler.callback.__name__):
                inspect.signature(handler.callback).bind(object(), object())

    def test_missing_routes_and_grade_helper_are_correctly_integrated(self):
        expected = {
            "admin_drawing_back:101": "admin_drawing_back",
            "admin_drawings_owner:101": "admin_drawings_owner",
            "admin_schedules_back:101": "admin_schedules_back",
            "admin_schedule_back:101": "admin_schedule_back",
            "admin_grades_back:101": "admin_grades_back",
            "admin_grade_list_back:101": "admin_grade_list_back",
            "admin_grade_list:7:101": "admin_grade_list",
            "admin_exam_list:7": "admin_exam_stage",
        }
        for data, name in expected.items():
            matches = [handler for handler in self.global_callbacks if handler.pattern.match(data)]
            self.assertEqual([handler.callback.__name__ for handler in matches], [name])

    def test_global_admin_patterns_do_not_shadow_each_other(self):
        for module, data in produced_callbacks():
            with self.subTest(module=module, callback=data):
                matches = [handler for handler in self.global_callbacks if handler.pattern.match(data)]
                self.assertLessEqual(len(matches), 1, [h.callback.__name__ for h in matches])

    def test_global_permission_guard_precedes_all_conversations(self):
        guards = [group for group, handler in self.registrations
                  if isinstance(handler, CallbackQueryHandler) and handler.callback.__name__ == "permission_guard"]
        self.assertEqual(guards, [-2])
        self.assertTrue(all(conv.per_user and conv.per_chat for conv in self.conversations))


if __name__ == "__main__":
    unittest.main()
