"""Inspect the real pet renderer with isolated data; see docs/transparency.md."""
import argparse
import ctypes
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import PySide6
from PySide6.QtCore import Qt, QTimer, qVersion
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

import main
from preferences import Preferences
from storage import NoteStore


def cocoa_state(window):
    """Read public AppKit properties, without changing native rendering state.

    Cocoa QWidget.winId() is an NSView*, not an NSWindow*. Only use the
    already-shown top-level widget; making the sprite native changes rendering.
    All selectors below take no arguments and return pointers or BOOLs.
    """
    if sys.platform != 'darwin' or QApplication.platformName() != 'cocoa':
        return None
    objc = ctypes.CDLL('/usr/lib/libobjc.A.dylib')
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    pointer_call = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
        ('objc_msgSend', objc))
    bool_call = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(
        ('objc_msgSend', objc))

    def send(receiver, selector, call=pointer_call):
        if not receiver:
            raise RuntimeError(f'No native receiver for {selector}')
        return call(receiver, objc.sel_registerName(selector.encode('ascii')))

    view = int(window.winId())
    native_window = send(view, 'window')
    return {
        'window_has_shadow': send(native_window, 'hasShadow', bool_call),
        'window_is_opaque': send(native_window, 'isOpaque', bool_call),
        'view_is_opaque': send(view, 'isOpaque', bool_call),
    }


def widget_state(widget):
    return {
        'auto_fill_background': widget.autoFillBackground(),
        'stylesheet': widget.styleSheet(),
        'attributes': {name: widget.testAttribute(getattr(Qt.WidgetAttribute, name))
                       for name in ('WA_TranslucentBackground', 'WA_NoSystemBackground',
                                    'WA_OpaquePaintEvent', 'WA_NativeWindow')},
    }


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=45)
    parser.add_argument('--no-glow', action='store_true', help='isolate the Qt graphics effect')
    parser.add_argument('--native-shadow', action='store_true', help='allow the OS window shadow')
    args = parser.parse_args()
    if args.seconds < 1:
        parser.error('--seconds must be positive')
    app = QApplication([])
    output = Path(tempfile.mkdtemp(prefix='superdpet-transparency-'))

    class DiagnosticWindow(main.PetWindow):
        def apply_task_glow(self):
            super().apply_task_glow()
            if args.no_glow and self.has_sprite:
                self.reminder_glow.setEnabled(False)

    with tempfile.TemporaryDirectory(prefix='superdpet-test-data-') as directory:
        preferences = Preferences(Path(directory) / 'preferences.json')
        preferences.startup_permission = False
        with patch.object(main, 'NoteStore', return_value=NoteStore(Path(directory) / 'notes.json')), \
                patch.object(main.PetWindow, 'setup_tray', lambda w: setattr(w, 'tray', Mock())):
            window = DiagnosticWindow(preferences)
        if args.native_shadow:
            window.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, False)
        window.show()
        app.processEvents()
        revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                  capture_output=True, text=True, check=False).stdout.strip()
        report = {
            'revision': revision, 'checkout': str(ROOT), 'python': sys.version,
            'executable': sys.executable, 'os': platform.platform(),
            'architecture': platform.machine(), 'pyside': PySide6.__version__,
            'qt': qVersion(), 'backend': app.platformName(),
            'options': vars(args),
            'environment': {k: v for k, v in os.environ.items()
                            if k.startswith(('QT_', 'SUPERDPET_'))},
            'sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                       for name in ('main.py', 'idle_behavior.py',
                                    'assets/superdpet_standing_1024.png')},
            'captures': [],
        }
        errors = []

        def capture():
            if window.quitting:
                return
            try:
                index = len(report['captures'])
                record = {
                    'index': index, 'pose': window.pose, 'frame': window.pet.frame_name,
                    'action': window.pet.action_kind, 'phase': window.pet.get_action_phase(),
                    'dpr': window.devicePixelRatioF(),
                    'alpha_buffer_size': window.windowHandle().format().alphaBufferSize(),
                    'no_native_shadow_hint': bool(window.windowFlags()
                                                 & Qt.WindowType.NoDropShadowWindowHint),
                    'window': widget_state(window), 'sprite': widget_state(window.pet),
                    'cocoa': cocoa_state(window),
                    'glow_enabled': window.has_sprite and window.reminder_glow.isEnabled(),
                }
                # Copy BEFORE grab(): grab() triggers fresh painting and can hide
                # stale-pixel bugs. This is a Qt buffer, not a desktop screenshot;
                # on buffered backends it need not be the currently presented buffer.
                device = window.backingStore().paintDevice()
                if isinstance(device, QImage):
                    backing = device.copy()
                    record['backing_has_alpha'] = backing.hasAlphaChannel()
                    record['backing_corner_alpha'] = backing.pixelColor(0, 0).alpha()
                    if not backing.save(str(output / f'{index:03d}-backing.png')):
                        raise RuntimeError('Could not save backing buffer')
                else:
                    record['backing_unavailable'] = type(device).__name__
                if not window.grab().save(str(output / f'{index:03d}-fresh.png')):
                    raise RuntimeError('Could not save fresh render')
                report['captures'].append(record)
                (output / 'report.json').write_text(json.dumps(report, indent=2))
            except Exception as error:
                errors.append(str(error))
                print(f'Diagnostic failed: {error}', file=sys.stderr, flush=True)
                window.close()

        print(f'Output: {output}\nBackend: {app.platformName()}\n'
              'Click to wave; right-click to change pose or sleep; drag as usual.\n'
              'Compare the visible desktop with backing.png and fresh.png.\n'
              'Captures contain only the test pet; notes and preferences use temporary files.',
              flush=True)
        capture_timer = QTimer(window)
        capture_timer.timeout.connect(capture)
        capture_timer.start(2000)
        QTimer.singleShot(250, capture)
        QTimer.singleShot(args.seconds * 1000, window.close)
        try:
            app.exec()
        finally:
            capture_timer.stop()
            window.close()
        return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(run())
