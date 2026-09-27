import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication

import main
from mood import TaskMood, MOOD_COLORS
from storage import NoteStore


class MoodTests(unittest.TestCase):
    def test_counts_due_boundary_completion_and_restart(self):
        now = datetime.now(timezone.utc)
        note = dict(completed=False, due_at=(now + timedelta(seconds=1)).isoformat())
        mood = TaskMood()
        mood.refresh([])
        self.assertEqual(mood.state, 'Calm')
        mood.refresh([note], now)
        self.assertEqual((mood.state, mood.pending, mood.completed, mood.overdue),
                         ('Focused', 1, 0, 0))
        mood.refresh([note], now + timedelta(seconds=1))
        self.assertEqual((mood.state, mood.overdue), ('Concerned', 1))
        finished = dict(note, completed=True)
        mood.refresh([finished], now, completed_task=True)
        self.assertEqual((mood.state, mood.pending, mood.completed, mood.overdue),
                         ('Happy', 0, 1, 0))
        mood.refresh([finished], now)
        self.assertEqual(mood.state, 'Happy')
        restarted = TaskMood()
        restarted.refresh([finished], now)
        self.assertEqual(restarted.state, 'Calm')
        mood.refresh([finished, note], now, completed_task=True)
        self.assertEqual(mood.state, 'Focused')
        mood.refresh([], now)
        self.assertEqual(mood.state, 'Calm')

    def test_store_events_glow_reminder_priority_and_quit(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            store = NoteStore(Path(directory) / 'notes.json')
            with patch.object(main, 'NoteStore', return_value=store), \
                    patch.object(main.PetWindow, 'setup_tray', lambda w: setattr(w, 'tray', Mock())), \
                    patch.object(main.PetWindow, 'offer_startup_permission', lambda w: None):
                window = main.PetWindow(Mock(startup_permission=False, load_error=None))
            try:
                self.assertEqual(window.mood.state, 'Calm')
                store.add('task', datetime.now(timezone.utc) + timedelta(hours=1))
                self.assertEqual(window.mood.state, 'Focused')
                self.assertIn('1 pending', window.toolTip())
                window.set_reminder_appearance(True)
                self.assertEqual(window.reminder_glow.color().name(), '#ffb347')
                store.complete(store.notes[0]['id'])
                window.task_completed()
                self.assertEqual(window.mood.state, 'Happy')
                self.assertEqual(window.reminder_glow.color().name(), '#ffb347')
                window.set_reminder_appearance(False)
                self.assertEqual(window.reminder_glow.color().name(), MOOD_COLORS['Happy'].lower())
                store.delete_completed(store.notes[0]['id'])
                self.assertEqual(window.mood.state, 'Calm')
                # Simulate time crossing a due date without a storage event.
                store.add('due soon', datetime.now(timezone.utc) + timedelta(hours=1))
                store.notes[0]['due_at'] = datetime.now(timezone.utc).isoformat()
                window.mood_timer.timeout.emit()
                self.assertEqual(window.mood.state, 'Concerned')
                self.assertEqual(window.mood.overdue, 1)
            finally:
                window.close()
                self.assertFalse(window.mood_timer.isActive())
                window.deleteLater()
                app.processEvents()
