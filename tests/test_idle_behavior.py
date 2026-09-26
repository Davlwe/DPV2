import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from PySide6.QtCore import QAbstractAnimation, QPoint, QRect, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMenu

import main
from idle_behavior import IDLE, IdleController


class IdleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        for mocker in (
            patch.object(main, "NoteStore", return_value=Mock(load_error=None, notes=[])),
            patch.object(main.PetWindow, "setup_tray", lambda w: setattr(w, "tray", Mock())),
            patch.object(main.PetWindow, "offer_startup_permission", lambda w: None),
        ):
            mocker.start()
            self.addCleanup(mocker.stop)
        self.window = main.PetWindow(Mock(startup_permission=False, load_error=None))
        self.window.show()
        self.app.processEvents()
        self.idle = self.window.idle
        self.idle.settings = replace(IDLE, wander_chance=1.0)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def start_walk(self):
        self.idle.wander_timer.stop()
        with patch.object(QApplication, "platformName", return_value="offscreen"), patch(
            "idle_behavior.random.randint", return_value=90
        ):
            self.idle.try_wander()
        self.assertEqual(self.idle.state, "wandering")

    def test_negative_monitor_bounds_and_small_screen(self):
        area = QRect(-1920, -200, 1920, 1080)
        size = QSize(288, 400)
        for point in (QPoint(-9999, -9999), QPoint(9999, 9999), QPoint(-800, 0)):
            result = IdleController.bounded_position(point, area, size)
            self.assertTrue(area.contains(QRect(result, size)))
        self.assertIsNone(IdleController.bounded_position(QPoint(), QRect(0, 0, 100, 100), size))

    def test_walk_is_bounded_and_does_not_activate_window(self):
        with patch.object(self.window, "activateWindow") as activate, patch.object(self.window, "raise_") as raise_window:
            self.start_walk()
            self.idle.travel.setCurrentTime(IDLE.wander_ms // 2)
            self.assertTrue(self.window.screen().availableGeometry().contains(self.window.geometry()))
            self.idle.travel.setCurrentTime(IDLE.wander_ms)
            self.assertEqual(self.idle.state, "waiting")
            self.assertTrue(self.idle.wander_timer.isActive())
            activate.assert_not_called()
            raise_window.assert_not_called()

    def test_press_stops_walk_before_drag_origin_and_click_still_opens_controls(self):
        self.start_walk()
        QTest.mousePress(self.window, Qt.MouseButton.LeftButton, pos=QPoint(144, 180))
        self.assertEqual(self.idle.state, "paused")
        origin = QPoint(self.window.window_start)
        self.idle.travel.setCurrentTime(IDLE.wander_ms // 2)
        self.assertEqual(self.window.pos(), origin)
        QTest.mouseRelease(self.window, Qt.MouseButton.LeftButton, pos=QPoint(144, 180))
        self.assertTrue(self.window.note_actions.isVisible())
        self.idle.refresh()
        self.assertEqual(self.idle.state, "paused")
        self.window.hide_interaction()
        self.app.processEvents()
        self.assertEqual(self.idle.state, "waiting")
        self.assertGreaterEqual(self.idle.wander_timer.interval(), 15000)
        self.assertLessEqual(self.idle.wander_timer.interval(), 30000)

    def test_dialogs_and_menus_stop_walk_synchronously(self):
        for widget in (QDialog(self.window), QMenu(self.window), self.window.reminder_dialog):
            self.start_walk()
            widget.show()
            self.assertEqual(self.idle.state, "paused")
            self.assertFalse(self.idle.wander_timer.isActive())
            self.idle.refresh()
            self.assertEqual(self.idle.state, "paused")
            widget.hide()
            self.app.processEvents()
            self.assertEqual(self.idle.state, "waiting")

    def test_drag_does_not_open_short_click_controls(self):
        self.start_walk()
        QTest.mousePress(self.window, Qt.MouseButton.LeftButton, pos=QPoint(100, 160))
        QTest.mouseMove(self.window, QPoint(140, 190))
        self.assertTrue(self.window.dragging)
        self.assertEqual(self.idle.state, "paused")
        QTest.mouseRelease(self.window, Qt.MouseButton.LeftButton, pos=QPoint(140, 190))
        self.assertFalse(self.window.bubble.isVisible())
        self.assertFalse(self.window.dragging)
        self.app.processEvents()
        self.assertEqual(self.idle.state, "waiting")

    def test_hidden_and_dragging_pause_and_quit_stops_everything(self):
        self.start_walk()
        self.window.dragging = True
        self.idle.move_step(QPoint(500, 500))
        self.assertEqual(self.idle.state, "paused")
        self.window.dragging = False
        self.window.hide()
        self.app.processEvents()
        self.assertEqual(self.idle.state, "paused")
        self.assertEqual(self.idle.bob.state(), QAbstractAnimation.State.Paused)
        self.window.show()
        self.app.processEvents()
        self.window.stop_background_work()
        self.idle.refresh()
        self.assertEqual(self.idle.state, "stopped")
        for timer in (self.idle.guard, self.idle.wander_timer, self.idle.pulse_timer):
            self.assertFalse(timer.isActive())
        for animation in (self.idle.bob, self.idle.breath, self.idle.pulse, self.idle.travel):
            self.assertEqual(animation.state(), QAbstractAnimation.State.Stopped)

    def test_breath_pulse_and_reminder_restore(self):
        self.idle.breath.setCurrentTime(IDLE.breath_ms // 2)
        self.assertAlmostEqual(self.window.pet.breath, IDLE.breath_scale)
        self.idle.start_pulse()
        self.idle.pulse.setCurrentTime(IDLE.pulse_ms // 2)
        self.assertGreater(self.window.pet.halo, 0.9)
        self.window.set_reminder_appearance(True)
        self.window.reminder_dialog.show()
        self.assertEqual(self.window.pet.halo, 0)
        self.assertTrue(self.window.reminder_glow.isEnabled())
        self.window.reminder_dialog.reject()
        self.assertFalse(self.window.reminder_glow.isEnabled())
        self.assertEqual(self.window.idle_animation.duration(), IDLE.bob_ms)
        self.window.grab()  # Exercise custom painting with the actual sprite.

    def test_wayland_keeps_visuals_without_roaming(self):
        with patch.object(QApplication, "platformName", return_value="wayland"):
            self.idle.try_wander()
        self.assertEqual(self.idle.state, "waiting")
        self.assertEqual(self.idle.breath.state(), QAbstractAnimation.State.Running)


if __name__ == "__main__":
    unittest.main()
