import json
import tempfile
import unittest
from pathlib import Path

from fake_moodle import FakeMoodle
from moodle_sync import engine, wizard
from moodle_sync.paths import Home

R = "resource"
COURSES = {
    11: ("TSA/TSL25 - Elektronik (ABC)", [("Vorlesungsfolien", [(R, "Folien", ["Folien_01.pdf"])])]),
    12: ("TSA/TSL25 - Technische Informatik 3 (DEF)", [("Dokumente zum Prozessor", [(R, "DB", ["Datasheet.pdf"])])]),
    13: ("StuV", [("Allgemeines", [(R, "Info", ["stuv.pdf"])])]),
}


class ScriptedConsole(wizard.Console):
    def __init__(self, answers):
        self.answers = list(answers)
        self.output = []
        super().__init__(ask=self._next, secret=self._next, say=self.output.append)

    def _next(self, prompt=""):
        self.output.append(prompt)
        return self.answers.pop(0)


def fake_connect(moodle):
    return {"public_config": lambda site: {"sitename": "Test-Moodle", "enablemobilewebservice": 1},
            "token": lambda site, user, password: "secret-token",
            "moodle": lambda site, token: moodle}


class ParseSelectionTest(unittest.TestCase):
    def test_numbers_and_ranges(self):
        self.assertEqual(wizard.parse_selection("1,3-5 8", 10), {1, 3, 4, 5, 8})
        self.assertEqual(wizard.parse_selection("9-7", 10), {7, 8, 9})
        self.assertEqual(wizard.parse_selection("2, 99", 3), {2})
        with self.assertRaises(ValueError):
            wizard.parse_selection("alle", 3)


class WizardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Home(Path(self.tmp.name) / "home").ensure()
        self.target = Path(self.tmp.name) / "Studium"

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_setup(self):
        moodle = FakeMoodle(COURSES)
        con = ScriptedConsole([
            "",                       # Moodle address: default
            "max.muster", "geheim",   # login
            str(self.target),         # target folder
            "",                       # courses: keep preselection (StuV is unticked)
            "2", "TI3", "",           # rename course 2, then done
            "",                       # sort mode: categories
            "",                       # download now? yes
        ])
        code = wizard.run_wizard(self.home, con=con, connect=fake_connect(moodle), windows=None)
        self.assertEqual(code, 0)
        config = json.loads(self.home.config.read_text("utf-8"))
        self.assertEqual({c["folder"] for c in config["courses"].values()}, {"Elektronik", "TI3"})
        self.assertEqual(config["sort_mode"], "categories")
        self.assertEqual(json.loads(self.home.token.read_text("utf-8"))["token"], "secret-token")
        self.assertNotIn("geheim", self.home.token.read_text("utf-8"))
        self.assertTrue((self.target / "TI3" / "Material" / "Datasheet.pdf").exists())
        self.assertTrue((self.target / "Elektronik" / "Vorlesung" / "Folien_01.pdf").exists())
        self.assertIn("13", engine.load_state(self.home.state)["seen_courses"], "unticked courses are not reported later")

    def test_change_courses_later(self):
        moodle = FakeMoodle(COURSES)
        wizard.run_wizard(self.home, con=ScriptedConsole(["", "u", "p", str(self.target), "1", "", "", "n"]),
                          connect=fake_connect(moodle), windows=None)
        con = ScriptedConsole(["1,2", "", "n"])
        self.assertEqual(wizard.run_courses(self.home, con=con, connect=fake_connect(moodle)), 0)
        config = json.loads(self.home.config.read_text("utf-8"))
        self.assertEqual(len(config["courses"]), 2)


if __name__ == "__main__":
    unittest.main()
