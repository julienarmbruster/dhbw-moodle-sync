"""Reading and writing config.json and token.json."""
import datetime as dt
import json
import os
import sys


def load_config(home):
    try:
        return json.loads(home.config.read_text("utf-8"))
    except FileNotFoundError:
        return None


def save_config(home, config):
    home.ensure()
    tmp = home.config.with_name(home.config.name + ".tmp")
    tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", "utf-8")
    os.replace(tmp, home.config)


def load_token(home):
    try:
        return json.loads(home.token.read_text("utf-8")).get("token")
    except FileNotFoundError:
        return None


def save_token(home, token, user=None):
    """Stores only the app key (never the password); readable for the current user only on Linux/macOS."""
    home.ensure()
    data = {"token": token, "user": user, "created": dt.datetime.now().isoformat(timespec="seconds")}
    home.token.write_text(json.dumps(data), "utf-8")
    if sys.platform != "win32":
        os.chmod(home.token, 0o600)
