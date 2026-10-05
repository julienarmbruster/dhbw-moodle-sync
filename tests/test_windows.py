import os
import sys
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from moodle_sync import windows
from moodle_sync.paths import Home

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


class TaskXmlTest(unittest.TestCase):
    def test_task_definition(self):
        xml = windows.task_xml(r"C:\Program Files\Python\pythonw.exe", '-m moodle_sync --home "C:\\A & B" sync --quiet',
                               r"C:\A & B", "06:45")
        root = ET.fromstring(xml.split("\n", 1)[1])  # skip the UTF-16 declaration line
        self.assertEqual(root.find(".//t:StartWhenAvailable", NS).text, "true")
        self.assertEqual(root.find(".//t:DisallowStartIfOnBatteries", NS).text, "false")
        self.assertTrue(root.find(".//t:StartBoundary", NS).text.endswith("T06:45:00"))
        self.assertEqual(root.find(".//t:WorkingDirectory", NS).text, r"C:\A & B")
        self.assertIn("--quiet", root.find(".//t:Arguments", NS).text)


@unittest.skipUnless(sys.platform == "win32", "Windows only")
class LauncherTest(unittest.TestCase):
    def test_background_uses_pythonw(self):
        command, args = windows.launcher(background=True)
        self.assertEqual(args, ["-m", "moodle_sync"])
        if Path(sys.executable).with_name("pythonw.exe").exists():
            self.assertTrue(command.lower().endswith("pythonw.exe"))


@unittest.skipUnless(sys.platform == "win32" and os.environ.get("MOODLE_SYNC_INTEGRATION"),
                     "set MOODLE_SYNC_INTEGRATION=1 to touch the real Task Scheduler")
class IntegrationTest(unittest.TestCase):
    def test_shortcut_and_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Home(tmp).ensure()
            path = windows.create_shortcut(home, folder=tmp, name="Moodle Test")
            self.assertTrue(Path(path).exists())
            name = f"moodle-sync-test-{uuid.uuid4().hex[:8]}"
            windows.install_task(home, "05:00", name=name)
            try:
                self.assertIsNotNone(windows.task_next_run(name))
            finally:
                windows.remove_task(name)
            self.assertIsNone(windows.task_next_run(name))


if __name__ == "__main__":
    unittest.main()
