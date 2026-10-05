"""Interactive setup: Moodle address, login, target folder, courses, sorting, schedule and first sync."""
import getpass
import re
import sys
import time
from pathlib import Path

from . import engine
from .config import load_config, load_token, save_config, save_token
from .moodle import DEFAULT_SITE, NETWORK_ERRORS, Moodle, MoodleError, normalize_site, public_config, request_token
from .names import safe_filename, suggest_folder
from .paths import default_target

CONNECT = {"public_config": public_config, "token": request_token, "moodle": Moodle}

# Courses that are usually not a subject; they start unticked in the course list
ORGA_HINTS = re.compile(
    r"stuv|kursorganisation|organisation|arbeitsschutz|arbeitssicherheit|unterweisung|meinung|evaluation|"
    r"bibliothek|edv-einf|schreib|praxisprojekt|anleitung|videokonferenz|zoom|sprechstunde|infos? f(ü|ue)r",
    re.IGNORECASE)


class Console:
    """Input and output; tests pass their own functions."""

    def __init__(self, ask=input, secret=getpass.getpass, say=print):
        self.ask, self.secret, self.say = ask, secret, say

    def yes(self, question, default=True):
        answer = self.ask(f"{question} [{'J/n' if default else 'j/N'}]: ").strip().lower()
        return default if not answer else answer in ("j", "ja", "y", "yes")


def parse_selection(text, count):
    """'1,3-5 8' -> {1, 3, 4, 5, 8}; numbers outside 1..count are dropped."""
    chosen = set()
    for part in re.split(r"[,;\s]+", text.strip()):
        if not part:
            continue
        span = re.fullmatch(r"(\d+)-(\d+)", part)
        if span:
            a, b = sorted((int(span.group(1)), int(span.group(2))))
            chosen.update(range(a, b + 1))
        elif part.isdigit():
            chosen.add(int(part))
        else:
            raise ValueError(part)
    return {n for n in chosen if 1 <= n <= count}


def is_running(course, now):
    start, end = course.get("startdate") or 0, course.get("enddate") or 0
    return start <= now and (not end or end >= now)


def login(home, site, con, connect=CONNECT):
    """Asks for username and password (3 tries) and stores the app key. Fallback: paste a key from Moodle."""
    for _ in range(3):
        user = con.ask("Moodle-Anmeldename: ").strip()
        password = con.secret("Moodle-Kennwort (bleibt unsichtbar): ")
        try:
            token = connect["token"](site, user, password)
        except MoodleError as e:
            con.say(f"  Anmeldung fehlgeschlagen: {e}")
            continue
        except NETWORK_ERRORS as e:
            con.say(f"  Keine Verbindung zu Moodle: {e}")
            continue
        finally:
            password = None
        save_token(home, token, user)
        return token
    con.say("\nMeldest du dich nur über den Browser an (Single Sign-on)? Dann in Moodle unter")
    con.say("Profil > Einstellungen > Sicherheitsschlüssel den Schlüssel für 'Moodle mobile web service' kopieren.")
    key = con.ask("Schlüssel einfügen (Enter = abbrechen): ").strip()
    if not key:
        return None
    save_token(home, key)
    return key


def choose_courses(config, courses, con, now=None):
    """Course list with ticks and folder names. Returns (selected courses for the config, {id: title} not selected)."""
    now = now or time.time()
    existing = config.get("courses", {})
    courses = sorted(courses, key=lambda c: (not is_running(c, now), c.get("fullname", "").lower()))
    rows = []
    for c in courses:
        cid, title = str(c["id"]), c.get("fullname", "")
        if existing:
            ticked = cid in existing
        else:
            ticked = is_running(c, now) and not c.get("hidden") and not ORGA_HINTS.search(title)
        rows.append({"id": cid, "title": title, "folder": existing.get(cid, {}).get("folder") or suggest_folder(title),
                     "ticked": ticked})

    con.say("\nDeine Moodle-Kurse ([x] = vorausgewählt):")
    for i, row in enumerate(rows, 1):
        con.say(f"  [{'x' if row['ticked'] else ' '}] {i:>2}  {row['title']}")
    while True:
        answer = con.ask("Welche Kurse? Enter = die mit [x], sonst Nummern (z. B. 1,3,5-8): ")
        if not answer.strip():
            break
        try:
            chosen = parse_selection(answer, len(rows))
        except ValueError as e:
            con.say(f"  Das verstehe ich nicht: {e}")
            continue
        for i, row in enumerate(rows, 1):
            row["ticked"] = i in chosen
        break

    selected = [row for row in rows if row["ticked"]]
    taken = set()
    for row in selected:  # two courses must not share a folder
        base, n = row["folder"], 2
        while row["folder"].lower() in taken:
            row["folder"], n = f"{base}_{n}", n + 1
        taken.add(row["folder"].lower())
    if selected:
        con.say("\nOrdner pro Kurs:")
        for i, row in enumerate(selected, 1):
            con.say(f"  {i:>2}  {row['folder']:<40} <- {row['title']}")
        while True:
            answer = con.ask("Einen Namen ändern? Nummer eingeben (Enter = passt so): ").strip()
            if not answer:
                break
            if not answer.isdigit() or not 1 <= int(answer) <= len(selected):
                con.say("  Bitte eine Nummer aus der Liste eingeben.")
                continue
            row = selected[int(answer) - 1]
            new = con.ask(f"  Neuer Ordnername für '{row['title']}' [{row['folder']}]: ").strip()
            if new:
                row["folder"] = safe_filename(new)

    result = {}
    for row in selected:
        entry = dict(existing.get(row["id"], {}))  # keeps own rules of a course
        entry.update({"name": row["title"], "folder": row["folder"]})
        entry.setdefault("rules", [])
        result[row["id"]] = entry
    return result, {row["id"]: row["title"] for row in rows if not row["ticked"]}


def choose_sort_mode(config, con):
    con.say("\nWie sollen die Dateien innerhalb eines Kurses sortiert werden?")
    con.say("  1  nach Art: Vorlesung, Uebungen, Klausurvorbereitung, Hausarbeit, Material (empfohlen)")
    con.say("  2  genau wie die Abschnitte im Moodle-Kurs")
    current = "2" if config.get("sort_mode") == "sections" else "1"
    answer = con.ask(f"Auswahl [{current}]: ").strip() or current
    return "sections" if answer == "2" else "categories"


def setup_windows(home, con, windows):
    answer = con.ask("\nJeden Tag automatisch abgleichen? Uhrzeit [07:00] oder 'nein': ").strip().lower() or "07:00"
    if answer not in ("n", "nein", "no"):
        if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", answer):
            con.say("  Unklare Uhrzeit, ich nehme 07:00.")
            answer = "07:00"
        try:
            windows.install_task(home, answer)
            con.say(f"  OK: täglich um {answer} (verpasste Läufe werden nachgeholt, sobald der PC an ist)")
        except Exception as e:
            con.say(f"  Aufgabe konnte nicht angelegt werden: {e}")
    if con.yes("Desktop-Verknüpfung 'Moodle aktualisieren' anlegen?"):
        try:
            con.say(f"  OK: {windows.create_shortcut(home)}")
        except Exception as e:
            con.say(f"  Verknüpfung konnte nicht angelegt werden: {e}")


def remember_unselected(home, unselected):
    """Courses the user did not tick are not reported as 'new course' later."""
    state = engine.load_state(home.state)
    state.setdefault("seen_courses", {}).update(unselected)
    engine.save_state(home.state, state)


def first_sync(home, config, moodle, con):
    con.say("\nPrüfe, was es zu laden gibt ...")
    plan = engine.sync(config, moodle, home.state, dry_run=True)
    con.say(f"  {len(plan.new)} Dateien neu ({plan.bytes / 1048576:.0f} MB), {plan.adopted} schon vorhanden")
    if plan.too_big:
        con.say(f"  {len(plan.too_big)} Dateien über {config.get('max_size_mb', 300)} MB werden übersprungen")
    if plan.new and con.yes("Jetzt herunterladen?"):
        report = engine.sync(config, moodle, home.state)
        errors = f", {len(report.errors)} Fehler (Details im Log)" if report.errors else ""
        con.say(f"  OK: {len(report.new)} Dateien geladen{errors}")


def run_wizard(home, con=None, connect=CONNECT, windows=None):
    con = con or Console()
    config = load_config(home) or {}
    con.say("moodle-sync einrichten (abbrechen mit Strg+C)\n")

    default_site = config.get("site", DEFAULT_SITE)
    site = normalize_site(con.ask(f"Moodle-Adresse deiner Hochschule [{default_site}]: ").strip() or default_site)
    try:
        info = connect["public_config"](site)
        con.say(f"  OK: {info.get('sitename') or site}")
        if not int(info.get("enablemobilewebservice") or 0):
            con.say("  Achtung: Hier ist der Zugang für die Moodle-App abgeschaltet, dann klappt moodle-sync nicht.")
            if not con.yes("Trotzdem versuchen?", default=False):
                return 1
    except Exception as e:
        con.say(f"  Hinweis: Moodle antwortet nicht wie erwartet ({e}). Ich versuche es trotzdem.")

    con.say("\nAnmeldung (dein Kennwort wird nicht gespeichert, nur ein App-Schlüssel wie bei der Moodle-App):")
    token = login(home, site, con, connect)
    if not token:
        con.say("Abgebrochen.")
        return 2
    moodle = connect["moodle"](site, token)
    me = moodle.site_info()
    con.say(f"  OK: angemeldet als {me.get('fullname') or me.get('username', '')}")

    default_dir = config.get("target") or str(default_target())
    target = con.ask(f"\nZielordner für deine Kursdateien [{default_dir}]: ").strip().strip('"') or default_dir
    config.update({"site": site, "target": str(Path(target).expanduser())})
    config["courses"], unselected = choose_courses(config, moodle.courses(me["userid"]), con)
    config["sort_mode"] = choose_sort_mode(config, con)
    for key, default in (("max_size_mb", 300), ("rules", []), ("ignore", []), ("new_courses", [])):
        config.setdefault(key, default)
    save_config(home, config)
    remember_unselected(home, unselected)
    con.say(f"\nEinstellungen gespeichert: {home.config}")

    if sys.platform == "win32" and windows is not None:
        setup_windows(home, con, windows)
    first_sync(home, config, moodle, con)
    con.say("\nFertig! Neue Dateien holst du ab jetzt mit 'Moodle aktualisieren' oder 'moodle-sync'.")
    return 0


def run_courses(home, con=None, connect=CONNECT):
    """Change course selection and folder names later (also to add new courses)."""
    con = con or Console()
    config, token = load_config(home), load_token(home)
    if not config or not token:
        con.say("Noch nicht eingerichtet, bitte zuerst 'moodle-sync setup' ausführen.")
        return 2
    moodle = connect["moodle"](config["site"], token)
    config["courses"], unselected = choose_courses(config, moodle.courses(moodle.site_info()["userid"]), con)
    save_config(home, config)
    remember_unselected(home, unselected)
    first_sync(home, config, moodle, con)
    return 0
