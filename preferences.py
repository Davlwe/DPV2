"""Application preferences kept separate from the user's notes."""

import json
from pathlib import Path

from PySide6.QtCore import QIODevice, QSaveFile, QStandardPaths


class Preferences:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        ) / "preferences.json"
        # None means no decision yet; it never grants permission.
        self.startup_permission = None
        self.load_error = None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Expected a preferences object.")
            permission = data.get("startup_permission")
            if permission is not None and type(permission) is not bool:
                raise ValueError("Invalid startup permission.")
            self.startup_permission = permission
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as error:
            self.load_error = str(error)

    def save_startup_permission(self, allowed):
        if type(allowed) is not bool:
            raise ValueError("Startup permission must be true or false.")
        if self.load_error is not None:
            raise OSError("Preferences could not be loaded. The existing file was left untouched.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps({"startup_permission": allowed}, indent=2) + "\n").encode("utf-8")
        file = QSaveFile(str(self.path))
        if not file.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(file.errorString())
        if file.write(data) != len(data):
            error = file.errorString()
            file.cancelWriting()
            raise OSError(error)
        if not file.commit():
            raise OSError(file.errorString())
        self.startup_permission = allowed
