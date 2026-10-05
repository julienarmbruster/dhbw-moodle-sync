"""File and folder names that are safe on Windows, macOS and Linux."""
import re
import unicodedata

_TRANSLIT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])$", re.IGNORECASE)
# "TSA/TSL25 - ", "EITES25 - ": cohort prefixes in DHBW course names
_COHORT_PREFIX = re.compile(r"^\s*[A-Z][A-Z0-9/]*\d{2}\s*[-–:]\s*")
# " (DEF)": lecturer code at the end of DHBW course names
_LECTURER_SUFFIX = re.compile(r"\s*\([A-ZÄÖÜ]{2,4}\)\s*$")


def nfc(text):
    return unicodedata.normalize("NFC", text or "")


def clean_segment(name, fallback="Sonstiges"):
    """Folder name without spaces, umlauts or characters that Windows forbids."""
    s = nfc(name).translate(_TRANSLIT)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9.\-]+", "_", s)
    s = re.sub(r"_*-_*", "-", s)
    s = re.sub(r"_+", "_", s).strip("._-")
    if _RESERVED.match(s):
        s = "_" + s
    return s[:60].rstrip("._-") or fallback


def safe_filename(name):
    """Keeps the original name (umlauts, spaces) and only replaces characters Windows forbids."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nfc(name)).strip().rstrip(".")
    if _RESERVED.match(s.split(".")[0]):
        s = "_" + s
    return s or "datei"


def suggest_folder(course_name):
    """'TSA/TSL25 - Technische Informatik 3 (DEF)' -> 'Technische_Informatik_3'."""
    s = _COHORT_PREFIX.sub("", nfc(course_name))
    s = _LECTURER_SUFFIX.sub("", s)
    return clean_segment(s, fallback="Kurs")


def unique_path(path):
    if not path.exists():
        return path
    for i in range(2, 1000):
        candidate = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Kein freier Dateiname für {path}")


def labeled(path, label):
    """'Skript.pdf' + 'neu 2026-10-05' -> 'Skript (neu 2026-10-05).pdf' (or with a number if taken)."""
    return unique_path(path.with_name(f"{path.stem} ({label}){path.suffix}"))
