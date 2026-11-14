"""Regression checks for dependency drift and CI failure visibility."""

import contextlib
import io
import json
import runpy
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = runpy.run_path(str(ROOT / "scripts/ci/dependencies.py"))
REPORT = runpy.run_path(str(ROOT / "scripts/ci/report.py"))


class CiMaintenanceTests(unittest.TestCase):
    def copy_dependencies(self, root):
        for filename in (
            "requirements.lock",
            "requirements-dev.lock",
            "requirements-hashed.lock",
            "pyproject.toml",
            "python-dependencies.json",
        ):
            shutil.copyfile(ROOT / filename, root / filename)

    def test_dependency_drift_rejects_missing_architecture_and_changed_hash(self):
        for mutation in ("architecture", "hash", "project", "development"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_dependencies(root)
                if mutation in ("architecture", "hash"):
                    path = root / "python-dependencies.json"
                    module = json.loads(path.read_text())
                    if mutation == "architecture":
                        module["sources"] = [
                            source
                            for source in module["sources"]
                            if source.get("only-arches") != ["aarch64"]
                        ]
                    else:
                        module["sources"][0]["sha256"] = "0" * 64
                    path.write_text(json.dumps(module))
                else:
                    path = root / (
                        "pyproject.toml" if mutation == "project" else "requirements-dev.lock"
                    )
                    pins, _ = DEPENDENCIES["read_lock"](root / "requirements.lock")
                    path.write_text(
                        path.read_text().replace(f"atproto=={pins['atproto']}", "atproto==0.0.1")
                    )
                with self.assertRaises(ValueError):
                    DEPENDENCIES["check"](root)

    def test_health_advisories_fail_without_modifying_pins(self):
        pins, sources = DEPENDENCIES["check"](ROOT)
        original = (ROOT / "requirements.lock").read_bytes()
        responses = []
        for name, _version in sorted(pins.items()):
            urls = [
                {"url": source["url"], "digests": {"sha256": source["sha256"]}}
                for source in sources
            ]
            responses.extend(
                [
                    {
                        "urls": urls,
                        "vulnerabilities": [{"id": "INVENTED-ADVISORY", "withdrawn": None}]
                        if name == "atproto"
                        else [],
                    },
                    {"info": {"version": "999.0"}},
                ]
            )
        with (
            tempfile.TemporaryDirectory() as directory,
            contextlib.redirect_stdout(io.StringIO()),
            patch.dict(DEPENDENCIES["health"].__globals__, fetch=lambda _url: responses.pop(0)),
        ):
            output = Path(directory) / "report.json"
            with self.assertRaisesRegex(ValueError, "advisories"):
                DEPENDENCIES["health"](ROOT, output)
            self.assertTrue(any(item["vulnerabilities"] for item in json.loads(output.read_text())))
        self.assertEqual((ROOT / "requirements.lock").read_bytes(), original)

    def test_missing_native_results_and_preflight_failure_are_visible(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            REPORT["summary"](root, {"native": "failure"})
            self.assertIn("before a test report", (root / "summary.md").read_text())
            (root / "source-tests.json").write_text(
                json.dumps({"preflight": "No invented display"})
            )
            REPORT["summary"](root, {"native": "failure"})
            self.assertIn("setup failed before tests ran", (root / "summary.md").read_text())
            self.assertIn("<main></main>", (root / "index.html").read_text())
