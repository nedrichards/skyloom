#!/usr/bin/env python3
"""Regenerate checked wheel hashes after pip download -r requirements.lock -d wheels.

Runtime: GNOME 51 Python 3.14, currently x86_64 only. No network in build commands.
"""

import hashlib
import json
import urllib.request
from pathlib import Path


def verify_wheel(wheel: Path, expected: str) -> str:
    """Verify downloaded bytes even when Python runs with optimization enabled."""
    with wheel.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != expected:
        raise ValueError(f"SHA-256 mismatch for {wheel.name}")
    return digest


def main(root: Path) -> None:
    sources = []
    requirements = []
    for wheel in sorted((root / "wheels").glob("*.whl")):
        name, version = wheel.name.split("-")[:2]
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{name}/{version}/json", timeout=30
        ) as response:
            metadata = json.load(response)
        item = next(f for f in metadata["urls"] if f["filename"] == wheel.name)
        digest = verify_wheel(wheel, item["digests"]["sha256"])
        requirements.append(f"{name}=={version} --hash=sha256:{digest}")
        sources.append({"type": "file", "url": item["url"], "sha256": digest, "dest": "wheels"})
    if not sources:
        raise ValueError("No downloaded wheels found; existing dependency locks were preserved")
    module = {
        "name": "python-dependencies",
        "buildsystem": "simple",
        "build-commands": [
            "pip3 install --no-index --no-deps --no-build-isolation --prefix=/app wheels/*.whl"
        ],
        "sources": sources,
    }
    (root / "python-dependencies.json").write_text(
        json.dumps(module, indent=2) + "\n", encoding="utf-8"
    )
    (root / "requirements-hashed.lock").write_text(
        "# GNOME 51, CPython 3.14, x86_64\n" + "\n".join(requirements) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main(Path(__file__).resolve().parent.parent)
