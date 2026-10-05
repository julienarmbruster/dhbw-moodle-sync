"""Where settings, Moodle key, state and log are stored."""
import os
import sys
from pathlib import Path

APP_NAME = "dhbw-moodle-sync"


def default_home():
    env = os.environ.get("MOODLE_SYNC_HOME")
    if env:
        return Path(env).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP_NAME


def default_target():
    documents = Path.home() / "Documents"
    return (documents if documents.exists() else Path.home()) / "Moodle"


class Home:
    """The app folder: config.json (settings), token.json (Moodle key), state.json (known files), sync.log."""

    def __init__(self, path=None):
        self.dir = Path(path).expanduser().resolve() if path else default_home()
        self.config = self.dir / "config.json"
        self.token = self.dir / "token.json"
        self.state = self.dir / "state.json"
        self.log = self.dir / "sync.log"

    def ensure(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        return self
