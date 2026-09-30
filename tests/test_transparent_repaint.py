"""Check removed artwork against a retained alpha surface, not a fresh grab.

These tests exercise Qt painting but cannot certify the macOS compositor.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtGui import QImage, QPainter, QRegion
from PySide6.QtWidgets import QApplication, QWidget

import main
from preferences import Preferences
from storage import NoteStore


class TransparentRepaintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        preferences = Preferences(Path(self.temp.name) / 'preferences.json')
        preferences.startup_permission = False
        with patch.object(main, 'NoteStore', return_value=NoteStore(Path(self.temp.name) / 'notes.json')), \
                patch.object(main.PetWindow, 'setup_tray', lambda w: setattr(w, 'tray', Mock())), \
                patch.dict(os.environ, SUPERDPET_DEV_MODE='0'):
            self.w = main.PetWindow(preferences)
        self.w.show()
        self.app.processEvents()
        # Freeze clocks, while keeping real transitions and rendering intact.
        self.w.idle.guard.stop()
        self.w.idle.blink_timer.stop()
        self.w.mood_timer.stop()
        self.w.reminder_timer.stop()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def surface(self):
        image = QImage(self.w.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        return image

    def render(self, image):
        painter = QPainter(image)
        try:
            # Do not let QWidget.render prefill the target for us. The window
            # must erase obsolete pixels, just as on a retained native surface.
            self.w.render(painter, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
        finally:
            painter.end()

    def assert_matches_clean_frame(self, retained):
        self.render(retained)
        clean = self.surface()
        self.render(clean)
        self.assertEqual(retained, clean, 'Previous frame pixels survived repaint')
        # The fix must keep drawing the current pet, not simply erase it all.
        self.assertTrue(any(clean.pixelColor(x, y).alpha() > 0
                            for x in range(0, clean.width(), 8)
                            for y in range(60, 320, 8)))
        return clean

    def test_greeting_timeout_clears_box_and_controls(self):
        w = self.w
        w.bubble.setText('Wanna add a note or reminder?')
        w.show_interaction()
        retained = self.surface()
        self.render(retained)
        bubble_point = w.bubble.geometry().center()
        self.assertGreater(retained.pixelColor(bubble_point).alpha(), 0)
        # Same path used by the four-second greeting timeout.
        w.bubble_timer.timeout.emit()
        clean = self.assert_matches_clean_frame(retained)
        self.assertEqual(clean.pixelColor(bubble_point).alpha(), 0)
        self.assertFalse(w.note_actions.isVisible())

    def test_pose_sleep_breathing_and_wake_clear_old_silhouettes(self):
        w = self.w
        retained = self.surface()
        self.render(retained)
        for _ in range(2):
            for pose in ('sitting', 'standing'):
                with self.subTest(pose=pose):
                    if w.pose != pose:
                        w.toggle_pose()
                    w.pet.stop_action()
                    w.idle.blink_timer.stop()
                    self.assert_matches_clean_frame(retained)
                    w.sleep.enter_sleep()
                    self.assertTrue(w.sleep.sleeping)
                    w.pet.action_animation.pause()
                    for phase in (0.0, 0.5, 0.9):
                        w.pet.set_action_phase(phase)
                        self.assert_matches_clean_frame(retained)
                    w.sleep.activity()
                    w.idle.blink_timer.stop()
                    self.assert_matches_clean_frame(retained)

    def test_wave_rotation_and_reaction_glows_do_not_accumulate(self):
        w = self.w
        retained = self.surface()
        for glow_enabled in (True, False):
            w.reminder_glow.setEnabled(glow_enabled)
            for action in ('wave', 'happy', 'alert'):
                with self.subTest(glow=glow_enabled, action=action):
                    w.pet.show_frame('wave' if action == 'wave' else 'open')
                    w.pet.play_action(action)
                    w.pet.action_animation.pause()
                    for phase in (0.0, 0.25, 0.5, 0.75, 1.0):
                        w.pet.set_action_phase(phase)
                        self.assert_matches_clean_frame(retained)
                    w.pet.stop_action()
                    w.pet.show_frame('open')
                    self.assert_matches_clean_frame(retained)

    def test_backing_buffer_clears_hidden_greeting_before_fresh_render(self):
        w = self.w
        w.bubble.setText('Transparent backing buffer check')
        w.show_interaction()
        self.app.processEvents()
        device = w.backingStore().paintDevice()
        if not isinstance(device, QImage):
            self.skipTest('Backend does not expose an image backing buffer')
        # Unlike QWidget.render/grab, this observes the buffer after normal
        # update processing, without requesting a fresh rendering of the widget.
        point = w.bubble.geometry().center() * device.devicePixelRatio()
        self.assertGreater(device.pixelColor(point).alpha(), 0)
        w.hide_interaction()
        self.app.processEvents()
        image = w.backingStore().paintDevice().copy()
        self.assertTrue(image.hasAlphaChannel())
        self.assertEqual(image.pixelColor(point).alpha(), 0)
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)


if __name__ == '__main__':
    unittest.main()
