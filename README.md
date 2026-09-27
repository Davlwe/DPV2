# SuperDpet

Run from this checkout:

```bash
.venv/bin/python main.py
```

On native Windows, use `.venv\Scripts\python.exe main.py` with a Windows Python
environment containing PySide6.

The standing pet blinks every 2–5 seconds, closing its eyes for 120–180ms after
the closed-eye frame has actually painted. Controls and menus do not suspend
blinking. Dragging, modal dialogs, active reminders, and waving do; a fresh
random delay starts afterward. The tray-unavailable notice is non-modal.
Short left-clicks immediately show the buttons and one random greeting while a
closed-eye wave plays for 950ms:
“Hi, how can I help you today?” or “Wanna add a note or reminder?” The only
left-click buttons are Add Note and View Notes. Quit remains in the right-click
and tray menus. Repeated clicks restart one wave timer; dragging cancels the
wave and hides the greeting and buttons.
Reminders use an orange glow
and alert motion. Completing a note queues a happy bounce with sparkles after
the notes dialog closes. Normal idle never moves the desktop window.

Blink and action timings are in `IdleSettings` in `idle_behavior.py`. Temporary
timestamped diagnostics are controlled by `BLINK_DIAGNOSTICS` in that file.
The standing, standing-blink, and standing-wave 1024px frames are loaded relative
to `main.py`; no source assets are rewritten. Normal idle uses neither the older
poster-like full-body image nor the original bust sprites.
Missing images produce terminal errors and retain a visible fallback.

## Reminder choices

Add Note has a “Remind me” choice: 1, 5, or 10 minutes before the due time.
Settings saves the default for future notes (initially 5 minutes), including on
WSL where startup registration is unavailable. Changing this default does not
change existing notes; each Add Note form can override it.

Each note stores `reminder_minutes` in `notes.json`. The trigger is its due time
minus that number of minutes. Legacy notes without the field receive 5 minutes
when loaded, and the migrated field is persisted on the next successful write.
Completed/already-reminded notes remain excluded; overdue unshown reminders are
caught up after restart. The global default lives in `preferences.json` alongside
startup consent. The developer 5-second test uses the chosen default as its lead.

For an additional visible desktop check (not offscreen), run:

```bash
.venv/bin/python tests/native_interaction_check.py
```

It opens a temporary pet, checks painted blink/wave transitions and interactions,
uses temporary note storage, saves three pet-only captures in `assets/diagnostics/`,
then closes. Native compositor drag and menu gestures should also be checked
manually, since synthetic mouse events may not receive Wayland input grabs.
Pass `--no-captures` to run without writing any images.

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
