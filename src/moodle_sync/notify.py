"""Desktop notifications without extra packages: Windows toast, macOS notification centre, Linux notify-send."""
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

# AppUserModelID of Windows PowerShell; lets us show toasts without registering an own app
_TOAST_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
_NO_WINDOW = 0x08000000

log = logging.getLogger("moodle_sync")


def _xml_escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _windows_toast(title, lines, open_path):
    texts = "".join(f"<text>{_xml_escape(t)}</text>" for t in [title, *lines][:3])
    launch = f' activationType="protocol" launch="{_xml_escape(Path(open_path).as_uri())}"' if open_path else ""
    xml = f'<toast{launch}><visual><binding template="ToastGeneric">{texts}</binding></visual></toast>'
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null;"
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument; $x.LoadXml($env:MOODLE_SYNC_TOAST);"
        "$t = New-Object Windows.UI.Notifications.ToastNotification $x;"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{_TOAST_APP_ID}').Show($t)"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                   env=dict(os.environ, MOODLE_SYNC_TOAST=xml), creationflags=_NO_WINDOW,
                   capture_output=True, timeout=30)


def notify(title, lines=(), open_path=None):
    """Shows a notification; clicking it opens open_path (Windows). Failures are only logged."""
    lines = [line for line in lines if line]
    try:
        if sys.platform == "win32":
            _windows_toast(title, lines, open_path)
        elif sys.platform == "darwin":
            script = f"display notification {json.dumps(' '.join(lines))} with title {json.dumps(title)}"
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=30)
        elif shutil.which("notify-send"):
            subprocess.run(["notify-send", title, "\n".join(lines)], capture_output=True, timeout=30)
    except Exception as e:
        log.warning("Benachrichtigung fehlgeschlagen: %s", e)
