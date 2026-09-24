# SuperDpet

Run from this checkout:

```bash
.venv/bin/python main.py
```

On native Windows, use `.venv\Scripts\python.exe main.py` with a Windows Python
environment containing PySide6.

## Optional startup (Milestone 6)

On a supported native desktop, the first launch asks about startup. It is off by
default. Check **Start SuperDpet when I sign in** and click **Save** to consent
and register it. **No thanks**, Escape, or closing that initial dialog saves a
decline, so the app does not ask again. Startup registration never happens just
from opening the app or Settings.

Right-click the pet and choose **Settings**, or use **Settings** in the tray
menu, to change your choice. Uncheck the option and save to remove registration.
The preference is saved separately from notes in `preferences.json` in Qt's
application data directory. Errors are reported; unreadable preferences are
preserved and startup changes are disabled until the file is repaired.

Registration applies to the current user's next desktop sign-in, using these
platform mechanisms:

- Windows: the `SuperDpet` value in
  `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`.
  See Microsoft's [Run key documentation](https://learn.microsoft.com/en-us/windows/win32/setupapi/run-and-runonce-registry-keys).
- Linux: `io.superdpet.SuperDpet.desktop` in `$XDG_CONFIG_HOME/autostart`, or
  `~/.config/autostart` by default. The desktop must support
  [XDG autostart](https://specifications.freedesktop.org/autostart/latest/).
- macOS: `~/Library/LaunchAgents/io.superdpet.SuperDpet.plist`, a per-user
  [launch agent](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
  that runs at login without restarting after Quit.

This source checkout registers its current Python interpreter and `main.py`
using absolute paths. Keep both in place. If you move the app or replace its
environment, launch it manually from the new location and save the setting again.
The OS can independently restrict login/background items.

**WSL:** automatic startup is unsupported and the Settings checkbox is disabled
with an explanation. No Windows or Linux startup entry is created from WSL.
Manual launch, notes, reminders, and the tray fallback continue to work.

**Hide Pet** leaves the app and reminder checks running. **Quit** stops both for
the current session; if startup is enabled, the app can open at the next sign-in.
Turn the option off in Settings to prevent that. Startup entries use `--startup`,
which exits without showing the pet unless saved permission is explicitly true.

## Verification

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
```

Tests use temporary paths and a mocked Windows registry, leaving real startup
settings untouched. Native sign-in behavior still requires testing on each OS.
On WSL, open Settings to check the explanation and disabled checkbox, then test
the reminder and Quit controls. On a native desktop, test declining and
restarting, enabling and signing in again, and disabling and signing in again.
