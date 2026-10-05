import unittest

from moodle_sync.rules import target_dir

CATEGORIES = {"sort_mode": "categories"}


def where(section, filename, module="x", config=CATEGORIES, course=None, filepath="/"):
    return target_dir(config, course or {}, section, module, filename, filepath)


class DefaultRulesTest(unittest.TestCase):
    def test_sections_by_kind(self):
        self.assertEqual(where("Vorlesungsfolien", "a.pdf"), "Vorlesung")
        self.assertEqual(where("Lecture Slides", "a.pdf"), "Vorlesung")
        self.assertEqual(where("Übungen", "Blatt1.pdf"), "Uebungen")
        self.assertEqual(where("Übungen /Klausurvorbereitung", "Übungsklausur_1.pdf"), "Klausurvorbereitung")
        self.assertEqual(where("Hausarbeit", "Template.pptx"), "Hausarbeit")
        self.assertEqual(where("Extras", "ISO_15288.pdf"), "Material")

    def test_orga_and_formula_sheets_stay_in_course_folder(self):
        self.assertEqual(where("Allgemeines", "Organisatorisches.pdf"), "")
        self.assertEqual(where("Formelsammlung", "El_ES_FS.pdf"), "")
        self.assertEqual(where("Abschnitt 2", "Formelsammlung 3.5.pdf"), "")

    def test_generic_sections_use_the_file_name(self):
        self.assertEqual(where("Abschnitt 3", "Übungen_Teil_3.pdf"), "Uebungen")
        self.assertEqual(where("Abschnitt 3", "Lösung_Teil_3.PDF"), "Uebungen")
        self.assertEqual(where("Abschnitt 3", "Skriptum_Teil_3.pdf"), "Vorlesung")
        self.assertEqual(where("6. Oktober - 12. Oktober", "Folien.pdf"), "Vorlesung")

    def test_unknown_section_keeps_its_name(self):
        self.assertEqual(where("Projekt Roboterarm", "Plan.pdf"), "Projekt_Roboterarm")

    def test_folder_contents_keep_subfolders(self):
        self.assertEqual(where("Vorlesung", "a.pdf", filepath="/Woche 1/"), "Vorlesung/Woche_1")


class OwnRulesTest(unittest.TestCase):
    def test_course_rules_first_and_ignore(self):
        course = {"rules": [{"section": "Dozentenbereich", "ignore": True},
                            {"file": "^Skript", "to": "Skripte"}]}
        self.assertIsNone(where("Dozentenbereich", "Tools.zip.001", course=course))
        self.assertEqual(where("Allgemeines", "Skript_Kapitel1.pdf", course=course), "Skripte")

    def test_global_rules_and_umlauts_in_targets(self):
        config = {"sort_mode": "categories", "rules": [{"section": "übung", "to": "Übungsblätter"}]}
        self.assertEqual(where("Übungen", "Blatt1.pdf", config=config), "Übungsblätter")

    def test_global_ignore(self):
        config = {"sort_mode": "categories", "ignore": [{"file": r"\.mp4$", "ignore": True}]}
        self.assertIsNone(where("Vorlesung", "Aufzeichnung.mp4", config=config))

    def test_sections_mode_mirrors_moodle(self):
        config = {"sort_mode": "sections"}
        self.assertEqual(where("Übungen /Klausurvorbereitung", "a.pdf", config=config), "Uebungen_Klausurvorbereitung")
        self.assertEqual(where("Allgemeines", "a.pdf", config=config), "Allgemeines")


if __name__ == "__main__":
    unittest.main()
