"""Windows integration: a daily scheduled task and a desktop shortcut "Moodle aktualisieren"."""
import datetime as dt
import getpass
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

TASK_NAME = "Moodle-Sync"
SHORTCUT_NAME = "Moodle aktualisieren"
_NO_WINDOW = 0x08000000


def launcher(background):
    """Program and arguments that start moodle-sync: the .exe when frozen, else (pythonw|python) -m moodle_sync."""
    if getattr(sys, "frozen", False):
        return sys.executable, []
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")
    if background and windowless.exists():
        exe = windowless
    return str(exe), ["-m", "moodle_sync"]


def task_xml(command, arguments, workdir, at="07:00"):
    """Task definition: daily at `at`, catches up on missed runs, also on battery, max 30 minutes."""
    hour, minute = (int(x) for x in at.split(":"))
    start = dt.datetime.combine(dt.date.today(), dt.time(hour, minute)).isoformat()
    domain = os.environ.get("USERDOMAIN", "")
    user = f"{domain}\\{getpass.getuser()}" if domain else getpass.getuser()
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Lädt neue Dateien aus Moodle (dhbw-moodle-sync). Verpasste Läufe werden nachgeholt.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{escape(user)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(command)}</Command>
      <Arguments>{escape(arguments)}</Arguments>
      <WorkingDirectory>{escape(workdir)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _run(args, encoding="oem", **kwargs):
    """Runs a Windows tool; console tools like schtasks answer in the OEM code page."""
    result = subprocess.run(args, capture_output=True, text=True, encoding=encoding, errors="replace",
                            creationflags=_NO_WINDOW, **kwargs)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"{args[0]} fehlgeschlagen")
    return result.stdout.strip()


def _powershell(script, env=None):
    script = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + script
    return _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], encoding="utf-8", env=env)


def install_task(home, at="07:00", name=TASK_NAME):
    command, args = launcher(background=True)
    arguments = subprocess.list2cmdline(args + ["--home", str(home.dir), "sync", "--quiet"])
    xml = task_xml(command, arguments, str(home.dir), at)
    fd, path = tempfile.mkstemp(suffix=".xml")
    try:
        with os.fdopen(fd, "w", encoding="utf-16") as f:
            f.write(xml)
        _run(["schtasks", "/Create", "/TN", name, "/XML", path, "/F"])
    finally:
        os.unlink(path)


def remove_task(name=TASK_NAME):
    _run(["schtasks", "/Delete", "/TN", name, "/F"])


def task_next_run(name=TASK_NAME):
    """Next run time as text, or None if the task does not exist."""
    script = f"(Get-ScheduledTaskInfo -TaskName '{name}' -ErrorAction Stop).NextRunTime.ToString('dd.MM.yyyy HH:mm')"
    try:
        return _powershell(script)
    except RuntimeError:
        return None


def create_shortcut(home, folder=None, name=SHORTCUT_NAME):
    """Creates '<name>.lnk' on the desktop (or in folder) that runs a visible sync. Returns its path."""
    command, args = launcher(background=False)
    script = (
        "$d = if ($env:MS_FOLDER) { $env:MS_FOLDER } else { [Environment]::GetFolderPath('Desktop') };"
        "$p = Join-Path $d ($env:MS_NAME + '.lnk');"
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($p);"
        "$s.TargetPath = $env:MS_TARGET; $s.Arguments = $env:MS_ARGS; $s.WorkingDirectory = $env:MS_WORKDIR;"
        "$s.IconLocation = $env:MS_ICON; $s.Description = 'Lädt neue Dateien aus Moodle'; $s.Save(); $p"
    )
    env = dict(os.environ, MS_FOLDER=str(folder or ""), MS_NAME=name, MS_TARGET=command,
               MS_ARGS=subprocess.list2cmdline(args + ["--home", str(home.dir), "sync", "--pause"]),
               MS_WORKDIR=str(home.dir), MS_ICON=os.path.expandvars(r"%SystemRoot%\System32\imageres.dll,229"))
    return _powershell(script, env=env)
