"""Compares the Moodle courses with the local folders and downloads what is new or changed.

Rules of thumb:
- A file that is already on disk (same name and size, anywhere in the course folder) is adopted, not downloaded again.
- A file you changed is never overwritten; a new Moodle version is saved next to it as "name (neu DATE)".
- Files you moved or deleted are not downloaded again unless Moodle has a new version.
"""
import datetime as dt
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .moodle import MoodleError
from .names import labeled, nfc, safe_filename, unique_path
from .rules import target_dir

log = logging.getLogger("moodle_sync")


@dataclass
class Report:
    new: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    adopted: int = 0
    too_big: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    new_courses: list = field(default_factory=list)
    bytes: int = 0

    @property
    def changed(self):
        return bool(self.new or self.updated)


def load_state(path):
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except FileNotFoundError:
        return {}


def save_state(path, state):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, path)


def target_root(config):
    return Path(config.get("target") or config["base"]).expanduser()


def course_config(config, course_id, title):
    """Settings of a selected course, or of a new course matched by a "new_courses" rule, else None."""
    if course_id in config.get("courses", {}):
        return config["courses"][course_id]
    for rule in config.get("new_courses", []):
        if re.search(rule["match"], title, re.IGNORECASE):
            return {"folder": rule["folder"], "rules": rule.get("rules", [])}
    return None


def module_files(module):
    """Files of a Moodle activity. For a 'file' resource only the main file, like a click in Moodle does;
    extra files in a resource are mostly accidental duplicate uploads."""
    files = [f for f in module.get("contents") or [] if f.get("type") == "file"]
    if module.get("modname") == "resource" and len(files) > 1:
        files = [f for f in files if f.get("sortorder")] or files
    return files


def build_index(folder):
    """(lower-case name, size) -> existing file, used to adopt files that are already there."""
    index = {}
    if folder.exists():
        for p in folder.rglob("*"):
            if p.is_file() and not p.name.endswith(".part"):
                index.setdefault((nfc(p.name).lower(), p.stat().st_size), p)
    return index


def _unchanged_since_download(path, entry):
    try:
        stat = path.stat()
    except OSError:
        return False
    return stat.st_size == entry.get("size") and abs(stat.st_mtime - entry.get("mtime", 0)) < 2


def sync(config, moodle, state_path, dry_run=False):
    """Runs one sync. With dry_run nothing is downloaded or saved; the report shows what would happen."""
    root = target_root(config)
    state = load_state(state_path)
    known = state.setdefault("files", {})
    seen_courses = state.setdefault("seen_courses", {})
    report = Report()
    max_bytes = int(config.get("max_size_mb", 300)) * 1024 * 1024
    today = dt.date.today().isoformat()

    userid = moodle.site_info()["userid"]
    for course in moodle.courses(userid):
        course_id, title = str(course["id"]), course.get("fullname", "")
        ccfg = course_config(config, course_id, title)
        if ccfg is None:
            if course_id not in seen_courses:
                seen_courses[course_id] = title
                report.new_courses.append(title)
            continue
        course_dir = root / ccfg["folder"]
        index = None
        try:
            sections = moodle.contents(int(course_id))
        except MoodleError as e:
            report.errors.append(f"{ccfg['folder']}: Kursinhalt nicht lesbar ({e})")
            continue
        for section in sections:
            for module in section.get("modules", []):
                if module.get("modname") not in ("resource", "folder"):
                    continue
                for f in module_files(module):
                    name, filepath = f["filename"], f.get("filepath") or "/"
                    rel = target_dir(config, ccfg, section.get("name", ""), module.get("name", ""), name, filepath)
                    if rel is None:
                        continue
                    key = f"{course_id}:{module['id']}:{filepath}{name}"
                    size, modified = int(f.get("filesize") or 0), int(f.get("timemodified") or 0)
                    entry = known.get(key)
                    if entry and entry.get("size") == size and entry.get("timemodified") == modified:
                        continue
                    shown_target = "/".join(p for p in (ccfg["folder"], rel, name) if p)
                    if size > max_bytes:
                        known[key] = {"size": size, "timemodified": modified, "skipped": "zu groß"}
                        report.too_big.append(f"{shown_target} ({size / 1048576:.0f} MB)")
                        continue
                    folder = course_dir.joinpath(*rel.split("/")) if rel else course_dir
                    if entry is None:
                        if index is None:
                            index = build_index(course_dir)
                        hit = index.get((nfc(safe_filename(name)).lower(), size))
                        if hit:
                            known[key] = {"path": str(hit.relative_to(root)), "size": size,
                                          "timemodified": modified, "mtime": hit.stat().st_mtime}
                            report.adopted += 1
                            continue
                        dest, kind = unique_path(folder / safe_filename(name)), "new"
                    else:
                        old = root / entry["path"] if entry.get("path") else None
                        if old is not None and _unchanged_since_download(old, entry):
                            dest = old
                        else:
                            near = old.parent if old is not None and old.parent.exists() else folder
                            dest = labeled(near / safe_filename(name), f"neu {today}")
                        kind = "updated"
                    shown = dest.relative_to(root).as_posix()
                    report.bytes += size
                    if dry_run:
                        getattr(report, kind).append(shown)
                        continue
                    try:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        log.info("%s %s (%.1f MB)", "Lade" if kind == "new" else "Aktualisiere", shown, size / 1048576)
                        moodle.download(f["fileurl"], dest, size)
                    except Exception as e:
                        report.errors.append(f"{shown}: {e}")
                        log.error("Download fehlgeschlagen: %s: %s", shown, e)
                        continue
                    known[key] = {"path": str(dest.relative_to(root)), "size": size,
                                  "timemodified": modified, "mtime": dest.stat().st_mtime}
                    getattr(report, kind).append(shown)
                    save_state(state_path, state)
                    time.sleep(0.2)
    if not dry_run:
        state["last_sync"] = dt.datetime.now().isoformat(timespec="seconds")
        save_state(state_path, state)
    return report
