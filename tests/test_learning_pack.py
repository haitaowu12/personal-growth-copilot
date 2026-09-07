from __future__ import annotations
import copy
import importlib.util
import json
import subprocess
import shutil
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot"
spec = importlib.util.spec_from_file_location(
    "learning_builder", SKILL / "scripts/build_learning.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class LearningPackTests(unittest.TestCase):
    def setUp(self):
        self.pack = json.loads(
            (SKILL / "assets/learning/requirements-writing.json").read_text()
        )

    def test_pack_validates_and_orders_only_explicit_prerequisites(self):
        self.assertEqual(builder.validate_pack(self.pack), [])
        self.assertEqual(
            builder.concept_order(self.pack), ["obligation", "measure", "purpose"]
        )

    def test_rejects_cycles_missing_evidence_and_unsafe_source_urls(self):
        for mutation in ("cycle", "source", "url", "duplicate", "answer"):
            p = copy.deepcopy(self.pack)
            if mutation == "cycle":
                p["concepts"][0]["prerequisites"] = ["purpose"]
            if mutation == "source":
                p["concepts"][0]["source_ids"] = ["not-found"]
            if mutation == "url":
                p["sources"][0]["url"] = "javascript:alert(1)"
            if mutation == "duplicate":
                p["concepts"][1]["id"] = "obligation"
            if mutation == "answer":
                p["concepts"][0]["questions"]["diagnostic"]["correct"] = "missing"
            with self.subTest(mutation=mutation):
                self.assertTrue(builder.validate_pack(p))

    def test_build_is_deterministic_and_escapes_topic_text(self):
        p = copy.deepcopy(self.pack)
        p["title"] = "</script><script>alert(1)</script>"
        raw = json.dumps(p).encode()
        one = builder.render(raw)
        self.assertEqual(one, builder.render(raw))
        self.assertNotIn("<script>alert(1)</script>", one)
        self.assertIn("connect-src", one)
        self.assertNotIn("https://fonts.", one)

    def test_bad_pack_fails_before_html_is_generated(self):
        self.pack["concepts"][0]["prerequisites"] = ["absent"]
        with self.assertRaises(ValueError):
            builder.render(json.dumps(self.pack).encode())


class SharedLearningReducerTests(unittest.TestCase):
    def test_browser_reducer_in_node(self):
        node = shutil.which("node")
        self.assertIsNotNone(
            node, "Node.js 22 is required for development checks, not for learners."
        )
        for name in ("core.js", "player.js"):
            syntax = subprocess.run(
                [node, "--check", str(SKILL / "assets/learning" / name)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(syntax.returncode, 0, syntax.stderr)
        result = subprocess.run(
            [node, "--test", str(ROOT / "tests/learning_core.test.cjs")],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class LearningDistributionTests(unittest.TestCase):
    def test_archive_is_reproducible_complete_and_excludes_working_data(self):
        import hashlib
        import io
        import zipfile

        spec = importlib.util.spec_from_file_location(
            "learning_package", ROOT / "scripts/package_learning.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        data = module.package_bytes()
        self.assertEqual(data, module.package_bytes())
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            self.assertIn("requirements-writing.html", names)
            self.assertIn("personal-growth-copilot/scripts/build_learning.py", names)
            self.assertFalse(
                any(
                    "progress" in n or "__pycache__" in n or "target-results" in n
                    for n in names
                )
            )
            manifest = json.loads(archive.read("MANIFEST.json"))
            self.assertEqual(set(manifest["files"]), names - {"MANIFEST.json"})
            for name, digest in manifest["files"].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
            # Build from only the packaged skill, outside the repository.
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                archive.extractall(tmp)
                builder = (
                    Path(tmp) / "personal-growth-copilot/scripts/build_learning.py"
                )
                import sys

                output = Path(tmp) / "rebuilt.html"
                result = subprocess.run(
                    [sys.executable, str(builder), "--out", str(output)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    output.read_bytes(), archive.read("requirements-writing.html")
                )
