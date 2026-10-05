# dhbw-moodle-sync

[![Tests](https://github.com/julienarmbruster/dhbw-moodle-sync/actions/workflows/tests.yml/badge.svg)](https://github.com/julienarmbruster/dhbw-moodle-sync/actions/workflows/tests.yml)

Lädt deine Moodle-Kursdateien automatisch in sortierte Ordner und hält sie aktuell. Gebaut an der
DHBW Ravensburg, funktioniert aber mit jedem Moodle, das die offizielle Moodle-App erlaubt.

```
Semester_3/
├── Elektronik/
│   ├── Elektronik_Inhalt_Org.pdf
│   ├── Uebungen/
│   └── Vorlesung/
├── Fahrzeugtechnik/
│   ├── Formelsammlung 3.5.pdf
│   ├── Klausurvorbereitung/
│   ├── Uebungen/
│   └── Vorlesung/
└── Technische_Informatik_3/
    ├── Material/
    └── Vorlesung/
```

## Was es kann

- **Einrichtung in wenigen Minuten:** Ein Assistent fragt Moodle-Adresse, Anmeldung, Zielordner und Kurse ab und schlägt
  Ordnernamen vor („TSA/TSL25 - Technische Informatik 3 (DEF)“ → `Technische_Informatik_3`).
- **Sortiert automatisch** nach Art (Vorlesung, Uebungen, Klausurvorbereitung, Hausarbeit, Material) oder genau wie die
  Abschnitte im Moodle-Kurs.
- **Lädt nur Neues und Geändertes.** Dateien, die schon da sind (gleicher Name, gleiche Größe), werden erkannt und nicht
  doppelt geladen.
- **Überschreibt nie deine Änderungen:** Hast du eine Datei bearbeitet, landet eine neue Moodle-Version daneben.
- **Läuft von allein:** täglicher Abgleich im Hintergrund (holt verpasste Läufe nach), dazu ein Desktop-Button
  „Moodle aktualisieren“ und eine Benachrichtigung, wenn etwas Neues da ist.
- **Keine Zusatzpakete:** nur Python. Dein Passwort wird nie gespeichert.

## Installation

### Windows

1. Python installieren, falls noch nicht vorhanden: im Microsoft Store „Python 3.13“ oder in PowerShell
   `winget install Python.Python.3.13`.
2. In PowerShell:
   ```powershell
   python -m pip install --user https://github.com/julienarmbruster/dhbw-moodle-sync/archive/refs/heads/main.zip
   python -m moodle_sync setup
   ```
   (Falls `python` nicht gefunden wird, nimm `py`.)
3. Der Assistent führt durch den Rest: Anmeldung, Kursauswahl, Ordner, täglicher Abgleich und Desktop-Button.

### macOS und Linux

```bash
python3 -m pip install --user https://github.com/julienarmbruster/dhbw-moodle-sync/archive/refs/heads/main.zip
python3 -m moodle_sync setup
```

Für den täglichen Abgleich zeigt `python3 -m moodle_sync schedule` eine passende crontab-Zeile.

## Benutzung

| Befehl | Was passiert |
|---|---|
| `moodle-sync` | Abgleich (beim ersten Mal: Einrichtung) |
| `moodle-sync sync --dry-run` | zeigt nur, was geladen würde |
| `moodle-sync courses` | Kurse hinzufügen oder entfernen, Ordnernamen ändern |
| `moodle-sync login` | neu anmelden, z. B. nach einer Passwortänderung |
| `moodle-sync schedule 06:30` | Uhrzeit des täglichen Abgleichs ändern (`--off` schaltet ihn ab, Windows) |
| `moodle-sync shortcut` | Desktop-Button neu anlegen (Windows) |
| `moodle-sync status` | Einstellungen, letzter Abgleich, Kursliste |

Wird `moodle-sync` nicht gefunden, funktioniert immer `python -m moodle_sync …`.

## So wird sortiert

Im Standard („nach Art“) entscheidet zuerst der Name des Moodle-Abschnitts, danach der Dateiname:

| Abschnitt oder Datei enthält … | Ordner |
|---|---|
| Vorlesung, Folien, Skript, Lecture, Slides, Unterlagen | `Vorlesung` |
| Übung, Aufgabe, Lösung, Blatt, Exercise, Tutorium, Labor | `Uebungen` |
| Klausur, Prüfung, Exam | `Klausurvorbereitung` |
| Hausarbeit, Projektarbeit, Assignment | `Hausarbeit` |
| Literatur, Material, Dokumente, Standards, Extras | `Material` |
| Allgemeines, Organisation, Formelsammlung | direkt im Kursordner |
| alles andere | Ordner mit dem Namen des Abschnitts |

Inhalte aus Moodle-Ordnern behalten ihre Unterordner. Alternativ bildet die Einstellung „wie Moodle-Abschnitte“ den
Kurs 1:1 ab.

### Eigene Regeln

In der `config.json` im Einstellungsordner (`moodle-sync status` zeigt ihn an) kannst du alles anpassen:

```json
{
  "courses": {
    "10002": {
      "name": "TSA/TSL25 - Technische Informatik 3 (DEF)",
      "folder": "TI3",
      "rules": [
        {"section": "Dozentenbereich", "ignore": true},
        {"section": "GPIO", "to": "Programmieraufgaben/GPIO"}
      ]
    }
  },
  "rules": [{"section": "Übung", "to": "Übungsblätter"}],
  "ignore": [{"file": "\\.mp4$", "ignore": true}],
  "new_courses": [{"match": "Mathematik 3", "folder": "Mathe_3"}],
  "max_size_mb": 300
}
```

- `section`, `module` und `file` sind reguläre Ausdrücke für Abschnitt, Moodle-Eintrag und Dateiname. Groß- und
  Kleinschreibung ist egal, und alle angegebenen Felder müssen passen.
- `to` ist der Unterordner, `""` heißt direkt in den Kursordner. Mit `"ignore": true` wird die Datei übersprungen.
- Reihenfolge: Kursregeln, dann eigene Regeln (`rules`), dann die Standardregeln. Die erste passende Regel gewinnt.
- `new_courses` ordnet neu auftauchende Kurse automatisch einem Ordner zu, zum Beispiel wenn Mathe 3 erst später in
  Moodle erscheint.

Eine vollständige Beispieldatei liegt unter [`examples/config.example.json`](examples/config.example.json).

## Was passiert, wenn …

- **… der Dozent eine Datei aktualisiert?** Eine unveränderte lokale Kopie wird ersetzt. Hast du sie bearbeitet,
  etwa Notizen ins PDF geschrieben, kommt die neue Version daneben als `Datei (neu 2026-10-05).pdf`.
- **… ich eine Datei verschiebe oder lösche?** Sie wird nicht erneut geladen, außer Moodle hat eine neue Version.
- **… ein neuer Kurs dazukommt?** Du bekommst eine Benachrichtigung und fügst ihn mit `moodle-sync courses` hinzu.
- **… eine Datei riesig ist?** Dateien über 300 MB werden übersprungen und gemeldet (`max_size_mb`).
- **… eine Datei in einem Moodle-Eintrag doppelt hochgeladen wurde?** Geladen wird nur die Hauptdatei, wie beim
  Anklicken in Moodle.

## Sicherheit und Datenschutz

- Dein Passwort geht einmal an deine Moodle-Seite, genau wie bei der Moodle-App, und wird nicht gespeichert.
- Gespeichert wird nur ein App-Schlüssel in `token.json` im Einstellungsordner (Windows:
  `%LOCALAPPDATA%\dhbw-moodle-sync`). Du kannst ihn jederzeit in Moodle unter *Profil → Einstellungen →
  Sicherheitsschlüssel* widerrufen.
- Das Programm spricht nur mit deiner Moodle-Seite: kein Tracking, keine Cloud, keine Fremdpakete.
- Es lädt nur, worauf du in Moodle ohnehin Zugriff hast, und macht zwischen Downloads kurze Pausen, um den Server zu
  schonen.

## Probleme?

- **„Anmeldung fehlgeschlagen“:** Nimm Anmeldename und Kennwort wie auf der Moodle-Webseite. Läuft die Anmeldung an
  deiner Hochschule über eine andere Seite (Single Sign-on), kopiere den Schlüssel unter *Profil → Einstellungen →
  Sicherheitsschlüssel* und füge ihn im Assistenten ein.
- **„Zugang für die Moodle-App abgeschaltet“:** Deine Hochschule erlaubt die Moodle-App nicht, dann klappt es leider
  nicht.
- **Log:** Die Datei `sync.log` liegt im Einstellungsordner.
- **Andere Hochschule:** Gib im Assistenten einfach deren Moodle-Adresse ein.

## Deinstallieren

```powershell
python -m moodle_sync schedule --off
python -m pip uninstall dhbw-moodle-sync
```

Danach die Desktop-Verknüpfung und den Einstellungsordner löschen. Deine Kursdateien bleiben natürlich liegen.

## Hinweise

Das ist ein inoffizielles Projekt von Studierenden, nicht von der DHBW. Kursmaterialien sind urheberrechtlich
geschützt: Nutze sie nur für dich selbst und verbreite sie nicht weiter.

## Mitmachen

```bash
git clone https://github.com/julienarmbruster/dhbw-moodle-sync
cd dhbw-moodle-sync
python -m pip install -e .
python -m unittest discover -s tests
```

Fehler und Ideen gerne als [Issue](https://github.com/julienarmbruster/dhbw-moodle-sync/issues).

## Lizenz

MIT, siehe [LICENSE](LICENSE).
