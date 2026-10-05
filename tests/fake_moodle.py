"""A fake Moodle for tests: courses are described as nested tuples, downloads write dummy bytes."""
from moodle_sync.moodle import MoodleError


class FakeMoodle:
    def __init__(self, courses, broken=()):
        """courses: {id: (title, [(section, [(modname, module_name, [file, ...])])])};
        file = "name" (100 bytes, modified 1) or ("name", size, modified)."""
        self.courses_def = courses
        self.broken = set(broken)
        self.downloads = []

    def site_info(self):
        return {"userid": 7, "fullname": "Test Person"}

    def courses(self, userid):
        return [{"id": cid, "fullname": title, "startdate": 0, "enddate": 0}
                for cid, (title, _) in self.courses_def.items()]

    def contents(self, courseid):
        if courseid in self.broken:
            raise MoodleError("nopermissions", "Kein Zugriff")
        result, module_id = [], courseid * 1000
        for section, modules in self.courses_def[courseid][1]:
            mods = []
            for modname, module_name, files in modules:
                module_id += 1
                contents = []
                for i, f in enumerate(files):
                    name, size, modified = (f, 100, 1) if isinstance(f, str) else f
                    contents.append({"type": "file", "filename": name, "filepath": "/", "filesize": size,
                                     "timemodified": modified, "fileurl": f"https://moodle.test/{name}?forcedownload=1",
                                     "sortorder": 1 if modname == "resource" and i == 0 else 0})
                mods.append({"id": module_id, "name": module_name, "modname": modname, "contents": contents})
            result.append({"name": section, "modules": mods})
        return result

    def download(self, fileurl, dest, expected_size=0):
        dest.write_bytes(b"x" * expected_size)
        self.downloads.append(dest.name)
