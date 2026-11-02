"""Check that distribution validation rejects damaged/unsafe release archives."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile


SPEC = importlib.util.spec_from_file_location("verify_package", Path(__file__).resolve().parents[1] / "verify-package.py")
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class PackageValidationTests(unittest.TestCase):
    def make_archive(self, parent: Path, *, omit: str | None = None, extra: dict[str, str] | None = None) -> Path:
        files = {name: "" for name in VERIFY.REQUIRED}
        files.update({
            "package.json": json.dumps({"name": VERIFY.PLUGIN_ID, "version": "0.1.0"}),
            "plugin.json": json.dumps({"name": "Ally System Control"}),
            "py_modules/ally_system_control/controller.py": "class SystemController: pass\n",
            "py_modules/comtypes-1.0.0.dist-info/licenses/LICENSE.txt": "Test fixture license\n",
        })
        if omit:
            files.pop(omit)
        archive_path = parent / "fixture.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            for name, content in files.items():
                archive.writestr(f"{VERIFY.PLUGIN_ID}/{name}", content)
            for name, content in (extra or {}).items():
                archive.writestr(name, content)
        return archive_path

    def test_self_contained_archive_imports_without_repository_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            VERIFY.verify_archive(self.make_archive(Path(temporary)))

    def test_missing_backend_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "Missing files"):
                VERIFY.verify_archive(self.make_archive(Path(temporary), omit="main.py"))

    def test_traversal_and_second_roots_are_rejected_before_extracting(self) -> None:
        for bad_path in (f"{VERIFY.PLUGIN_ID}/../../escaped.py", "other-plugin/main.py", "/absolute.py"):
            with self.subTest(path=bad_path), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    VERIFY.verify_archive(self.make_archive(Path(temporary), extra={bad_path: ""}))

    def test_private_inventory_and_bytecode_are_rejected(self) -> None:
        for bad_path in (f"{VERIFY.PLUGIN_ID}/docs/environment-audit.json", f"{VERIFY.PLUGIN_ID}/py_modules/module.pyc"):
            with self.subTest(path=bad_path), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaisesRegex(ValueError, "Development/private"):
                    VERIFY.verify_archive(self.make_archive(Path(temporary), extra={bad_path: ""}))

    def test_duplicate_entries_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = self.make_archive(Path(temporary))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(archive_path, "a") as archive:
                    archive.writestr(f"{VERIFY.PLUGIN_ID}/main.py", "")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                VERIFY.verify_archive(archive_path)


if __name__ == "__main__":
    unittest.main()
