"""Minimal client for the Moodle mobile web service (the same interface the Moodle app uses)."""
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

USER_AGENT = f"dhbw-moodle-sync/{__version__} (+https://github.com/julienarmbruster/dhbw-moodle-sync)"
DEFAULT_SITE = "https://elearning.dhbw-ravensburg.de"
SERVICE = "moodle_mobile_app"
NETWORK_ERRORS = (urllib.error.URLError, socket.timeout, ConnectionError, TimeoutError)


class MoodleError(Exception):
    def __init__(self, code, message=""):
        super().__init__(f"{message} ({code})" if message else str(code))
        self.code = code


def normalize_site(url):
    """Accepts 'elearning.example.de' or a pasted page URL and returns the site root."""
    url = url.strip().rstrip("/")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    return re.sub(r"/(login/index\.php|my|course/view\.php|admin)(\b.*)?$", "", url).rstrip("/")


def _post(url, data, timeout=60):
    body = urllib.parse.urlencode(data).encode()
    request = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _flatten(params, prefix=""):
    """Moodle REST format: {'options': [{'name': 'x'}]} -> {'options[0][name]': 'x'}."""
    flat = {}
    for key, value in params.items():
        name = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(_flatten(value, name))
        elif isinstance(value, (list, tuple)):
            flat.update(_flatten(dict(enumerate(value)), name))
        else:
            flat[name] = value
    return flat


def public_config(site):
    """Public site information (no login needed): name, whether app access is enabled, login type."""
    body = json.dumps([{"index": 0, "methodname": "tool_mobile_get_public_config", "args": {}}]).encode()
    request = urllib.request.Request(
        f"{site}/lib/ajax/service-nologin.php?info=tool_mobile_get_public_config", data=body,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))[0]
    if result.get("error"):
        raise MoodleError("publicconfig", str((result.get("exception") or {}).get("message", "")))
    return result["data"]


def request_token(site, username, password, service=SERVICE):
    """Exchanges username and password for an app key. The password is not stored anywhere."""
    result = _post(f"{site}/login/token.php", {"username": username, "password": password, "service": service})
    if not result.get("token"):
        raise MoodleError(result.get("errorcode", "login"), result.get("error", "Anmeldung fehlgeschlagen"))
    return result["token"]


class Moodle:
    def __init__(self, site, token):
        self.site = site.rstrip("/")
        self.token = token

    def call(self, function, **params):
        data = {"wstoken": self.token, "wsfunction": function, "moodlewsrestformat": "json", **_flatten(params)}
        result = _post(f"{self.site}/webservice/rest/server.php", data)
        if isinstance(result, dict) and "exception" in result:
            raise MoodleError(result.get("errorcode", "?"), result.get("message", ""))
        return result

    def site_info(self):
        return self.call("core_webservice_get_site_info")

    def courses(self, userid):
        return self.call("core_enrol_get_users_courses", userid=userid)

    def contents(self, courseid):
        return self.call("core_course_get_contents", courseid=courseid)

    def download(self, fileurl, dest, expected_size=0, attempts=3):
        url = fileurl + ("&" if "?" in fileurl else "?") + "token=" + urllib.parse.quote(self.token)
        for attempt in range(1, attempts + 1):
            try:
                return self._download_once(url, dest, expected_size)
            except NETWORK_ERRORS + (IOError,):
                if attempt == attempts:
                    raise
                time.sleep(5 * attempt)

    def _download_once(self, url, dest, expected_size):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        part = dest.with_name(dest.name + ".part")
        try:
            with urllib.request.urlopen(request, timeout=120) as response, open(part, "wb") as out:
                content_type = response.headers.get("Content-Type", "")
                while True:
                    chunk = response.read(1 << 16)
                    if not chunk:
                        break
                    out.write(chunk)
            size = part.stat().st_size
            if "json" in content_type and size < 4096:
                # Moodle reports download errors as a small JSON document
                error = json.loads(part.read_text("utf-8", errors="replace") or "{}")
                if isinstance(error, dict) and ("errorcode" in error or "exception" in error):
                    raise MoodleError(error.get("errorcode", "?"), error.get("error") or error.get("message", ""))
            if expected_size and size != expected_size:
                raise IOError(f"unvollständig ({size} von {expected_size} Bytes)")
            os.replace(part, dest)
        finally:
            if part.exists():
                part.unlink()
