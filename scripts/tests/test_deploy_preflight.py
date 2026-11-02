"""An incomplete package must never replace a working deployed plugin."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


POWERSHELL = shutil.which("pwsh")
SCRIPTS = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Requires Windows and PowerShell 7")
class DeployPreflightTests(unittest.TestCase):
    def test_missing_dependency_or_license_preserves_current_plugin_before_any_move(self):
        for omission in ("dependency", "metadata", "license"):
            with self.subTest(omission=omission), tempfile.TemporaryDirectory(prefix="ally deploy fixture ") as temporary:
                root = Path(temporary)
                scripts = root / "scripts"
                scripts.mkdir()
                for name in ("common.ps1", "deploy-dev.ps1"):
                    shutil.copy2(SCRIPTS / name, scripts / name)
                staging = root / "out" / "staging" / "ally-system-control"
                for name in ("plugin.json", "main.py", "LICENSE", "dist/index.js", "py_modules/ally_system_control/__init__.py"):
                    target = staging / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("", encoding="utf-8")
                (staging / "package.json").write_text(json.dumps({"name": "ally-system-control"}), encoding="utf-8")
                if omission != "dependency":
                    dependency = staging / "py_modules" / "comtypes" / "__init__.py"
                    dependency.parent.mkdir(parents=True)
                    dependency.write_text("", encoding="utf-8")
                if omission != "metadata":
                    metadata = staging / "py_modules" / "comtypes-1.0.0.dist-info" / "licenses"
                    metadata.mkdir(parents=True)
                    if omission != "license":
                        (metadata / "LICENSE.txt").write_text("Fixture license", encoding="utf-8")
                homebrew = root / "homebrew"
                deployed = homebrew / "plugins" / "ally-system-control"
                deployed.mkdir(parents=True)
                sentinel = deployed / "working-version.txt"
                sentinel.write_text("Preserve current plugin", encoding="utf-8")
                result = subprocess.run(
                    [POWERSHELL, "-NoProfile", "-File", str(scripts / "deploy-dev.ps1"), "-HomebrewPath", str(homebrew)],
                    cwd=root, text=True, capture_output=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("comtypes", result.stderr)
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "Preserve current plugin")
                self.assertEqual(list(deployed.iterdir()), [sentinel])
                self.assertFalse((homebrew / "backups").exists())
                self.assertEqual(sorted(path.name for path in homebrew.iterdir()), ["plugins"])


if __name__ == "__main__":
    unittest.main()
