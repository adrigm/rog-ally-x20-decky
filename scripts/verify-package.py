"""Validate an install ZIP using stdlib only, then import its vendored modules.

Run with `python -I -B scripts/verify-package.py artifacts/<package>.zip`.
This never calls Windows setters, installs a plugin, or imports the repository
backend. Validation deliberately uses a fresh extraction and an isolated child.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import zipfile


PLUGIN_ID = "ally-system-control"
REQUIRED = {
    "plugin.json", "package.json", "main.py", "LICENSE", "README.md",
    "dist/index.js", "py_modules/ally_system_control/__init__.py",
    "py_modules/comtypes/__init__.py",
}
FORBIDDEN_PARTS = {
    ".git", ".venv", "node_modules", "__pycache__", ".pytest_cache",
    "tests", "docs", "scripts", "logs", "settings", "environment-audit.json",
}


def verify_archive(archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if not entries:
            raise ValueError("The archive is empty")
        seen: set[str] = set()
        relative_files: set[str] = set()
        for entry in entries:
            if "\\" in entry.filename:
                raise ValueError(f"Non-portable ZIP path: {entry.filename}")
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != PLUGIN_ID:
                raise ValueError(f"ZIP must contain exactly one {PLUGIN_ID}/ root: {entry.filename}")
            if entry.filename in seen:
                raise ValueError(f"Duplicate ZIP entry: {entry.filename}")
            seen.add(entry.filename)
            if ((entry.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError(f"Symlink in ZIP: {entry.filename}")
            relative = PurePosixPath(*path.parts[1:])
            if any(part in FORBIDDEN_PARTS for part in relative.parts) or relative.suffix in {".pyc", ".pyo", ".log"}:
                raise ValueError(f"Development/private file in ZIP: {entry.filename}")
            if not entry.is_dir():
                relative_files.add(relative.as_posix())
        missing = REQUIRED - relative_files
        if missing:
            raise ValueError(f"Missing files: {', '.join(sorted(missing))}")
        manifest = json.loads(archive.read(f"{PLUGIN_ID}/package.json"))
        if manifest.get("name") != PLUGIN_ID:
            raise ValueError("Unexpected package name")
        if not any("dist-info/licenses/" in name and name.startswith("py_modules/comtypes-") for name in relative_files):
            # Older wheels can place LICENSE.txt directly in dist-info.
            if not any(name.startswith("py_modules/comtypes-") and ".dist-info/" in name and "license" in name.lower() for name in relative_files):
                raise ValueError("The vendored comtypes license is missing")
        failed_entry = archive.testzip()
        if failed_entry:
            raise ValueError(f"Corrupt ZIP entry: {failed_entry}")
        with tempfile.TemporaryDirectory(prefix="ally-package-check-") as temporary:
            archive.extractall(temporary)
            plugin = Path(temporary) / PLUGIN_ID
            probe = r'''
import importlib, json, pathlib, sys
plugin = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(plugin))
sys.path.insert(0, str(plugin / "py_modules"))
for name in ("ally_system_control", "ally_system_control.controller", "comtypes", "main"):
    module = importlib.import_module(name)
    location = pathlib.Path(module.__file__).resolve()
    if plugin not in location.parents:
        raise RuntimeError(f"{name} imported from outside the extracted package: {location}")
print(json.dumps({"packageImports": "ok", "root": plugin.name}))
'''
            subprocess.run([sys.executable, "-I", "-B", "-c", probe, str(plugin)], cwd=temporary, check=True)
    print(f"ZIP structure, licenses and isolated imports: OK ({archive_path.name})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -I -B scripts/verify-package.py <archive.zip>")
    verify_archive(Path(sys.argv[1]).resolve(strict=True))
