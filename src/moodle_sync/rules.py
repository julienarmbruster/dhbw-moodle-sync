"""Decides in which subfolder of a course folder a Moodle file ends up.

A rule is a dict with optional regexes for "section", "module" and "file" (case-insensitive,
all given ones must match) and a target "to" (subfolder, "" = course folder itself).
{"ignore": true} instead of "to" skips matching files. The first matching rule wins.
"""
import re

from .names import clean_segment, nfc, safe_filename

# Default sorting for sort_mode "categories" (German and English section names).
DEFAULT_RULES = [
    {"section": r"formelsammlung|formula", "to": ""},
    {"file": r"formelsammlung|formula.?sheet", "to": ""},
    {"section": r"^(allgemein|general|organisation|organisatorisch|orga\b|infos?\b|informationen)", "to": ""},
    {"section": r"klausur|prüfung|pruefung|exam", "to": "Klausurvorbereitung"},
    {"section": r"hausarbeit|projektarbeit|seminararbeit|assignment|abgabe", "to": "Hausarbeit"},
    {"section": r"übung|uebung|aufgabe|lösung|loesung|exercise|tutori|praktikum|labor|homework", "to": "Uebungen"},
    {"section": r"vorlesung|folie|skript|lecture|slide|unterlagen|script", "to": "Vorlesung"},
    {"section": r"literatur|literature|standard|material|extra|dokument|additional|datenbl|reading", "to": "Material"},
    {"file": r"klausur|prüfung|pruefung|exam", "to": "Klausurvorbereitung"},
    {"file": r"übung|uebung|aufgabe|lösung|loesung|blatt|exercise|sheet|solution", "to": "Uebungen"},
    # generic section names ("Abschnitt 3", "Thema 2", weekly sections like "6. Oktober - 12. Oktober")
    {"section": r"^(inhalt|abschnitt|thema|kapitel|woche|topic|week|section|unit)"
                r"|\d{1,2}\.?\s*(jan|feb|mär|mar|apr|mai|may|jun|jul|aug|sep|okt|oct|nov|dez|dec)", "to": "Vorlesung"},
]


def rule_matches(rule, section, module, filename):
    for key, value in (("section", section), ("module", module), ("file", filename)):
        if key in rule and not re.search(rule[key], nfc(value), re.IGNORECASE):
            return False
    return True


def target_dir(config, course, section, module, filename, filepath="/"):
    """Subfolder (with "/" separators) inside the course folder, or None if the file is ignored."""
    own_rules = course.get("rules", []) + config.get("rules", [])
    for rule in own_rules + config.get("ignore", []):
        if rule.get("ignore") and rule_matches(rule, section, module, filename):
            return None
    candidates = [rule for rule in own_rules if not rule.get("ignore")]
    if config.get("sort_mode", "categories") == "categories":
        candidates += config.get("generic_rules", DEFAULT_RULES)
    to = next((rule.get("to", "") for rule in candidates if rule_matches(rule, section, module, filename)), None)
    if to is None:
        to = clean_segment(section) if nfc(section).strip() else ""
    parts = [safe_filename(p) for p in to.replace("\\", "/").split("/") if p.strip()]
    parts += [clean_segment(p) for p in (filepath or "/").split("/") if p]
    return "/".join(parts)
