import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image, ImageChops
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMenu

import main


class IdleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        for mocker in (
            patch.object(main, 'NoteStore', return_value=Mock(load_error=None, notes=[])),
            patch.object(main.PetWindow, 'setup_tray', lambda w: setattr(w, 'tray', Mock())),
            patch.object(main.PetWindow, 'offer_startup_permission', lambda w: None),
        ):
            mocker.start()
            self.addCleanup(mocker.stop)
        self.window = main.PetWindow(Mock(startup_permission=False, load_error=None))
        self.window.show()
        self.app.processEvents()
        self.idle = self.window.idle

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_randomized_delay_and_duration(self):
        self.assertTrue(2000 <= self.idle.blink_timer.interval() <= 5000)
        self.idle.start_blink()
        self.assertTrue(self.window.pet.blinking)
        self.assertFalse(self.idle.reopen_timer.isActive())
        QTest.qWait(40)  # Closed-eye frame must paint before its duration starts.
        self.assertTrue(120 <= self.idle.reopen_timer.interval() <= 180)
        with patch('idle_behavior.random.randint', return_value=3456):
            self.idle.finish_blink()
        self.assertFalse(self.window.pet.blinking)
        self.assertEqual(self.idle.blink_timer.interval(), 3456)

    def test_sprite_swap_changes_eyes_without_moving_body_or_hit_area(self):
        w = self.window
        geometry, pet_geometry = w.geometry(), w.pet.geometry()
        opened = w.pet.grab().toImage()
        self.idle.start_blink()
        closed = w.pet.grab().toImage()
        self.assertNotEqual(opened, closed)
        self.assertEqual(w.geometry(), geometry)
        self.assertEqual(w.pet.geometry(), pet_geometry)
        self.idle.finish_blink()
        self.assertEqual(opened, w.pet.grab().toImage())

    def test_real_blink_timer_reopens(self):
        self.idle.start_blink()
        QTest.qWait(230)
        self.assertFalse(self.window.pet.blinking)
        self.assertEqual(self.idle.state, 'waiting')

    def test_modal_pauses_but_controls_and_menus_do_not(self):
        self.window.show_interaction()
        menu = QMenu(self.window)
        menu.show()
        self.idle.refresh()
        self.idle.start_blink()
        self.assertTrue(self.window.pet.blinking)
        menu.hide()
        modal = QDialog(self.window)
        modal.setModal(True)
        modal.show()
        self.app.processEvents()
        self.assertEqual(self.idle.state, 'paused')
        self.assertFalse(self.window.pet.blinking)
        modal.hide()
        with patch('idle_behavior.random.randint', return_value=4321):
            self.app.processEvents()
        self.assertEqual(self.idle.blink_timer.interval(), 4321)

    def test_click_and_drag_are_preserved(self):
        self.idle.start_blink()
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, pos=QPoint(140, 190))
        self.assertTrue(self.window.note_actions.isVisible())
        self.assertEqual(self.window.pet.action_kind, 'wave')
        self.assertEqual(self.window.pet.pixmap().cacheKey(), self.window.pet.wave_frame.cacheKey())
        self.idle.refresh()
        self.assertNotEqual(self.idle.state, 'paused')
        self.window.hide_interaction()
        self.app.processEvents()
        QTest.mousePress(self.window, Qt.MouseButton.LeftButton, pos=QPoint(100, 160))
        QTest.mouseMove(self.window, QPoint(140, 190))
        self.assertTrue(self.window.dragging)
        self.idle.start_blink()
        self.assertFalse(self.window.pet.blinking)
        QTest.mouseRelease(self.window, Qt.MouseButton.LeftButton, pos=QPoint(140, 190))
        self.assertFalse(self.window.bubble.isVisible())
        self.app.processEvents()
        self.assertEqual(self.idle.state, 'waiting')

    def test_greetings_show_during_wave_and_repeated_clicks_replace_message(self):
        for greeting in main.GREETINGS:
            with patch('main.random.choice', return_value=greeting):
                QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, pos=QPoint(140, 190))
            self.assertEqual(self.idle.state, 'waving')
            self.assertEqual(self.window.bubble.text(), greeting)
            self.assertTrue(self.window.bubble.isVisible())
            self.assertTrue(self.window.note_actions.isVisible())
            self.idle.finish_wave()
            self.assertEqual(self.window.bubble.text(), greeting)
            self.assertTrue(self.window.bubble.isVisible())
            self.assertTrue(self.window.note_actions.isVisible())
            self.assertTrue(self.window.bubble_timer.isActive())
        with patch('main.random.choice', side_effect=main.GREETINGS):
            QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, pos=QPoint(140, 190))
            QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, pos=QPoint(140, 190))
        self.assertTrue(self.window.bubble.isVisible())
        self.assertEqual(self.idle.state, 'waving')
        self.assertEqual(self.window.bubble.text(), main.GREETINGS[1])
        self.idle.finish_wave()
        self.assertEqual(self.window.bubble.text(), main.GREETINGS[1])
        self.assertTrue(self.window.bubble_timer.isActive())

    def test_drag_hides_greeting(self):
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, pos=QPoint(140, 190))
        QTest.mousePress(self.window, Qt.MouseButton.LeftButton, pos=QPoint(100, 160))
        QTest.mouseMove(self.window, QPoint(140, 190))
        QTest.mouseRelease(self.window, Qt.MouseButton.LeftButton, pos=QPoint(140, 190))
        self.app.processEvents()
        self.idle.finish_wave()  # Simulate stale completion delivery.
        self.assertFalse(self.window.bubble.isVisible())
        self.assertFalse(self.window.note_actions.isVisible())

    def test_hide_and_quit_stop_blinking(self):
        self.idle.start_blink()
        self.window.hide()
        self.app.processEvents()
        self.assertFalse(self.window.pet.blinking)
        self.assertEqual(self.idle.state, 'paused')
        self.window.show()
        self.app.processEvents()
        self.assertEqual(self.idle.state, 'waiting')
        self.window.stop_background_work()
        self.idle.refresh()
        self.assertEqual(self.idle.state, 'stopped')
        for timer in (self.idle.guard, self.idle.blink_timer, self.idle.reopen_timer,
                      self.idle.wave_timer, self.idle.presentation_timer):
            self.assertFalse(timer.isActive())

    def test_wave_owns_frame_repeated_click_restarts_and_resumes_blink(self):
        self.idle.start_wave()
        QTest.qWait(100)
        self.assertEqual(self.idle.state, 'waving')
        self.assertTrue(self.idle.wave_timer.isActive())
        first_revision = self.window.pet.frame_revision
        self.idle.start_blink()  # Simulate an already queued blink timeout.
        self.idle.finish_blink()
        self.assertEqual(self.window.pet.frame_name, 'wave')
        self.idle.start_wave()
        QTest.qWait(50)
        self.assertGreater(self.window.pet.frame_revision, first_revision)
        self.assertGreater(self.idle.wave_timer.remainingTime(), 850)
        self.assertFalse(self.idle.blink_timer.isActive())
        QTest.qWait(1000)
        self.assertEqual(self.window.pet.frame_name, 'open')
        self.assertTrue(self.idle.blink_timer.isActive())
        self.assertTrue(2000 <= self.idle.blink_timer.interval() <= 5000)

    def test_reminder_and_modal_override_wave(self):
        self.idle.start_wave()
        self.window.set_reminder_appearance(True)
        self.assertEqual(self.window.pet.frame_name, 'open')
        self.assertFalse(self.idle.wave_timer.isActive())
        self.assertEqual(self.window.pet.action_kind, 'alert')
        self.idle.start_wave()
        self.assertNotEqual(self.idle.state, 'waving')
        self.window.set_reminder_appearance(False)
        self.app.processEvents()
        self.idle.start_wave()
        modal = QDialog(self.window)
        modal.setModal(True)
        modal.show()
        self.app.processEvents()
        self.assertEqual(self.window.pet.frame_name, 'open')
        self.assertEqual(self.idle.state, 'paused')
        modal.hide()
        self.app.processEvents()
        self.assertTrue(self.idle.blink_timer.isActive())

    def test_stale_paint_cannot_finish_new_wave(self):
        self.idle.start_blink()
        old_revision = self.window.pet.frame_revision
        self.idle.start_wave()
        self.idle.frame_presented('blink', old_revision)
        self.assertFalse(self.idle.reopen_timer.isActive())
        self.assertEqual(self.window.pet.frame_name, 'wave')

    def test_missing_wave_visible_fallback_finishes(self):
        self.window.pet.wave_frame = None
        self.idle.start_wave()
        self.assertFalse(self.window.pet.pixmap().isNull())
        QTest.qWait(1100)
        self.assertEqual(self.window.pet.frame_name, 'open')
        self.assertTrue(self.idle.blink_timer.isActive())

    def test_wave_assets_are_transparent_and_matching_size(self):
        assets = Path(main.__file__).parent / 'assets'
        for size in (1024, 256):
            with Image.open(assets / f'superdpet_standing_wave_{size}.png') as image:
                self.assertEqual(image.size, (size, size))
                self.assertEqual(image.mode, 'RGBA')
                self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_right_click_keeps_menu_and_does_not_wave(self):
        QTest.mouseClick(self.window, Qt.MouseButton.RightButton, pos=QPoint(140, 190))
        self.assertTrue(self.window.settings_menu.isVisible())
        self.assertNotEqual(self.idle.state, 'waving')
        self.window.settings_menu.hide()

    def test_quit_during_wave_stops_all_actions(self):
        self.idle.start_wave()
        QTest.qWait(50)
        self.window.stop_background_work()
        QTest.qWait(250)
        self.assertEqual(self.idle.state, 'stopped')
        for timer in (self.idle.wave_timer, self.idle.presentation_timer,
                      self.idle.blink_timer, self.idle.reopen_timer, self.idle.guard):
            self.assertFalse(timer.isActive())
        self.assertIsNone(self.window.pet.action_kind)

    def test_missing_blink_keeps_open_frame(self):
        self.idle.pause()
        self.window.pet.set_frames(self.window.pet.open_frame, QPixmap())
        self.idle.refresh()
        self.assertFalse(self.idle.blink_timer.isActive())
        self.idle.start_blink()
        self.assertFalse(self.window.pet.blinking)

    def test_reminder_glow_survives_pausing(self):
        self.idle.start_blink()
        self.window.set_reminder_appearance(True)
        self.window.reminder_dialog.show()
        self.assertFalse(self.window.pet.blinking)
        self.assertTrue(self.window.reminder_glow.isEnabled())
        self.window.reminder_dialog.reject()
        self.assertTrue(self.window.reminder_glow.isEnabled())
        self.assertEqual(self.window.reminder_glow.color().name(), '#8ca9e8')

    def test_tray_notice_never_blocks_blinks(self):
        self.window.explain_missing_tray()
        self.app.processEvents()
        self.assertFalse(self.window.tray_notice.isModal())
        self.idle.start_blink()
        self.assertTrue(self.window.pet.blinking)
        self.window.tray_notice.accept()
        self.app.processEvents()
        self.idle.finish_blink()
        self.assertTrue(self.idle.blink_timer.isActive())

    def test_missing_native_release_recovers(self):
        self.window.dragging = True
        self.window.system_drag = True
        self.window.press_position = QPoint(100, 100)
        self.idle.pause()
        with patch.object(self.window, 'drag_activity') as clock:
            clock.elapsed.return_value = 800
            self.idle.refresh()
        self.assertFalse(self.window.dragging)
        self.assertFalse(self.window.system_drag)
        self.assertIsNone(self.window.press_position)
        self.assertTrue(self.idle.blink_timer.isActive())

    def test_watchdog_repairs_stopped_timer(self):
        self.idle.blink_timer.stop()
        self.idle.refresh()
        self.assertTrue(self.idle.blink_timer.isActive())

    def test_completion_waits_for_modal_then_celebrates(self):
        modal = QDialog(self.window)
        modal.setModal(True)
        modal.show()
        self.idle.completed()
        self.assertTrue(self.idle.happy_pending)
        modal.hide()
        self.app.processEvents()
        self.assertEqual(self.window.pet.action_kind, 'happy')
        self.window.pet.action_animation.setCurrentTime(900)
        self.assertIsNone(self.window.pet.action_kind)

    def test_assets_preserve_alpha_and_pixels_outside_eyes(self):
        assets = Path(main.__file__).parent / 'assets'
        with Image.open(assets / 'superdpet_standing_1024.png') as original, Image.open(assets / 'superdpet_standing_blink_1024.png') as blink:
            self.assertEqual(blink.size, original.size)
            self.assertEqual(blink.mode, 'RGBA')
            self.assertIsNone(ImageChops.difference(original.getchannel('A'), blink.getchannel('A')).getbbox())
            difference = ImageChops.difference(original.convert('RGB'), blink.convert('RGB'))
            self.assertIsNotNone(difference.getbbox())
            difference.paste((0, 0, 0), (416, 236, 616, 303))
            self.assertIsNone(difference.getbbox())
        with Image.open(assets / 'superdpet_standing_blink_256.png') as small:
            self.assertEqual(small.size, (256, 256))
            self.assertEqual(small.mode, 'RGBA')


if __name__ == '__main__':
    unittest.main()
