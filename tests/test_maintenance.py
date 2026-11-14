"""Offline checks for dependency lock generation; never fetch live metadata."""

import hashlib
import json
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/generate-dependencies.py"
TOOLS = runpy.run_path(str(SCRIPT))


class DependencyTests(unittest.TestCase):
    def test_checksum_and_optimized_python_reject_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "invented-1.0-py3-none-any.whl"
            wheel.write_bytes(b"synthetic wheel bytes")
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            self.assertEqual(TOOLS["verify_wheel"](wheel, digest), digest)
            wheel.write_bytes(b"tampered bytes")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                TOOLS["verify_wheel"](wheel, digest)
            result = subprocess.run(  # noqa: S603 — fixed interpreter/code and locally generated fixture paths.
                [
                    sys.executable,
                    "-O",
                    "-c",
                    (
                        "import runpy, sys; from pathlib import Path; "
                        "runpy.run_path(sys.argv[1])['verify_wheel'](Path(sys.argv[2]), sys.argv[3])"
                    ),
                    str(SCRIPT),
                    str(wheel),
                    digest,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SHA-256 mismatch", result.stderr)

    def test_empty_wheel_directory_preserves_existing_locks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / "requirements-hashed.lock"
            lock.write_text("existing lock", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "No downloaded wheels"):
                TOOLS["main"](root)
            self.assertEqual(lock.read_text(encoding="utf-8"), "existing lock")

    def test_manifest_and_hash_lock_use_verified_wheel(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheels = root / "wheels"
            wheels.mkdir()
            wheel = wheels / "invented-1.0-py3-none-any.whl"
            wheel.write_bytes(b"synthetic wheel bytes")
            metadata = {
                "urls": [
                    {
                        "filename": wheel.name,
                        "url": "https://example.invalid/caf\u00e9.whl",
                        "digests": {"sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()},
                    }
                ]
            }
            with (
                patch("urllib.request.urlopen"),
                patch("json.load", return_value=metadata),
            ):
                TOOLS["main"](root)
            manifest = json.loads((root / "python-dependencies.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["sources"][0]["url"], metadata["urls"][0]["url"])
            self.assertEqual(
                manifest["sources"][0]["sha256"], metadata["urls"][0]["digests"]["sha256"]
            )
            self.assertIn(
                "invented==1.0 --hash=sha256:" + manifest["sources"][0]["sha256"],
                (root / "requirements-hashed.lock").read_text(encoding="utf-8"),
            )

    def test_native_wheels_are_filtered_and_incomplete_platforms_preserve_locks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "wheels").mkdir()
            (root / "requirements.lock").write_text("invented==1.0\n")
            metadata = {"urls": []}
            paths = []
            for architecture in ("x86_64", "aarch64"):
                wheel = (
                    root / "wheels" / f"invented-1.0-cp314-cp314-manylinux_2_17_{architecture}.whl"
                )
                wheel.write_bytes(architecture.encode())
                paths.append(wheel)
                metadata["urls"].append(
                    {
                        "filename": wheel.name,
                        "url": "https://example.invalid/" + wheel.name,
                        "digests": {"sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()},
                    }
                )
            with patch("urllib.request.urlopen"), patch("json.load", return_value=metadata):
                TOOLS["main"](root)
                manifest = json.loads((root / "python-dependencies.json").read_text())
                self.assertEqual(
                    {tuple(source["only-arches"]) for source in manifest["sources"]},
                    {("x86_64",), ("aarch64",)},
                )
                lock = (root / "requirements-hashed.lock").read_text()
                self.assertEqual(lock.count("invented==1.0"), 1)
                self.assertEqual(lock.count("--hash=sha256:"), 2)
                paths[1].unlink()
                with self.assertRaisesRegex(ValueError, "Missing invented wheels"):
                    TOOLS["main"](root)
                self.assertEqual((root / "requirements-hashed.lock").read_text(), lock)

    def test_unknown_wheel_platform_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported wheel platform"):
            TOOLS["wheel_architectures"]("invented-1.0-cp314-cp314-win_amd64.whl")


class PerformanceMetricsTests(unittest.TestCase):
    def test_missing_samples_and_tail_latency_remain_visible(self):
        metrics = runpy.run_path(str(SCRIPT.with_name("performance-pass.py")))["distribution"]
        self.assertIsNone(metrics([]))
        samples = [10.0] * 99 + [120.0]
        result = metrics(samples)
        self.assertEqual(result["p95_ms"], 10)
        self.assertEqual(result["max_ms"], 120)
        self.assertEqual(result["over_50_ms"], 1)
        self.assertEqual(samples[-1], 120)
