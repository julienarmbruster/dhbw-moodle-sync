import datetime as dt
import os
import tempfile
import time
import unittest
from pathlib import Path

from fake_moodle import FakeMoodle
from moodle_sync import engine

R, F = "resource", "folder"


def course_def(files_in_slides=("Folien_01.pdf",), exercise=("Blatt_01.pdf", 100, 1)):
    return {
        11: ("TSA/TSL25 - Elektronik (ABC)", [
            ("Allgemeines", [(R, "Orga", ["Elektronik_Inhalt_Org.pdf"])]),
            ("Vorlesungsvorlagen", [(F, "Vorlesungsvorlagen", list(files_in_slides))]),
            ("Übungen", [(R, "Übung 1", [exercise])]),
        ]),
        12: ("StuV", [("Allgemeines", [(R, "Info", ["stuv.pdf"])])]),
    }


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "Semester_3"
        self.state = Path(self.tmp.name) / "state.json"
        self.config = {"target": str(self.root), "sort_mode": "categories",
                       "courses": {"11": {"name": "Elektronik", "folder": "Elektronik", "rules": []}}}

    def tearDown(self):
        self.tmp.cleanup()

    def run_sync(self, moodle, **kwargs):
        return engine.sync(self.config, moodle, self.state, **kwargs)

    def test_first_sync_sorts_files_and_second_sync_does_nothing(self):
        moodle = FakeMoodle(course_def())
        report = self.run_sync(moodle)
        self.assertEqual(sorted(report.new), ["Elektronik/Elektronik_Inhalt_Org.pdf", "Elektronik/Uebungen/Blatt_01.pdf",
                                              "Elektronik/Vorlesung/Folien_01.pdf"])
        self.assertEqual(report.new_courses, ["StuV"])
        again = self.run_sync(FakeMoodle(course_def()))
        self.assertFalse(again.changed)
        self.assertEqual(again.new_courses, [], "a course is only reported once")

    def test_existing_files_are_adopted_not_downloaded(self):
        (self.root / "Elektronik" / "Irgendwo").mkdir(parents=True)
        (self.root / "Elektronik" / "Irgendwo" / "Folien_01.pdf").write_bytes(b"x" * 100)
        moodle = FakeMoodle(course_def())
        report = self.run_sync(moodle)
        self.assertEqual(report.adopted, 1)
        self.assertNotIn("Folien_01.pdf", moodle.downloads)

    def test_update_replaces_untouched_file_but_keeps_edited_one(self):
        self.run_sync(FakeMoodle(course_def(files_in_slides=[("Folien_01.pdf", 100, 1), ("Folien_02.pdf", 100, 1)])))
        edited = self.root / "Elektronik" / "Vorlesung" / "Folien_02.pdf"
        time.sleep(0.01)
        edited.write_bytes(b"my notes" * 50)
        os.utime(edited, (time.time() + 10, time.time() + 10))
        report = self.run_sync(FakeMoodle(course_def(files_in_slides=[("Folien_01.pdf", 150, 2), ("Folien_02.pdf", 250, 2)])))
        today = dt.date.today().isoformat()
        self.assertEqual(sorted(report.updated), ["Elektronik/Vorlesung/Folien_01.pdf",
                                                  f"Elektronik/Vorlesung/Folien_02 (neu {today}).pdf"])
        self.assertEqual((self.root / "Elektronik/Vorlesung/Folien_01.pdf").stat().st_size, 150)
        self.assertEqual(edited.read_bytes(), b"my notes" * 50)

    def test_new_file_does_not_overwrite_own_file_with_same_name(self):
        own = self.root / "Elektronik" / "Uebungen" / "Blatt_01.pdf"
        own.parent.mkdir(parents=True)
        own.write_bytes(b"mine")
        report = self.run_sync(FakeMoodle(course_def()))
        self.assertIn("Elektronik/Uebungen/Blatt_01 (2).pdf", report.new)
        self.assertEqual(own.read_bytes(), b"mine")

    def test_only_main_file_of_a_resource(self):
        courses = {11: ("Elektronik", [("Übungen", [(R, "Lösung", ["Loesung.pdf", "Loesung (1).pdf"])])])}
        moodle = FakeMoodle(courses)
        self.run_sync(moodle)
        self.assertEqual(moodle.downloads, ["Loesung.pdf"])

    def test_too_big_files_are_skipped_and_reported_once(self):
        self.config["max_size_mb"] = 1
        big = FakeMoodle(course_def(exercise=("Video.mp4", 5 * 1024 * 1024, 1)))
        self.assertEqual(len(self.run_sync(big).too_big), 1)
        self.assertEqual(self.run_sync(big).too_big, [])

    def test_new_course_rule_and_broken_course(self):
        self.config["new_courses"] = [{"match": r"mathe(matik)?\s*3", "folder": "Mathe_3"}]
        courses = course_def()
        courses[13] = ("TSA/TSL25 - Mathematik 3 (PQR)", [("Vorlesung", [(R, "Kapitel 1", ["Mathe3_K1.pdf"])])])
        report = self.run_sync(FakeMoodle(courses, broken={11}))
        self.assertEqual(report.new, ["Mathe_3/Vorlesung/Mathe3_K1.pdf"])
        self.assertEqual(len(report.errors), 1)

    def test_dry_run_changes_nothing(self):
        moodle = FakeMoodle(course_def())
        report = self.run_sync(moodle, dry_run=True)
        self.assertEqual(len(report.new), 3)
        self.assertEqual(report.bytes, 300)
        self.assertEqual(moodle.downloads, [])
        self.assertFalse(self.state.exists())
        self.assertFalse(self.root.exists())


if __name__ == "__main__":
    unittest.main()
