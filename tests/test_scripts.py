from __future__ import annotations

import tempfile
import unittest
from unittest import mock
from pathlib import Path

from importlib.util import module_from_spec, spec_from_file_location

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = spec_from_file_location(name, path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync = load("sync_skills", ROOT / ".github/scripts/sync_skills.py")
validate = load("validate_skills", ROOT / ".github/scripts/validate_skills.py")


class ScriptTests(unittest.TestCase):
    def test_parse_empty_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sources.yml"
            config.write_text("sources: []\n", encoding="utf-8")
            self.assertEqual(sync.parse_sources(config), [])

    def test_parse_source_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sources.yml"
            config.write_text(
                "sources:\n"
                "  - name: upstream-example\n"
                "    repository: 'https://github.com/acme/skills.git'\n"
                "    ref: main\n",
                encoding="utf-8",
            )
            self.assertEqual(
                sync.parse_sources(config),
                [
                    {
                        "name": "upstream-example",
                        "repository": "https://github.com/acme/skills.git",
                        "ref": "main",
                    }
                ],
            )

    def test_parse_paths_whitelist(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sources.yml"
            config.write_text("sources:\n  - name: x\n    repository: https://example/x\n    paths: [.system/skill-creator, .curated/playwright]\n", encoding="utf-8")
            parsed = sync.parse_sources(config)
            self.assertEqual(parsed[0]["paths"], [".system/skill-creator", ".curated/playwright"])

    def test_frontmatter_requires_name_and_description(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            path.write_text("---\nname: demo\ndescription: Works\n---\n", encoding="utf-8")
            self.assertEqual(validate.parse_frontmatter(path), ("demo", "Works", None))
            path.write_text("---\nname: demo\n---\n", encoding="utf-8")
            self.assertIn("description", validate.parse_frontmatter(path)[2] or "")

    def test_sync_copies_root_resources_and_preserves_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vendor = root / "vendor"
            vendor.mkdir()
            old = vendor / "src" / "old"
            old.mkdir(parents=True)
            (old / "SKILL.md").write_text("old", encoding="utf-8")
            upstream = root / "upstream"
            upstream.mkdir()
            (upstream / "SKILL.md").write_text("---\nname: root\ndescription: d\n---\n", encoding="utf-8")
            (upstream / "asset.txt").write_text("asset", encoding="utf-8")

            def fake_run(command, cwd=None):
                dest = Path(command[-1])
                dest.mkdir(parents=True)
                for item in upstream.iterdir():
                    if item.is_file():
                        shutil.copy2(item, dest / item.name)

            import shutil
            source = {"name": "src", "repository": "https://example.invalid/repo"}
            with mock.patch.object(sync, "run", side_effect=fake_run):
                self.assertEqual(sync.sync_source(source, vendor, root / "tmp"), 1)
            self.assertTrue((vendor / "src" / "src" / "asset.txt").exists())
            # A failed source must leave the previous vendor tree untouched.
            before = (vendor / "src" / "src" / "asset.txt").read_text()
            with mock.patch.object(sync, "run", side_effect=RuntimeError("network")):
                with self.assertRaises(RuntimeError):
                    sync.sync_source(source, vendor, root / "tmp2")
            self.assertEqual((vendor / "src" / "src" / "asset.txt").read_text(), before)

    def test_validate_rejects_directory_collisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in (root / "skills" / "same", root / "vendor" / "a" / "same"):
                path.mkdir(parents=True)
                (path / "SKILL.md").write_text("---\nname: " + path.parent.name + "\ndescription: d\n---\n", encoding="utf-8")
            self.assertEqual(validate.main.__name__, "main")
            with mock.patch("sys.argv", ["validate", "--root", str(root)]):
                self.assertEqual(validate.main(), 1)


if __name__ == "__main__":
    unittest.main()
