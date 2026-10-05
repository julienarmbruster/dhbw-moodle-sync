import tempfile
import unittest
from pathlib import Path

from moodle_sync.names import clean_segment, labeled, safe_filename, suggest_folder, unique_path


class SuggestFolderTest(unittest.TestCase):
    def test_dhbw_course_names(self):
        cases = {
            "TSA/TSL25 - Technische Informatik 3 (DEF)": "Technische_Informatik_3",
            "TSA25/TSL25 - Digitaltechnik (GHI)": "Digitaltechnik",
            "TSA/TSL25 - Automotive / Aerospace Software-Engineering (JKL)": "Automotive_Aerospace_Software-Engineering",
            "TSA/TFE25 - Fahrzeugtechnik und Fahrzeugelektrik (MNO)": "Fahrzeugtechnik_und_Fahrzeugelektrik",
            "StuV": "StuV",
        }
        for title, folder in cases.items():
            self.assertEqual(suggest_folder(title), folder, title)

    def test_other_universities_keep_their_names(self):
        self.assertEqual(suggest_folder("Analysis für Informatik (WS 2026/27)"), "Analysis_fuer_Informatik_WS_2026_27")


class CleanNamesTest(unittest.TestCase):
    def test_clean_segment(self):
        self.assertEqual(clean_segment("Übungen /Klausurvorbereitung"), "Uebungen_Klausurvorbereitung")
        self.assertEqual(clean_segment("Harware-Timer (TIM)"), "Harware-Timer_TIM")
        self.assertEqual(clean_segment("Café"), "Cafe")
        self.assertEqual(clean_segment("CON"), "_CON")
        self.assertEqual(clean_segment("   "), "Sonstiges")

    def test_safe_filename_keeps_umlauts_and_spaces(self):
        self.assertEqual(safe_filename("Lösung Teil 3.pdf"), "Lösung Teil 3.pdf")
        self.assertEqual(safe_filename('a:b?"c".pdf'), "a_b__c_.pdf")
        self.assertEqual(safe_filename("notizen. "), "notizen")
        self.assertEqual(safe_filename("aux.txt"), "_aux.txt")


class UniquePathTest(unittest.TestCase):
    def test_numbers_and_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Skript.pdf"
            self.assertEqual(unique_path(path), path)
            path.write_text("x")
            self.assertEqual(unique_path(path).name, "Skript (2).pdf")
            self.assertEqual(labeled(path, "neu 2026-10-05").name, "Skript (neu 2026-10-05).pdf")


if __name__ == "__main__":
    unittest.main()
