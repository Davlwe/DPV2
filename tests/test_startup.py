"""Run with QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests."""

import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication, QDialogButtonBox

from preferences import Preferences
from settings_dialog import SettingsDialog
from startup import APP_ID, RUN_KEY, StartupRegistration, desktop_argument


class StartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.preferences = Preferences(self.root / "preferences.json")

    def registration(self, system="Linux", release="native"):
        with patch("startup.platform.system", return_value=system), \
                patch("startup.platform.release", return_value=release), \
                patch.dict(os.environ, {"WSL_DISTRO_NAME": "", "WSL_INTEROP": "", "XDG_CONFIG_HOME": str(self.root)}), \
                patch("startup.Path.home", return_value=self.root):
            return StartupRegistration()

    def test_permission_default_decline_and_restart(self):
        self.assertIsNone(self.preferences.startup_permission)
        self.assertFalse(self.preferences.path.exists())
        dialog = SettingsDialog(self.preferences, self.registration(), first_run=True)
        self.assertFalse(dialog.start_at_login.isChecked())
        dialog.reject()
        self.assertIs(Preferences(self.preferences.path).startup_permission, False)
        self.assertFalse(self.registration().entry_path.exists())

    def test_linux_enable_disable_and_settings_restore(self):
        startup = self.registration()
        self.assertFalse(startup.entry_path.exists())
        dialog = SettingsDialog(self.preferences, startup, first_run=True)
        dialog.start_at_login.setChecked(True)
        dialog.save()
        self.assertTrue(startup.is_enabled())
        self.assertTrue(Preferences(self.preferences.path).startup_permission)
        self.assertIn("--startup", startup.entry_path.read_text())
        restored = SettingsDialog(Preferences(self.preferences.path), startup)
        self.assertTrue(restored.start_at_login.isChecked())
        restored.start_at_login.setChecked(False)
        restored.save()
        self.assertFalse(startup.entry_path.exists())
        self.assertIs(Preferences(self.preferences.path).startup_permission, False)

    def test_cancel_does_not_enable(self):
        startup = self.registration()
        dialog = SettingsDialog(self.preferences, startup, first_run=True)
        dialog.start_at_login.setChecked(True)
        dialog.reject()
        self.assertFalse(startup.entry_path.exists())
        self.assertIs(Preferences(self.preferences.path).startup_permission, False)

    def test_corrupt_preferences_preserved(self):
        self.preferences.path.write_text('{broken')
        prefs = Preferences(self.preferences.path)
        startup = self.registration()
        dialog = SettingsDialog(prefs, startup)
        self.assertFalse(dialog.start_at_login.isEnabled())
        with self.assertRaises(OSError):
            prefs.save_startup_permission(True)
        self.assertEqual(self.preferences.path.read_text(), '{broken')
        self.assertFalse(startup.entry_path.exists())

    def test_preferences_save_failure_leaves_os_untouched(self):
        startup = self.registration()
        dialog = SettingsDialog(self.preferences, startup)
        dialog.start_at_login.setChecked(True)
        with patch.object(self.preferences, "save_startup_permission", side_effect=OSError("disk full")), \
                patch("settings_dialog.QMessageBox.warning") as warning:
            dialog.save()
        warning.assert_called_once()
        self.assertFalse(startup.entry_path.exists())
        self.assertIsNone(self.preferences.startup_permission)

    def test_registration_failure_is_not_reported_as_enabled(self):
        startup = self.registration()
        dialog = SettingsDialog(self.preferences, startup)
        dialog.start_at_login.setChecked(True)
        with patch.object(startup, "set_enabled", side_effect=OSError("access denied")), \
                patch("settings_dialog.QMessageBox.warning") as warning:
            dialog.save()
        warning.assert_called_once()
        self.assertFalse(dialog.start_at_login.isChecked())
        self.assertFalse(startup.entry_path.exists())

    def test_failed_removal_still_revokes_permission(self):
        startup = self.registration()
        startup.set_enabled(True)
        self.preferences.save_startup_permission(True)
        dialog = SettingsDialog(self.preferences, startup)
        dialog.start_at_login.setChecked(False)
        with patch.object(startup, "set_enabled", side_effect=OSError("access denied")), \
                patch("settings_dialog.QMessageBox.warning"):
            dialog.save()
        self.assertTrue(startup.entry_path.exists())
        self.assertIs(Preferences(self.preferences.path).startup_permission, False)

    def test_wsl_never_registers(self):
        startup = self.registration(release="6.18-microsoft-standard-WSL2")
        self.assertIn("WSL", startup.unsupported_reason)
        dialog = SettingsDialog(self.preferences, startup)
        self.assertFalse(dialog.start_at_login.isEnabled())
        self.assertFalse(dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled())
        with self.assertRaises(OSError):
            startup.set_enabled(True)
        self.assertFalse(startup.entry_path.exists())

    def test_mac_launch_agent_and_removal(self):
        startup = self.registration("Darwin")
        startup.command = ["/Users/test/My App/python", "/Users/test/My App/main.py", "--startup"]
        startup.set_enabled(True)
        entry = plistlib.loads(startup.entry_path.read_bytes())
        self.assertEqual(entry["ProgramArguments"], startup.command)
        self.assertEqual(entry["Label"], APP_ID)
        self.assertTrue(entry["RunAtLoad"])
        self.assertNotIn("KeepAlive", entry)
        self.assertTrue(startup.is_enabled())
        startup.set_enabled(False)
        self.assertFalse(startup.entry_path.exists())

    def test_windows_only_own_user_value_is_changed(self):
        values = {"OtherApp": "leave alone"}
        key = MagicMock()
        def query(handle, name):
            if name not in values:
                raise FileNotFoundError(name)
            return values[name], 1
        def delete(handle, name):
            if name not in values:
                raise FileNotFoundError(name)
            del values[name]
        registry = SimpleNamespace(
            HKEY_CURRENT_USER="HKCU", KEY_SET_VALUE=2, REG_SZ=1,
            OpenKey=MagicMock(return_value=key), CreateKeyEx=MagicMock(return_value=key),
            QueryValueEx=query, DeleteValue=delete,
            SetValueEx=lambda handle, name, reserved, kind, value: values.update({name: value}),
        )
        startup = self.registration("Windows")
        startup.command = [r"C:\My App\pythonw.exe", r"C:\My App\main.py", "--startup"]
        with patch.dict(sys.modules, {"winreg": registry}):
            self.assertFalse(startup.is_enabled())
            startup.set_enabled(True)
            self.assertEqual(values["SuperDpet"], subprocess.list2cmdline(startup.command))
            registry.CreateKeyEx.assert_called_with("HKCU", RUN_KEY, 0, 2)
            self.assertTrue(startup.is_enabled())
            startup.set_enabled(False)
            startup.set_enabled(False)
        self.assertEqual(values, {"OtherApp": "leave alone"})

    def test_linux_quoting_and_venv_path(self):
        self.assertEqual(desktop_argument('/my app/main.py'), '"/my app/main.py"')
        self.assertEqual(desktop_argument('a$b'), '"a\\\\$b"')
        self.assertEqual(desktop_argument('a%b'), '"a%%b"')
        with self.assertRaises(ValueError):
            desktop_argument('a\nb')
        startup = self.registration()
        self.assertEqual(startup.command[0], os.path.abspath(sys.executable))

    def test_startup_launch_without_consent_exits_before_pet(self):
        import main
        for permission in (None, False):
            self.preferences.startup_permission = permission
            with patch.object(main, "QApplication", return_value=self.app), \
                    patch.object(main, "Preferences", return_value=self.preferences), \
                    patch.object(main, "PetWindow") as pet, \
                    patch.object(sys, "argv", ["main.py", "--startup"]):
                self.assertEqual(main.run(), 0)
                pet.assert_not_called()


if __name__ == "__main__":
    unittest.main()
