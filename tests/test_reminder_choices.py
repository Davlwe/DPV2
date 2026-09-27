import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QPushButton

import main
from notes_dialog import AddNoteDialog
from preferences import Preferences
from reminders import pending_reminders
from settings_dialog import SettingsDialog
from storage import NoteStore


class ReminderChoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = NoteStore(self.root / 'notes.json')
        self.prefs = Preferences(self.root / 'preferences.json')
        self.now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)

    def test_each_choice_exact_threshold_completed_and_reminded(self):
        due = self.now + timedelta(minutes=20)
        for minutes in (1, 5, 10):
            self.store.add(f'lead {minutes}', due, minutes)
            note = self.store.notes[-1]
            threshold = due - timedelta(minutes=minutes)
            self.assertEqual(pending_reminders([note], threshold - timedelta(microseconds=1)), [])
            self.assertEqual(pending_reminders([note], threshold), [note])
            self.assertEqual(pending_reminders([dict(note, completed=True)], due), [])
            self.assertEqual(pending_reminders([dict(note, reminded=True)], due), [])
        reloaded = NoteStore(self.store.path)
        self.assertEqual([n['reminder_minutes'] for n in reloaded.notes], [1, 5, 10])

    def test_legacy_migration_does_not_write_until_next_save_or_lose_fields(self):
        legacy = [{'id': 'old', 'text': 'Keep this text', 'due_at': self.now.isoformat(),
                   'completed': True, 'reminded': True}]
        original = json.dumps(legacy)
        self.store.path.write_text(original)
        migrated = NoteStore(self.store.path)
        self.assertIsNone(migrated.load_error)
        self.assertEqual(migrated.notes, [dict(legacy[0], reminder_minutes=5)])
        self.assertEqual(self.store.path.read_text(), original)
        migrated.add('new', self.now, 10)
        self.assertEqual(json.loads(self.store.path.read_text())[0], dict(legacy[0], reminder_minutes=5))

    def test_catchup_once_after_restart(self):
        self.store.add('overdue', self.now - timedelta(hours=1), 1)
        restarted = NoteStore(self.store.path)
        ready = pending_reminders(restarted.notes, self.now)
        self.assertEqual(len(ready), 1)
        restarted.mark_reminded({ready[0]['id']})
        self.assertEqual(pending_reminders(restarted.notes, self.now), [])
        self.assertEqual(pending_reminders(NoteStore(self.store.path).notes, self.now), [])

    def test_invalid_leads_fail_without_overwriting_data(self):
        self.store.add('valid', self.now, 5)
        original = self.store.path.read_bytes()
        for invalid in (0, 30, True, '5', None):
            with self.assertRaises(ValueError):
                self.store.add('invalid', self.now, invalid)
            self.assertEqual(self.store.path.read_bytes(), original)

    def test_default_persists_without_changing_startup_consent(self):
        self.prefs.save_startup_permission(True)
        self.prefs.save_default_reminder_minutes(10)
        reloaded = Preferences(self.prefs.path)
        self.assertEqual(reloaded.default_reminder_minutes, 10)
        self.assertTrue(reloaded.startup_permission)
        reloaded.save_startup_permission(False)
        self.assertEqual(Preferences(self.prefs.path).default_reminder_minutes, 10)

    def test_legacy_preferences_default_and_cancel(self):
        self.prefs.path.write_text('{"startup_permission": false}')
        prefs = Preferences(self.prefs.path)
        self.assertEqual(prefs.default_reminder_minutes, 5)
        dialog = SettingsDialog(prefs, Mock(unsupported_reason='WSL'))
        dialog.reminder_default.setCurrentIndex(dialog.reminder_default.findData(1))
        dialog.reject()
        self.assertEqual(Preferences(self.prefs.path).default_reminder_minutes, 5)

    def test_settings_on_wsl_and_per_note_override(self):
        startup = Mock(unsupported_reason='WSL: startup unsupported')
        dialog = SettingsDialog(self.prefs, startup)
        self.assertFalse(dialog.start_at_login.isEnabled())
        dialog.reminder_default.setCurrentIndex(dialog.reminder_default.findData(10))
        dialog.save()
        startup.set_enabled.assert_not_called()
        prefs = Preferences(self.prefs.path)
        self.assertEqual(prefs.default_reminder_minutes, 10)
        self.assertIsNone(prefs.startup_permission)
        add = AddNoteDialog(self.store, default_reminder_minutes=prefs.default_reminder_minutes)
        self.assertEqual(add.remind_me.currentData(), 10)
        self.assertEqual([add.remind_me.itemText(i) for i in range(3)],
                         ['1 minute before', '5 minutes before', '10 minutes before'])
        add.text_input.setPlainText('Override default')
        add.remind_me.setCurrentIndex(add.remind_me.findData(1))
        add.save_note()
        self.assertEqual(self.store.notes[0]['reminder_minutes'], 1)
        self.assertEqual(Preferences(self.prefs.path).default_reminder_minutes, 10)
        default_form = AddNoteDialog(self.store)
        self.assertEqual(default_form.remind_me.currentData(), 5)

    def test_app_reminds_once_and_quit_is_only_in_menus(self):
        self.prefs.startup_permission = False
        with patch.object(main, 'NoteStore', return_value=self.store), \
                patch.object(main.PetWindow, 'offer_startup_permission', lambda w: None), \
                patch.object(main.PetWindow, 'explain_missing_tray', lambda w: None):
            window = main.PetWindow(self.prefs)
            window.show()
            self.app.processEvents()
            self.assertNotIn('Quit', [b.text() for b in window.findChildren(QPushButton)])
            self.assertIn('Quit', [a.text() for a in window.settings_menu.actions()])
            self.assertIn('Quit', [a.text() for a in window.tray_menu.actions()])
            self.store.add('ready', datetime.now(timezone.utc), 5)
            with patch.object(self.store, 'mark_reminded', wraps=self.store.mark_reminded) as save:
                window.check_reminders()
                window.check_reminders()
                save.assert_called_once()
                self.assertEqual(window.reminder_text.toPlainText().count('ready'), 1)
            window.close()
            self.app.processEvents()
