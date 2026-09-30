# macOS transparency investigation

Inspected baseline: `2a554445903b6afd4da872003298c749a989188f`.
This checkout already contains a transparency fix in that commit. No additional
runtime rendering change is justified by the reproduction available here.
The affected Mac's revision, Qt version and native output have not been supplied;
the reported large dark silhouette remains **unconfirmed**, not fixed by this
investigation. The available execution environment is Linux, not macOS.

## Rendering path and diagnosis

- `main.py`, `PetWindow.__init__`: creates the 288 × 400 top-level QWidget with
  `FramelessWindowHint | NoDropShadowWindowHint`, then sets
  `WA_TranslucentBackground`, all before showing it. The parent has no stylesheet
  or explicit opaque background. The 288 × 288 child sprite has a transparent
  stylesheet. Greeting and button backgrounds are intentional, separately hidden
  children. Menus and reminder dialogs are separate windows.
- `main.py`, `PetWindow.paintEvent`: replaces destination RGBA with transparent
  pixels using `CompositionMode_Source`. Transparent SourceOver would not erase;
  Source with transparent fill already does. Qt clips this to the paint region.
  Sprite changes and animation ticks request full parent updates.
- `idle_behavior.py`, `PetSprite.show_frame` and `paintEvent`: load original
  alpha pixmaps into a QLabel, then override its normal painting with one
  `drawPixmap`. There is no RGB conversion, alpha stripping, mask, opacity effect,
  or accumulated transformed pixmap. Drawing uses default SourceOver, smooth
  sampling and antialiasing. Each paint gets a new painter; transforms are bracketed
  with save/restore. Wave rotation is at most 0.8 degrees, reactions translate,
  and sleep scales the artwork and draws translucent Zs. The dark blue shadow
  on those Zs is only offset one pixel; it cannot explain a large pet silhouette.
  Reaction decorations use colored pens. The child does not own an independent
  native window in the normal configuration.
- `main.py`, `PetWindow.apply_task_glow`: the sprite has a
  `QGraphicsDropShadowEffect` that is enabled after construction by `refresh_mood`.
  It is an intentional centered colored glow, radius 14 / alpha 145 normally,
  radius 20 / alpha 230 for reminders. This effect introduces a separate Qt
  rendering/cache path, so it needs an independent A/B test if the problem remains.
  It is not configured as a black offset shadow.

**A — Native shadow:** the earlier revision set only FramelessWindowHint, leaving
the native shadow enabled. That is a plausible source of a dark silhouette even
with a perfectly transparent PNG. Current Qt Cocoa code explicitly sets
`NSWindow.hasShadow` from NoDropShadowWindowHint. The current checkout should
therefore disable it. This is a candidate for the earlier report, not proof of
what happened on the affected Mac.

**B/C — Backing store or stale painting:** existing retained-surface tests pass,
as do added rotation/effect tests and a check of the actual Qt backing image after
a greeting is hidden. Qt's Cocoa backing store itself clears dirty regions with
alpha before painting. Consequently, an artificial retained-QImage test failing
without the parent's explicit clear would not prove that native Cocoa forgot to
clear. The desktop compositor and effect-cache behavior still require native
reproduction.

**D — Alpha:** no application-side alpha loss was found. Output buffers and fresh
renders retain transparent pixels in the tested environment, including at 2×
scale. This does not rule out a Cocoa presentation bug on another configuration.

**E — Environment/version mismatch:** compare actual interpreter/Qt versions,
checkout hashes, native-window attributes and display scale on both Macs.
`requirements.txt` pins PySide6 6.11.2, but a previously created environment may
have another version. macOS/Qt builds, Retina/external-display scale and native
widget environment overrides can exercise different Cocoa paths. None of these
differences is established for the two Macs yet.

Adding a second clear inside the child is not supported by these findings. The
parent already clears before children and effects; child clearing would not
remove an OS shadow or cover the effect's full exterior bounds.

Primary references checked for the pinned Qt version:

- [Qt translucent QWidget requirements](https://doc.qt.io/qt-6/qwidget.html#creating-translucent-windows)
- [Cocoa window flags, including hasShadow](https://github.com/qt/qtbase/blob/v6.11.2/src/plugins/platforms/cocoa/qcocoawindow.mm#L646-L699)
- [Cocoa window opacity/background](https://github.com/qt/qtbase/blob/v6.11.2/src/plugins/platforms/cocoa/qnswindow.mm#L269-L290)
- [Cocoa backing-store clear](https://github.com/qt/qtbase/blob/v6.11.2/src/plugins/platforms/cocoa/qcocoabackingstore.mm#L78-L108)

## Reproduce on both Macs

Quit existing pet instances first. From the updated checkout, run each command
separately in a graphical desktop session, without forcing the offscreen backend:

```bash
git rev-parse --short HEAD
.venv/bin/python scripts/diagnose_transparency.py
.venv/bin/python scripts/diagnose_transparency.py --no-glow
.venv/bin/python scripts/diagnose_transparency.py --native-shadow
```

Each run creates an isolated pet for 45 seconds. Click to wave, switch standing /
sitting, sleep / wake, and drag over light and dark backgrounds. Repeat on each
display if their scaling differs. The two switches change only the diagnostic
instance, one factor at a time. The normal app retains all existing behavior.

The printed temporary output directory contains:

- `report.json`: source hashes, interpreter, PySide/Qt, OS, architecture, backend,
  scale, widget attributes and actual Cocoa `hasShadow` / `isOpaque` properties.
  Normal Cocoa results should have all three native booleans false; the shadow
  comparison should have `window_has_shadow: true`.
- `NNN-backing.png`: a copy of Qt's image backing buffer, taken before fresh
  rendering. On buffered backends this is not guaranteed to be the currently
  presented buffer. If unavailable, the report records that explicitly.
- `NNN-fresh.png`: a freshly rendered Qt widget, including its enabled mood glow.
  This is not a screenshot of the macOS compositor or its native shadow.

Capture the visible silhouette with macOS's screenshot tool while it is present
and compare it to the matching PNGs on a checkerboard or white background. Some
image viewers display transparent areas as black. Periodic fresh grabs can also
affect repaint timing; if the issue only occurs in normal `main.py`, record that.
The script captures only pet rendering; it never captures the desktop, uploads
anything, edits real notes/preferences, or changes login registration.

Interpret the results before applying a further fix:

| Observation | Next conclusion/check |
| --- | --- |
| Default is clean; enabling native shadow reproduces the silhouette | Native shadow is implicated; compare the failing checkout with the existing flag fix. |
| Default reports `window_has_shadow: true` on Cocoa | The hint did not reach the native window as expected; investigate that Qt build/lifecycle. |
| Only disabling the glow removes the artifact | The graphics-effect path is implicated; compare backing and fresh images before replacing any glow code. |
| Backing image contains trails; fresh image is clean | Investigate dirty-region/cache/buffer handling. |
| Both Qt images are clean, but desktop is not | Investigate native shadow/presentation; PNG editing or child clear is not supported. |
| Both Qt images show the same artifact | Investigate the Qt painting/effect path and distinguish the intended glow. |

## Verification in this environment

The original 68 unittest cases passed. Added tests cover rotation/reaction
repaints with and without glow, and actual backing-buffer alpha after hiding a
greeting. Run all tests and the 2× rendering subset with:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=2 .venv/bin/python -m unittest discover -s tests -p test_transparent_repaint.py -v
```

The existing visible Wayland pose and interaction checks passed, including blink,
wave, dragging, notes, reminders and menu handling. No lint/type-check configuration
is present. Native macOS diagnosis requires the above results from the affected
machine; Linux/offscreen success alone cannot certify a macOS rendering fix.
