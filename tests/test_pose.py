import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image, ImageChops
from PySide6.QtCore import QPoint, Qt, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import main
from preferences import Preferences
from storage import NoteStore


class PoseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.prefs = Preferences(Path(self.temp.name) / 'preferences.json')
        self.store = NoteStore(Path(self.temp.name) / 'notes.json')
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            window.close()
            window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def window(self):
        with patch.object(main, 'NoteStore', return_value=self.store), \
                patch.object(main.PetWindow, 'setup_tray', lambda w: setattr(w, 'tray', Mock())), \
                patch.object(main.PetWindow, 'offer_startup_permission', lambda w: None):
            window = main.PetWindow(self.prefs)
        self.windows.append(window)
        window.show()
        self.app.processEvents()
        return window

    def test_toggle_blink_greeting_reminder_and_restore(self):
        w = self.window()
        self.assertEqual(w.pose, 'standing')
        geometry = w.geometry()
        w.pose_action.trigger()
        self.assertEqual(w.pose, 'sitting')
        self.assertEqual(w.pose_action.text(), 'Stand up')
        self.assertNotEqual(w.idle.state, 'waving')
        self.assertEqual(w.geometry(), geometry)
        w.pet.stop_action()
        opened = w.pet.grab().toImage()
        w.idle.start_blink()
        self.assertEqual(w.pet.pixmap().cacheKey(), w.pose_frames['sitting'][1].cacheKey())
        self.assertNotEqual(opened, w.pet.grab().toImage())
        w.idle.finish_blink()
        QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=QPoint(140,190))
        self.assertTrue(w.note_actions.isVisible())
        self.assertEqual(w.idle.state, 'waving')
        self.assertEqual(w.pet.pixmap().cacheKey(), w.pose_frames['sitting'][2].cacheKey())
        self.assertNotEqual(w.pet.pixmap().toImage(), w.pose_frames['standing'][2].toImage())
        self.assertEqual(w.pose, 'sitting')
        self.assertEqual(Preferences(self.prefs.path).pose, 'sitting')
        w.idle.finish_wave()
        self.assertEqual(w.pet.pixmap().cacheKey(), w.pose_frames['sitting'][0].cacheKey())
        self.assertTrue(w.idle.blink_timer.isActive())
        w.idle.start_blink()
        self.assertEqual(w.pet.pixmap().cacheKey(), w.pose_frames['sitting'][1].cacheKey())
        w.idle.finish_blink()
        self.prefs = Preferences(self.prefs.path)
        self.assertEqual(self.window().pose, 'sitting')
        w.set_reminder_appearance(True)
        w.toggle_pose()
        self.assertEqual(w.pose, 'standing')
        self.assertEqual(w.pet.action_kind, 'alert')
        self.assertEqual(w.reminder_glow.color().name(), '#ffb347')
        w.set_reminder_appearance(False)
        self.assertTrue(w.idle.start_wave())
        self.assertEqual(w.pet.frame_name, 'wave')
        w.idle.finish_wave()
        self.assertEqual(w.pet.pixmap().cacheKey(), w.pose_frames['standing'][0].cacheKey())
        w.idle.start_blink()
        self.assertEqual(w.pet.pixmap().cacheKey(), w.pose_frames['standing'][1].cacheKey())

    def test_preferences_preserve_other_settings_and_handle_legacy(self):
        self.prefs.save_pose('sitting')
        self.prefs.save_default_reminder_minutes(10)
        self.prefs.save_startup_permission(False)
        loaded = Preferences(self.prefs.path)
        self.assertEqual((loaded.pose, loaded.default_reminder_minutes, loaded.startup_permission),
                         ('sitting', 10, False))
        self.prefs.path.write_text(json.dumps({'startup_permission': False}))
        self.assertEqual(Preferences(self.prefs.path).pose, 'standing')
        self.prefs.path.write_text(json.dumps({'pose': 'unknown'}))
        self.assertEqual(Preferences(self.prefs.path).pose, 'standing')

    def test_seated_drag_cancels_wave_and_pose_switch_rejects_stale_wave(self):
        w = self.window()
        w.toggle_pose()
        QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=QPoint(140, 190))
        self.assertEqual(w.idle.state, 'waving')
        QTest.mousePress(w, Qt.MouseButton.LeftButton, pos=QPoint(100, 160))
        QTest.mouseMove(w, QPoint(140, 190))
        self.assertTrue(w.dragging)
        QTest.mouseRelease(w, Qt.MouseButton.LeftButton, pos=QPoint(140, 190))
        self.app.processEvents()
        self.assertFalse(w.bubble.isVisible())
        self.assertEqual(w.pose, 'sitting')
        self.assertEqual(w.pet.frame_name, 'open')
        self.assertTrue(w.idle.blink_timer.isActive())
        w.idle.start_wave()
        w.toggle_pose()
        w.idle.finish_wave()
        self.assertEqual(w.pose_action.text(), 'Sit down')
        self.assertEqual(w.pet.pixmap().cacheKey(), w.pose_frames['standing'][0].cacheKey())
        self.assertEqual(Preferences(self.prefs.path).pose, 'standing')

    def test_save_failure_keeps_visible_pose(self):
        w = self.window()
        with patch.object(self.prefs, 'save_pose', side_effect=OSError('disk error')), \
                patch('main.QMessageBox.warning') as warning:
            w.toggle_pose()
        warning.assert_called_once()
        self.assertEqual(w.pose, 'standing')

    def test_asset_canvas_alpha_and_blink_changes_are_local(self):
        assets = Path(main.__file__).parent / 'assets'
        for size in (1024, 256):
            opened = Image.open(assets / f'superdpet_sitting_{size}.png')
            blink = Image.open(assets / f'superdpet_sitting_blink_{size}.png')
            self.assertEqual(opened.size, (size, size))
            self.assertEqual(blink.size, opened.size)
            self.assertEqual(opened.mode, 'RGBA')
            self.assertEqual(blink.mode, 'RGBA')
            self.assertEqual(opened.getchannel('A').tobytes(), blink.getchannel('A').tobytes())
            self.assertEqual(opened.getpixel((0,0))[3], 0)
            box = ImageChops.difference(opened, blink).convert('RGB').getbbox()
            self.assertIsNotNone(box)
            self.assertGreater(box[0], size * .40)
            self.assertLess(box[2], size * .63)
            self.assertGreater(box[1], size * .43)
            self.assertLess(box[3], size * .54)

    def test_seated_wave_assets_are_transparent_and_aligned(self):
        assets = Path(main.__file__).parent / 'assets'
        for size in (1024, 256):
            with Image.open(assets / f'superdpet_sitting_wave_{size}.png') as wave, \
                    Image.open(assets / f'superdpet_sitting_{size}.png') as opened:
                self.assertEqual(wave.size, opened.size)
                self.assertEqual(wave.mode, 'RGBA')
                self.assertEqual(wave.getpixel((0, 0))[3], 0)
                bounds = lambda im: im.getchannel('A').point(lambda a: 255 if a > 128 else 0).getbbox()
                for actual, expected in zip(bounds(wave), bounds(opened)):
                    self.assertLessEqual(abs(actual - expected), max(2, size * .01))
