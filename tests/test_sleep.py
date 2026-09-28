import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMenu

import main
from preferences import Preferences
from storage import NoteStore
from sleep_behavior import PetState


class SleepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = NoteStore(Path(self.temp.name) / 'notes.json')
        prefs = Preferences(Path(self.temp.name) / 'preferences.json')
        with patch.object(main, 'NoteStore', return_value=self.store), \
                patch.object(main.PetWindow, 'setup_tray', lambda w: setattr(w, 'tray', Mock())), \
                patch.object(main.PetWindow, 'offer_startup_permission', lambda w: None), \
                patch.dict(os.environ, SUPERDPET_DEV_MODE='0'):
            self.w = main.PetWindow(prefs)

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def show(self):
        self.w.show()
        self.app.processEvents()

    def sleep(self):
        self.w.sleep.enter_sleep()
        self.assertEqual(self.w.sleep.state, PetState.SLEEPING)

    def test_real_30_second_deadline_starts_only_after_show(self):
        self.assertFalse(self.w.sleep.timer.isActive())
        self.show()
        self.assertEqual(self.w.sleep.timer.interval(), 30_000)
        QTest.qWait(29_000)
        self.assertFalse(self.w.sleep.sleeping)
        QTest.qWait(1200)
        self.assertTrue(self.w.sleep.sleeping)

    def test_click_wakes_waves_and_restores_each_pose(self):
        self.show()
        for pose in ('standing', 'sitting'):
            if self.w.pose != pose:
                self.w.toggle_pose()
            self.sleep()
            QTest.mouseClick(self.w, Qt.MouseButton.LeftButton, pos=QPoint(140, 190))
            self.assertEqual(self.w.sleep.state, PetState.WAVING)
            self.assertEqual(self.w.pet.pixmap().cacheKey(), self.w.pose_frames[pose][2].cacheKey())
            self.w.idle.finish_wave()
            self.assertEqual(self.w.sleep.state, self.w.sleep.resting_state())
            self.assertEqual(self.w.pose, pose)
            self.assertTrue(self.w.idle.blink_timer.isActive())
            self.assertGreater(self.w.sleep.timer.remainingTime(), 29_000)

    def test_menu_sleep_waits_for_close_and_preserves_blockers(self):
        self.show()
        for pose in ('standing', 'sitting'):
            if self.w.pose != pose:
                self.w.toggle_pose()
            QTest.mouseClick(self.w, Qt.MouseButton.RightButton, pos=QPoint(140, 190))
            self.app.processEvents()
            self.assertTrue(self.w.settings_menu.isVisible())
            self.assertEqual(self.w.sleep_action.text(), 'Sleep')
            QTest.mouseClick(self.w.settings_menu, Qt.MouseButton.LeftButton,
                             pos=self.w.settings_menu.actionGeometry(self.w.sleep_action).center())
            self.app.processEvents()
            self.assertFalse(self.w.settings_menu.isVisible())
            self.assertTrue(self.w.sleep.sleeping)
            self.assertEqual(self.w.pose, pose)
            self.w.sleep.activity()
        self.w.set_reminder_appearance(True)
        self.w.sleep_action.trigger()
        self.app.processEvents()
        self.assertEqual(self.w.sleep.state, PetState.REMINDER)

    def test_animation_and_stale_callbacks(self):
        self.show()
        self.sleep()
        pet = self.w.pet
        geometry = pet.geometry()
        self.assertEqual(pet.frame_name, 'sleep')
        self.assertEqual(pet.action_animation.duration(), 3600)
        self.assertFalse(self.w.idle.blink_timer.isActive())
        pet.action_animation.setCurrentTime(0)
        first = pet.grab().toImage()
        pet.action_animation.setCurrentTime(1800)
        self.assertNotEqual(first, pet.grab().toImage())
        self.assertEqual(pet.geometry(), geometry)
        self.w.idle.start_blink()
        self.w.idle.finish_blink()
        self.w.idle.finish_wave()
        self.w.idle.presentation_expired()
        self.w.idle.refresh()
        self.assertEqual(pet.frame_name, 'sleep')
        self.assertEqual(pet.action_kind, 'sleep')

    def test_drag_and_right_click(self):
        self.show()
        self.sleep()
        QTest.mousePress(self.w, Qt.MouseButton.LeftButton, pos=QPoint(100, 160))
        self.assertTrue(self.w.sleep.sleeping)
        self.w.idle.refresh()
        self.assertTrue(self.w.sleep.sleeping)
        position = self.w.pos()
        QTest.mouseMove(self.w, QPoint(150, 200))
        self.assertTrue(self.w.dragging)
        self.assertNotEqual(self.w.pos(), position)
        self.w.idle.refresh()
        self.assertTrue(self.w.sleep.sleeping)
        self.assertEqual(self.w.pet.action_kind, 'sleep')
        self.assertEqual(self.w.pet.frame_name, 'sleep')
        QTest.mouseRelease(self.w, Qt.MouseButton.LeftButton, pos=QPoint(150, 200))
        self.assertFalse(self.w.bubble.isVisible())
        self.assertTrue(self.w.sleep.sleeping)
        self.assertFalse(self.w.sleep.timer.isActive())
        QTest.mouseClick(self.w, Qt.MouseButton.RightButton, pos=QPoint(140, 190))
        self.assertFalse(self.w.sleep.sleeping)
        self.assertTrue(self.w.settings_menu.isVisible())
        self.assertFalse(self.w.sleep.timer.isActive())
        self.w.settings_menu.hide()
        self.app.processEvents()
        self.assertGreater(self.w.sleep.timer.remainingTime(), 29_000)

    def test_sleeping_drag_through_sprite_and_native_state_event(self):
        self.show()
        self.sleep()
        QTest.mousePress(self.w.pet, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
        self.assertTrue(self.w.sleep.sleeping)
        QTest.mouseMove(self.w, QPoint(170, 220))
        self.assertTrue(self.w.dragging)
        QApplication.sendEvent(self.w, QEvent(QEvent.Type.WindowStateChange))
        self.app.processEvents()
        self.assertTrue(self.w.sleep.sleeping)
        QTest.mouseRelease(self.w, Qt.MouseButton.LeftButton, pos=QPoint(170, 220))
        self.assertTrue(self.w.sleep.sleeping)
        self.assertEqual(self.w.pet.action_kind, 'sleep')
        QTest.mouseClick(self.w, Qt.MouseButton.LeftButton, pos=QPoint(140, 190))
        self.assertEqual(self.w.sleep.state, PetState.WAVING)

    def test_dialogs_menus_developer_and_hidden_prevent_sleep(self):
        self.show()
        for widget in (QDialog(self.w), QMenu(self.w)):
            self.sleep()
            widget.show()
            self.app.processEvents()
            self.assertFalse(self.w.sleep.sleeping)
            self.w.sleep.enter_sleep()
            self.assertFalse(self.w.sleep.sleeping)
            self.assertFalse(self.w.sleep.timer.isActive())
            widget.hide()
            self.app.processEvents()
            self.assertGreater(self.w.sleep.timer.remainingTime(), 29_000)
        self.w.dev_mode = True
        self.w.sleep.enter_sleep()
        self.assertFalse(self.w.sleep.sleeping)
        self.w.dev_mode = False
        self.w.hide()
        self.app.processEvents()
        self.w.sleep.enter_sleep()
        self.assertFalse(self.w.sleep.sleeping)
        self.show()
        self.assertGreater(self.w.sleep.timer.remainingTime(), 29_000)

    def test_actual_note_and_settings_dialogs_wake(self):
        self.show()
        for open_dialog in (self.w.add_note, self.w.view_notes, self.w.show_settings):
            self.sleep()
            observed = []
            def inspect_and_close():
                observed.append((self.w.sleep.sleeping, self.w.sleep.timer.isActive()))
                QApplication.activeModalWidget().reject()
            QTimer.singleShot(25, inspect_and_close)
            open_dialog()
            self.app.processEvents()
            self.assertEqual(observed, [(False, False)])
            self.assertGreater(self.w.sleep.timer.remainingTime(), 29_000)

    def test_due_reminder_wakes_and_dismissal_rearms(self):
        self.show()
        self.store.add('Wake up', datetime.now(timezone.utc) + timedelta(seconds=30), 1)
        self.sleep()
        self.w.check_reminders()
        self.assertEqual(self.w.sleep.state, PetState.REMINDER)
        self.assertEqual(self.w.pet.action_kind, 'alert')
        self.assertTrue(self.w.reminder_dialog.isVisible())
        self.assertFalse(self.w.sleep.timer.isActive())
        self.w.reminder_dialog.reject()
        self.app.processEvents()
        self.assertEqual(self.w.sleep.state, PetState.IDLE)
        self.assertGreater(self.w.sleep.timer.remainingTime(), 29_000)
        self.assertTrue(self.w.idle.blink_timer.isActive())

    def test_hover_does_not_reset_deadline_and_shutdown_stops(self):
        self.show()
        self.w.sleep.timer.start(1000)
        QTest.qWait(40)
        QTest.mouseMove(self.w, QPoint(140, 180))
        self.assertLess(self.w.sleep.timer.remainingTime(), 1000)
        self.sleep()
        QTest.mouseMove(self.w, QPoint(145, 185))
        self.assertTrue(self.w.sleep.sleeping)
        self.w.stop_background_work()
        self.assertFalse(self.w.sleep.timer.isActive())
        self.assertFalse(self.w.idle.guard.isActive())
        self.assertIsNone(self.w.pet.action_kind)

    def test_assets_are_transparent_square_and_grounded(self):
        for size in (1024, 256):
            with Image.open(Path(main.__file__).parent / 'assets' / f'superdpet_sleeping_{size}.png') as im:
                self.assertEqual(im.size, (size, size))
                self.assertEqual(im.mode, 'RGBA')
                self.assertEqual(im.getpixel((0, 0))[3], 0)
                bounds = im.getchannel('A').point(lambda a: 255 if a > 128 else 0).getbbox()
                self.assertLess(abs(bounds[3] / size - 978 / 1024), .01)


if __name__ == '__main__':
    unittest.main()
