"""Execute the PowerShell wrapper against a fake package, without hardware IO."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


POWERSHELL = shutil.which("pwsh")
SCRIPTS = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt" and POWERSHELL and (3, 10) <= sys.version_info[:2] < (3, 15), "Requires Windows, PowerShell 7 and a Decky-compatible Python")
class SmokeWrapperTests(unittest.TestCase):
    def test_staging_path_with_spaces_is_not_forwarded_to_probe_argparse(self):
        with tempfile.TemporaryDirectory(prefix="ally smoke fixture ") as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            for name in ("common.ps1", "smoke-backend.ps1"):
                shutil.copy2(SCRIPTS / name, scripts / name)
            plugin = root / "out" / "staging" / "ally-system-control"
            package = plugin / "py_modules" / "ally_system_control"
            package.mkdir(parents=True)
            (plugin / "dist").mkdir()
            (plugin / "py_modules" / "comtypes").mkdir()
            (plugin / "py_modules" / "comtypes-1.0.0.dist-info" / "licenses").mkdir(parents=True)
            for name in ("plugin.json", "main.py", "LICENSE", "dist/index.js", "py_modules/ally_system_control/__init__.py", "py_modules/comtypes/__init__.py"):
                (plugin / name).write_text("", encoding="utf-8")
            (plugin / "py_modules" / "comtypes-1.0.0.dist-info" / "licenses" / "LICENSE.txt").write_text("Fixture license", encoding="utf-8")
            (plugin / "package.json").write_text(json.dumps({"name": "ally-system-control"}), encoding="utf-8")
            (package / "probe.py").write_text(
                "import argparse, json, sys\n"
                "parser = argparse.ArgumentParser()\n"
                "parser.add_argument('--read-only', action='store_true', required=True)\n"
                "args = parser.parse_args()\n"
                "print(json.dumps({'readOnly': args.read_only, 'argv': sys.argv}))\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [POWERSHELL, "-NoProfile", "-File", str(scripts / "smoke-backend.ps1"), "-PythonPath", sys.executable],
                cwd=root, text=True, capture_output=True, check=True,
            )
            output = json.loads(result.stdout)
            self.assertTrue(output["readOnly"])
            self.assertEqual(output["argv"], ["ally_system_control.probe", "--read-only"])


if __name__ == "__main__":
    unittest.main()
