"""Command line: moodle-sync [--home DIR] [sync | setup | courses | login | schedule | shortcut | status]."""
import argparse
import logging
import os
import sys
import time

from . import __version__, engine, wizard
from .config import load_config, load_token
from .moodle import NETWORK_ERRORS, Moodle, MoodleError
from .notify import notify
from .paths import Home, default_home

log = logging.getLogger("moodle_sync")


def windows_module():
    if sys.platform != "win32":
        return None
    from . import windows
    return windows


def build_parser():
    parser = argparse.ArgumentParser(
        prog="moodle-sync",
        description="Lädt deine Moodle-Kursdateien in sortierte Ordner und hält sie aktuell. "
                    "Ohne Befehl: Abgleich (oder Einrichtung, falls noch nichts eingerichtet ist).")
    parser.add_argument("--home", help=f"Ordner für Einstellungen, Schlüssel und Log (Standard: {default_home()})")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="BEFEHL")
    sync = sub.add_parser("sync", help="neue und geänderte Dateien laden")
    sync.add_argument("--dry-run", action="store_true", help="nur anzeigen, was passieren würde")
    sync.add_argument("--quiet", action="store_true", help="ohne Ausgabe und Rückfragen, meldet sich per Benachrichtigung")
    sync.add_argument("--pause", action="store_true", help="Fenster am Ende kurz offen lassen (Desktop-Verknüpfung)")
    sub.add_parser("setup", help="Einrichtungsassistent (Anmeldung, Kurse, Ordner, täglicher Abgleich)")
    sub.add_parser("courses", help="Kursauswahl und Ordnernamen ändern")
    sub.add_parser("login", help="neu bei Moodle anmelden")
    schedule = sub.add_parser("schedule", help="täglichen Abgleich einrichten oder abschalten (Windows)")
    schedule.add_argument("time", nargs="?", default="07:00", help="Uhrzeit, Standard 07:00")
    schedule.add_argument("--off", action="store_true", help="täglichen Abgleich entfernen")
    sub.add_parser("shortcut", help="Desktop-Verknüpfung 'Moodle aktualisieren' anlegen (Windows)")
    sub.add_parser("status", help="Einstellungen und letzten Abgleich anzeigen")
    return parser


def setup_logging(home, console):
    log.setLevel(logging.INFO)
    log.handlers.clear()
    if home.log.exists() and home.log.stat().st_size > 1_000_000:
        os.replace(home.log, home.log.with_name("sync.old.log"))
    to_file = logging.FileHandler(home.log, encoding="utf-8")
    to_file.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(to_file)
    if console and sys.stdout:
        to_console = logging.StreamHandler(sys.stdout)
        to_console.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(to_console)


def started_by_double_click():
    """True if this process owns its console window alone (exe started from Explorer)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        processes = (ctypes.c_uint * 4)()
        return ctypes.windll.kernel32.GetConsoleProcessList(processes, 4) <= 1
    except Exception:
        return False


def pause(seconds=20):
    if not sys.stdin or not sys.stdin.isatty():
        return
    try:
        import msvcrt
    except ImportError:
        input("\nEnter drücken zum Schließen.")
        return
    print(f"\nFenster schließt in {seconds} Sekunden (oder eine Taste drücken).")
    end = time.time() + seconds
    while time.time() < end:
        if msvcrt.kbhit():
            msvcrt.getwch()
            return
        time.sleep(0.1)


def summarize(config, report, dry_run, quiet):
    if report.adopted:
        log.info("%d vorhandene Dateien übernommen", report.adopted)
    if dry_run:
        for item in report.new:
            log.info("Würde laden: %s", item)
        for item in report.updated:
            log.info("Neue Version: %s", item)
    for item in report.too_big:
        log.warning("Übersprungen (zu groß): %s", item)
    for title in report.new_courses:
        log.info("Neuer Kurs (nicht ausgewählt): %s", title)
    for item in report.errors:
        log.error("Fehler: %s", item)
    log.info("Fertig: %d neu, %d aktualisiert%s", len(report.new), len(report.updated), " (Testlauf)" if dry_run else "")
    if not quiet or dry_run:
        return
    if report.changed:
        courses = sorted({path.split("/")[0] for path in report.new + report.updated})
        title = f"Moodle: {len(report.new)} neue Datei{'' if len(report.new) == 1 else 'en'}"
        if report.updated:
            title += f", {len(report.updated)} aktualisiert"
        notify(title, [", ".join(courses)], engine.target_root(config))
    if report.new_courses:
        notify("Neuer Moodle-Kurs", [", ".join(report.new_courses)[:150], "Mit 'moodle-sync courses' hinzufügen."])
    if report.errors:
        notify("Moodle-Sync: Fehler", [f"{len(report.errors)} Datei(en) nicht geladen, Details im Log."])


def run_sync(home, dry_run=False, quiet=False):
    config = load_config(home)
    if not config:
        if quiet:
            notify("Moodle-Sync ist noch nicht eingerichtet", ["Bitte einmal 'moodle-sync setup' ausführen."])
            return 2
        return wizard.run_wizard(home, windows=windows_module())
    token = load_token(home)
    for attempt in range(1, 4):
        if not token:
            if quiet:
                log.warning("Kein Moodle-Schlüssel vorhanden")
                notify("Moodle-Sync: Anmeldung nötig", ["'Moodle aktualisieren' starten oder 'moodle-sync login'."])
                return 2
            token = wizard.login(home, config["site"], wizard.Console())
            if not token:
                return 2
        try:
            report = engine.sync(config, Moodle(config["site"], token), home.state, dry_run=dry_run)
            break
        except MoodleError as e:
            if e.code != "invalidtoken":
                raise
            log.warning("Der gespeicherte Moodle-Schlüssel gilt nicht mehr")
            token = None
        except NETWORK_ERRORS as e:
            if not quiet or attempt == 3:
                raise
            log.warning("Moodle nicht erreichbar (%s), neuer Versuch in 2 Minuten", e)
            time.sleep(120)
    else:
        return 2
    summarize(config, report, dry_run, quiet)
    return 1 if report.errors else 0


def cmd_login(home):
    config = load_config(home)
    if not config:
        print("Noch nicht eingerichtet, bitte zuerst 'moodle-sync setup' ausführen.")
        return 2
    token = wizard.login(home, config["site"], wizard.Console())
    if token:
        print("Anmeldung gespeichert.")
    return 0 if token else 2


def cmd_schedule(home, args):
    windows = windows_module()
    if windows is None:
        print("Der tägliche Abgleich wird automatisch nur unter Windows eingerichtet. Unter macOS/Linux z. B. per crontab:")
        print(f"  0 7 * * *  {sys.executable} -m moodle_sync --home \"{home.dir}\" sync --quiet")
        return 0
    if args.off:
        windows.remove_task()
        print("Täglicher Abgleich entfernt.")
        return 0
    windows.install_task(home, args.time)
    print(f"Täglicher Abgleich um {args.time} eingerichtet, nächster Lauf: {windows.task_next_run() or '?'}")
    return 0


def cmd_shortcut(home):
    windows = windows_module()
    if windows is None:
        print("Desktop-Verknüpfungen gibt es nur unter Windows.")
        return 0
    print(f"Verknüpfung angelegt: {windows.create_shortcut(home)}")
    return 0


def cmd_status(home):
    config = load_config(home) or {}
    state = engine.load_state(home.state)
    files = state.get("files", {})
    print(f"Einstellungen:   {home.dir}")
    print(f"Moodle:          {config.get('site', '-')}")
    print(f"Zielordner:      {config.get('target') or config.get('base', '-')}")
    print(f"Sortierung:      {'wie Moodle-Abschnitte' if config.get('sort_mode') == 'sections' else 'nach Art'}")
    print(f"Angemeldet:      {'ja' if load_token(home) else 'nein'}")
    print(f"Letzter Abgleich: {state.get('last_sync', '-')}")
    print(f"Bekannte Dateien: {sum(1 for entry in files.values() if entry.get('path'))}")
    windows = windows_module()
    if windows is not None:
        next_run = windows.task_next_run()
        print(f"Täglicher Abgleich: {'nächster Lauf ' + next_run if next_run else 'aus'}")
    courses = config.get("courses", {})
    print(f"Kurse ({len(courses)}):")
    for course in courses.values():
        print(f"  {course['folder']:<40} {course.get('name', '')}")
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    home = Home(args.home).ensure()
    command = args.command or ("sync" if home.config.exists() else "setup")
    quiet = getattr(args, "quiet", False)
    dry_run = getattr(args, "dry_run", False)
    keep_open = getattr(args, "pause", False) or (args.command is None and started_by_double_click())
    setup_logging(home, console=not quiet)
    try:
        if command == "setup":
            code = wizard.run_wizard(home, windows=windows_module())
        elif command == "courses":
            code = wizard.run_courses(home)
        elif command == "login":
            code = cmd_login(home)
        elif command == "schedule":
            code = cmd_schedule(home, args)
        elif command == "shortcut":
            code = cmd_shortcut(home)
        elif command == "status":
            code = cmd_status(home)
        else:
            log.info("Start (%s%s)", "geplant" if quiet else "manuell", ", Testlauf" if dry_run else "")
            code = run_sync(home, dry_run=dry_run, quiet=quiet)
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        code = 130
    except Exception as e:  # the scheduled task must never fail silently
        log.exception("Abbruch: %s", e)
        if quiet:
            notify("Moodle-Sync: Abbruch", [str(e)[:150]])
        code = 1
    if keep_open:
        pause()
    return code
