"""Visible pose check with temporary storage; captures go to /tmp, not assets."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import main
from preferences import Preferences
from storage import NoteStore

app = QApplication([])
if app.platformName() in ('offscreen', 'minimal'):
    raise SystemExit('A visible desktop backend is required.')

with tempfile.TemporaryDirectory() as directory:
    preferences = Preferences(Path(directory) / 'preferences.json')
    preferences.startup_permission = False
    with patch.object(main, 'NoteStore', return_value=NoteStore(Path(directory) / 'notes.json')), \
            patch.object(main.PetWindow, 'setup_tray', lambda w: setattr(w, 'tray', Mock())):
        window = main.PetWindow(preferences)
    try:
        window.show()
        QTest.qWait(200)
        for pose in ('standing', 'sitting'):
            if window.pose != pose:
                window.pose_action.trigger()
                QTest.qWait(350)
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(140, 190))
            QTest.qWait(100)
            assert window.pose == pose
            assert window.pet.frame_name == 'wave'
            assert window.pet.pixmap().cacheKey() == window.pose_frames[pose][2].cacheKey()
            window.grab().save(f'/tmp/superdpet-{pose}-wave.png')
            QTest.qWait(1100)
            assert window.pet.frame_name == 'open'
            assert window.pet.pixmap().cacheKey() == window.pose_frames[pose][0].cacheKey()
            assert window.idle.blink_timer.isActive()
            window.grab().save(f'/tmp/superdpet-{pose}-idle.png')
            window.idle.start_blink()
            QTest.qWait(30)
            assert window.pet.pixmap().cacheKey() == window.pose_frames[pose][1].cacheKey()
            window.idle.finish_blink()
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=QPoint(100, 160))
        QTest.mouseMove(window, QPoint(140, 190))
        assert window.dragging
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=QPoint(140, 190))
        QTest.qWait(700)
        assert window.pose == 'sitting'
        assert window.pet.frame_name == 'open'
        assert not window.bubble.isVisible()
        assert Preferences(preferences.path).pose == 'sitting'
        assert window.pose_action.text() == 'Stand up'
        QTest.mouseClick(window, Qt.MouseButton.RightButton, pos=QPoint(140, 190))
        QTest.qWait(50)
        assert window.pose == 'sitting'
        # Keyboard selection of the first right-click menu item also works on Wayland.
        window.settings_menu.setActiveAction(window.pose_action)
        QTest.keyClick(window.settings_menu, Qt.Key.Key_Return)
        QTest.qWait(350)
        assert window.pose == 'standing'
        assert Preferences(preferences.path).pose == 'standing'
        print('PASS native poses: standing/seated wave, idle, blink, seated drag, Stand up menu.')
    finally:
        window.close()
