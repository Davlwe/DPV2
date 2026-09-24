"""Opt-in, per-user sign-in registration. Importing this module changes nothing."""

import os
import platform
import plistlib
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QIODevice, QSaveFile


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_ID = "io.superdpet.SuperDpet"


def desktop_argument(value):
    # Desktop Entry Exec quoting has two escaping layers, and is not shell quoting.
    if any(character in value for character in "\n\r\x00"):
        raise ValueError("Startup paths cannot contain line breaks or null characters.")
    quoted = ''.join('\\' + c if c in '\\"`$' else c for c in value)
    return '"' + quoted.replace('\\', '\\\\').replace('%', '%%') + '"'


class StartupRegistration:
    def __init__(self):
        self.system = platform.system()
        self.unsupported_reason = None
        if self.system == "Linux" and (
            "microsoft" in platform.release().lower()
            or os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP")
        ):
            self.unsupported_reason = (
                "Automatic startup is unavailable in WSL. This Linux app cannot "
                "register itself as a native Windows sign-in app. Run SuperDpet "
                "on a native Windows, macOS, or Linux desktop to enable it. "
                "You can still launch it manually and use reminders here."
            )
        elif self.system not in ("Windows", "Darwin", "Linux"):
            self.unsupported_reason = "Automatic startup is not supported on this operating system."

        # Do not resolve the interpreter symlink: that would bypass a Unix venv.
        executable = Path(os.path.abspath(sys.executable))
        if self.system == "Windows" and executable.name.lower() == "python.exe":
            windowed = executable.with_name("pythonw.exe")
            if windowed.is_file():
                executable = windowed
        self.command = [str(executable), str(Path(__file__).resolve().with_name("main.py")), "--startup"]
        self.entry_path = None
        if self.system == "Linux":
            config = Path(os.environ.get("XDG_CONFIG_HOME", ""))
            if not config.is_absolute():
                config = Path.home() / ".config"
            self.entry_path = config / "autostart" / f"{APP_ID}.desktop"
        elif self.system == "Darwin":
            self.entry_path = Path.home() / "Library" / "LaunchAgents" / f"{APP_ID}.plist"

    def is_enabled(self):
        if self.unsupported_reason:
            return False
        if self.system == "Windows":
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                    value, kind = winreg.QueryValueEx(key, "SuperDpet")
                    return kind == winreg.REG_SZ and value == self.windows_command()
            except FileNotFoundError:
                return False
        try:
            return self.entry_path.read_bytes() == self.entry_data()
        except FileNotFoundError:
            return False

    def windows_command(self):
        command = subprocess.list2cmdline(self.command)
        if len(command) > 260:
            raise ValueError("The app's path is too long for Windows sign-in registration. Move it to a shorter path.")
        return command

    def entry_data(self):
        if self.system == "Darwin":
            return plistlib.dumps({
                "Label": APP_ID,
                "ProgramArguments": self.command,
                "RunAtLoad": True,
                "LimitLoadToSessionType": "Aqua",
                # No KeepAlive: Quit must remain final for this session.
            })
        if "=" in self.command[0]:
            raise ValueError("Linux startup does not support an '=' in the interpreter path.")
        command = " ".join(desktop_argument(arg) for arg in self.command)
        return (
            "[Desktop Entry]\nType=Application\nName=SuperDpet\n"
            f"Exec={command}\nTerminal=false\n"
        ).encode("utf-8")

    def set_enabled(self, enabled):
        if self.unsupported_reason:
            raise OSError(self.unsupported_reason)
        if self.system == "Windows":
            import winreg
            if enabled:
                command = self.windows_command()
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, "SuperDpet", 0, winreg.REG_SZ, command)
            else:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                        winreg.DeleteValue(key, "SuperDpet")
                except FileNotFoundError:
                    pass
            return
        if not enabled:
            self.entry_path.unlink(missing_ok=True)
            return
        data = self.entry_data()
        self.entry_path.parent.mkdir(parents=True, exist_ok=True)
        file = QSaveFile(str(self.entry_path))
        if not file.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(file.errorString())
        if file.write(data) != len(data):
            error = file.errorString()
            file.cancelWriting()
            raise OSError(error)
        if not file.commit():
            raise OSError(file.errorString())
